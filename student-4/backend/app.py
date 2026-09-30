import os
import sqlite3
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student4.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")

# ---- Release 1: shared local MCP + RAG servers ----
MCP_URL = os.getenv("MCP_URL", "http://localhost:8100")
RAG_URL = os.getenv("RAG_URL", "http://localhost:8200")
MCP_ENABLED = os.getenv("MCP_ENABLED", "true").lower() == "true"
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"

# Tool boundary: this feature may only call these read-only MCP tools.
ALLOWED_MCP_TOOLS = {"search_markets", "get_market_price", "compare_markets"}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.get("/health")
def health():
    return jsonify(status="ok", feature="ai-market-analyst",
                   mcp_enabled=MCP_ENABLED, rag_enabled=RAG_ENABLED)


# ---- markets: full CRUD ----
@app.get("/markets")
def list_markets():
    category = request.args.get("category")
    q = request.args.get("q")
    sql, params = "SELECT * FROM markets WHERE 1=1", []
    if category:
        sql += " AND category = ?"; params.append(category)
    if q:
        sql += " AND title LIKE ?"; params.append(f"%{q}%")
    rows = db().execute(sql + " ORDER BY volume DESC", params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/markets/<int:mid>")
def get_market(mid):
    row = db().execute("SELECT * FROM markets WHERE id=?", (mid,)).fetchone()
    return (jsonify(dict(row)), 200) if row else (jsonify(error="not found"), 404)


@app.post("/markets")
def create_market():
    data = request.get_json(force=True) or {}
    conn = db()
    cur = conn.execute(
        "INSERT INTO markets (title, category, current_probability, volume, close_date) "
        "VALUES (?,?,?,?,?)",
        (
            data.get("title"),
            data.get("category"),
            data.get("current_probability"),
            data.get("volume"),
            data.get("close_date"),
        ),
    )
    conn.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/markets/<int:mid>")
def update_market(mid):
    data = request.get_json(force=True) or {}
    conn = db()
    existing = conn.execute("SELECT * FROM markets WHERE id=?", (mid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute(
        "UPDATE markets SET title=?, category=?, current_probability=?, volume=?, close_date=? WHERE id=?",
        (
            data.get("title", existing["title"]),
            data.get("category", existing["category"]),
            data.get("current_probability", existing["current_probability"]),
            data.get("volume", existing["volume"]),
            data.get("close_date", existing["close_date"]),
            mid,
        ),
    )
    conn.commit()
    return jsonify(updated=mid)


@app.delete("/markets/<int:mid>")
def delete_market(mid):
    conn = db()
    existing = conn.execute("SELECT * FROM markets WHERE id=?", (mid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute("DELETE FROM markets WHERE id=?", (mid,))
    conn.commit()
    return jsonify(deleted=mid)


# ---- analyses: full CRUD ----
@app.get("/analyses")
def list_analyses():
    rows = db().execute(
        "SELECT a.*, m.title, m.category, m.current_probability "
        "FROM analyses a JOIN markets m ON m.id = a.market_id "
        "ORDER BY a.created_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/analyses")
def create_analysis():
    data = request.get_json(force=True) or {}
    conn = db()
    cur = conn.execute(
        "INSERT INTO analyses (market_id, verdict, summary, confidence) VALUES (?,?,?,?)",
        (
            data["market_id"],
            data.get("verdict", "fair"),
            data.get("summary", ""),
            data.get("confidence", 0.5),
        ),
    )
    conn.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/analyses/<int:aid>")
def update_analysis(aid):
    data = request.get_json(force=True) or {}
    conn = db()
    existing = conn.execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute(
        "UPDATE analyses SET verdict=?, summary=?, confidence=? WHERE id=?",
        (
            data.get("verdict", existing["verdict"]),
            data.get("summary", existing["summary"]),
            data.get("confidence", existing["confidence"]),
            aid,
        ),
    )
    conn.commit()
    return jsonify(updated=aid)


@app.delete("/analyses/<int:aid>")
def delete_analysis(aid):
    conn = db()
    existing = conn.execute("SELECT * FROM analyses WHERE id=?", (aid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute("DELETE FROM analyses WHERE id=?", (aid,))
    conn.commit()
    return jsonify(deleted=aid)


# ---- chat_messages: Create / Read / Delete ----
@app.get("/chat")
def list_chat():
    market_id = request.args.get("market_id")
    sql, params = "SELECT * FROM chat_messages WHERE 1=1", []
    if market_id:
        sql += " AND market_id = ?"; params.append(market_id)
    rows = db().execute(sql + " ORDER BY id ASC", params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.delete("/chat/<int:cid>")
def delete_chat(cid):
    conn = db()
    existing = conn.execute("SELECT * FROM chat_messages WHERE id=?", (cid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute("DELETE FROM chat_messages WHERE id=?", (cid,))
    conn.commit()
    return jsonify(deleted=cid)


def _call_ai_mode(task: str, context: str):
    """Shared Plan/Act helper: calls the shared AI-Mode service, returns (output, reachable)."""
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={"task": task, "context": context},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("output", ""), True
    except Exception:
        return "", False


# ---- AI: analyse a single market for mispricing ----
@app.post("/ai/analyze")
def ai_analyze():
    data = request.get_json(force=True) or {}
    market_id = data.get("market_id")
    trace = []

    conn = db()
    market = conn.execute("SELECT * FROM markets WHERE id=?", (market_id,)).fetchone()
    if market is None:
        return jsonify(error="market not found"), 404

    # PLAN: decide what context the LLM needs to judge this market
    context = (
        f"{market['title']} ({market['category']}): "
        f"current probability={market['current_probability']}, volume={market['volume']}, "
        f"closes={market['close_date']}"
    )
    trace.append({"stage": "Plan", "detail": f"Selected market #{market_id} as the context for analysis."})

    # ACT: call the shared AI-Mode service
    task = "Explain whether this prediction market looks fairly priced, overpriced, or underpriced, and why."
    trace.append({"stage": "Act", "detail": "Called AI-Mode with the market context."})
    output, ai_reachable = _call_ai_mode(task, context)

    # OBSERVE: check whether we got a usable answer
    got_answer = ai_reachable and bool(output)
    trace.append({"stage": "Observe", "detail": f"Received {'a' if got_answer else 'no'} usable answer from AI-Mode."})

    # ADAPT: fall back gracefully, otherwise persist the analysis
    if not got_answer:
        output = "AI-Mode is currently unavailable. Please try again shortly."
        trace.append({"stage": "Adapt", "detail": "Returned a fallback message since AI-Mode could not be reached."})
        return jsonify(output=output, agentic_trace=trace)

    conn.execute(
        "INSERT INTO analyses (market_id, verdict, summary, confidence) VALUES (?,?,?,?)",
        (market_id, "fair", output, 0.5),
    )
    conn.commit()
    trace.append({"stage": "Adapt", "detail": "Saved the AI's analysis to the analyses table."})

    return jsonify(output=output, agentic_trace=trace)


# ---- AI: freeform chat about markets ----
@app.post("/ai/chat")
def ai_chat():
    data = request.get_json(force=True) or {}
    message = data.get("message", "")
    market_id = data.get("market_id")
    trace = []

    conn = db()

    # PLAN: ground the chat in the requested market (if any) plus recent history
    context_parts = []
    if market_id:
        market = conn.execute("SELECT * FROM markets WHERE id=?", (market_id,)).fetchone()
        if market:
            context_parts.append(
                f"Market: {market['title']} ({market['category']}), "
                f"p={market['current_probability']}, volume={market['volume']}"
            )
    if market_id:
        history = conn.execute(
            "SELECT role, content FROM chat_messages WHERE market_id=? ORDER BY id DESC LIMIT 4",
            (market_id,),
        ).fetchall()
    else:
        history = conn.execute(
            "SELECT role, content FROM chat_messages WHERE market_id IS NULL ORDER BY id DESC LIMIT 4"
        ).fetchall()
    for h in reversed(history):
        context_parts.append(f"{h['role']}: {h['content']}")
    context = "\n".join(context_parts)
    trace.append({"stage": "Plan", "detail": "Gathered market context and recent chat history."})

    conn.execute(
        "INSERT INTO chat_messages (market_id, role, content) VALUES (?,?,?)",
        (market_id, "user", message),
    )
    conn.commit()

    # ACT: call the shared AI-Mode service
    trace.append({"stage": "Act", "detail": "Called AI-Mode with the chat context."})
    output, ai_reachable = _call_ai_mode(message, context)

    # OBSERVE
    got_answer = ai_reachable and bool(output)
    trace.append({"stage": "Observe", "detail": f"Received {'a' if got_answer else 'no'} usable answer from AI-Mode."})

    # ADAPT
    if not got_answer:
        output = "AI-Mode is currently unavailable. Please try again shortly."
        trace.append({"stage": "Adapt", "detail": "Returned a fallback message since AI-Mode could not be reached."})
    else:
        conn.execute(
            "INSERT INTO chat_messages (market_id, role, content) VALUES (?,?,?)",
            (market_id, "assistant", output),
        )
        conn.commit()
        trace.append({"stage": "Adapt", "detail": "Saved the assistant's reply to chat_messages."})

    return jsonify(output=output, agentic_trace=trace)


# ---- MCP: frontend -> this backend -> shared MCP server ----
def _mcp_call(tool, params):
    """Returns (payload, http_status). Enforces the tool boundary and the CI switch."""
    if tool not in ALLOWED_MCP_TOOLS:
        return {"status": "rejected", "error": f"Tool '{tool}' is not permitted for this feature."}, 400
    if not MCP_ENABLED:
        return {"status": "disabled", "error": "MCP is disabled in this environment (MCP_ENABLED=false)."}, 503
    try:
        resp = requests.post(f"{MCP_URL}/mcp/call", json={"tool": tool, "params": params}, timeout=30)
        body = resp.json()
    except Exception as exc:
        return {"status": "unavailable", "error": f"MCP server unreachable: {exc}"}, 502
    if resp.status_code >= 400 or "error" in body:
        code = resp.status_code if 400 <= resp.status_code < 500 else 502
        return {"status": "error", "error": body.get("error", f"MCP returned HTTP {resp.status_code}")}, code
    return {"status": "ok", "tool": tool, "result": body.get("result"), "meta": body.get("meta", {})}, 200


def _observe(payload):
    if payload["status"] == "ok":
        return "Shared MCP server returned a structured result."
    return f"MCP call ended with status '{payload['status']}': {payload['error']}"


@app.post("/mcp/execute")
def mcp_execute():
    data = request.get_json(force=True, silent=True) or {}
    tool = data.get("tool")
    params = data.get("parameters") or {}
    if not isinstance(params, dict):
        return jsonify(status="rejected", error="parameters must be an object"), 400

    trace = [{"stage": "Plan", "detail": f"Selected MCP tool '{tool}' with parameters {params}."}]
    payload, code = _mcp_call(tool, params)
    trace.append({"stage": "Act", "detail": "Called the shared MCP server's /mcp/call endpoint."
                  if payload["status"] not in ("rejected", "disabled") else "Did not call MCP (blocked before the call)."})
    trace.append({"stage": "Observe", "detail": _observe(payload)})
    trace.append({"stage": "Adapt", "detail": "Returned the tool result to the frontend." if code == 200
                  else "Returned a structured error so the frontend can explain what happened."})
    return jsonify({**payload, "agentic_trace": trace}), code


# ---- Cross-exchange mispricing: save an MCP comparison as an analysis ----
CONFIDENCE_BY_STATUS = {"mispriced": 0.9, "watch": 0.6, "fair": 0.7}


@app.post("/mispricing/save")
def mispricing_save():
    """
    Re-runs compare_markets server-side (the client's numbers are never trusted),
    upserts the Polymarket market into the markets table with its live price,
    and stores the verdict in analyses.
    """
    data = request.get_json(force=True, silent=True) or {}
    params = {"polymarket_id": str(data.get("polymarket_id") or ""),
              "kalshi_ticker": str(data.get("kalshi_ticker") or "")}
    trace = [{"stage": "Plan", "detail": f"Re-check {params['polymarket_id']} vs {params['kalshi_ticker']} live before saving."}]
    payload, code = _mcp_call("compare_markets", params)
    trace.append({"stage": "Act", "detail": "Called the shared MCP server's compare_markets tool."})
    trace.append({"stage": "Observe", "detail": _observe(payload)})
    if code != 200:
        trace.append({"stage": "Adapt", "detail": "Nothing saved because the live comparison failed."})
        return jsonify({**payload, "agentic_trace": trace}), code

    poly, kalshi, cmp = (payload["result"][k] for k in ("polymarket", "kalshi", "comparison"))
    if cmp["status"] == "fair":
        verdict = "fair"
    else:
        verdict = "overpriced" if cmp["gap"] > 0 else "underpriced"
    confidence = CONFIDENCE_BY_STATUS[cmp["status"]]
    if cmp["basis"].startswith("last-trade"):
        confidence = round(confidence - 0.2, 2)
    summary = (f"Cross-exchange check vs Kalshi {kalshi['id']} ({kalshi['title']}): "
               f"Polymarket {poly['probability']:.1%} vs Kalshi {kalshi['probability']:.1%}, "
               f"{cmp['abs_gap_points']} pts apart -> {cmp['status']}; {cmp['direction']}. Basis: {cmp['basis']}.")

    conn = db()
    try:
        row = conn.execute("SELECT id FROM markets WHERE title=?", (poly["title"],)).fetchone()
        if row:
            market_id = row["id"]
            conn.execute("UPDATE markets SET current_probability=?, volume=? WHERE id=?",
                         (poly["probability"], int(poly["volume"]), market_id))
        else:
            market_id = conn.execute(
                "INSERT INTO markets (title, category, current_probability, volume, close_date) VALUES (?,?,?,?,?)",
                (poly["title"], poly["category"] or "General", poly["probability"], int(poly["volume"]),
                 (poly["close_date"] or "unknown")[:10]),
            ).lastrowid
        analysis_id = conn.execute(
            "INSERT INTO analyses (market_id, verdict, summary, confidence) VALUES (?,?,?,?)",
            (market_id, verdict, summary, confidence),
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    trace.append({"stage": "Adapt", "detail": f"Saved verdict '{verdict}' (confidence {confidence}) as analysis #{analysis_id}."})
    return jsonify(status="ok", market_id=market_id, analysis_id=analysis_id, verdict=verdict,
                   confidence=confidence, comparison=cmp, agentic_trace=trace), 201


# ---- RAG: frontend -> this backend -> shared RAG server ----
@app.post("/rag/ask")
def rag_ask():
    data = request.get_json(force=True, silent=True) or {}
    query = (data.get("query") or "").strip()
    market_ids = data.get("market_ids") or ([data["market_id"]] if data.get("market_id") else [])
    if not query:
        return jsonify(status="rejected", error="Query is required."), 400
    if len(query) > 500:
        return jsonify(status="rejected", error="Query too long (max 500 chars)."), 400
    if (not isinstance(market_ids, list) or len(market_ids) > 3
            or not all(isinstance(m, str) and 0 < len(m) <= 80 for m in market_ids)):
        return jsonify(status="rejected", error="market_ids must be up to 3 short strings."), 400

    trace = [{"stage": "Plan", "detail": "Ask the shared RAG server to retrieve sources and answer only from them"
              + (f", pinned to markets {', '.join(market_ids)}." if market_ids else ".")}]
    if not RAG_ENABLED:
        trace.append({"stage": "Adapt", "detail": "RAG is disabled here, so no call was made."})
        return jsonify(status="disabled", error="RAG is disabled in this environment (RAG_ENABLED=false).",
                       agentic_trace=trace), 503
    body = {"question": query}
    if market_ids:
        body["market_ids"] = market_ids
    try:
        resp = requests.post(f"{RAG_URL}/rag/query", json=body, timeout=180)
        resp.raise_for_status()
        result = resp.json()
    except Exception as exc:
        trace.append({"stage": "Act", "detail": "Called the shared RAG server's /rag/query endpoint."})
        trace.append({"stage": "Observe", "detail": "RAG server could not be reached."})
        trace.append({"stage": "Adapt", "detail": "Returned an error instead of an ungrounded answer."})
        return jsonify(status="unavailable", error=f"RAG server unreachable: {exc}", agentic_trace=trace), 502

    answer = result.get("answer", "")
    citations = [{"id": f"S{i + 1}", "ref": c.get("id", ""), "source": c.get("source", ""),
                  "snippet": c.get("excerpt", "")} for i, c in enumerate(result.get("citations", []))]
    insufficient = bool(result.get("insufficient_context"))
    generated = not insufficient and not answer.startswith("AI-Mode is currently unavailable")
    trace.append({"stage": "Act", "detail": "Called the shared RAG server's /rag/query endpoint."})
    trace.append({"stage": "Observe", "detail": "No relevant sources were retrieved." if insufficient else
                  f"Retrieved {len(citations)} source(s); confidence {result.get('confidence', 'Low')}."})
    trace.append({"stage": "Adapt", "detail": (
        "Showed an insufficient-context response instead of an unsupported answer." if insufficient else
        "Returned the grounded answer with its citations." if generated else
        "AI-Mode was offline, so only the retrieved sources are shown.")})
    return jsonify(status="insufficient_context" if insufficient else "ok", answer=answer,
                   confidence=result.get("confidence", "Low"), generated=generated,
                   citations=citations, agentic_trace=trace)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
