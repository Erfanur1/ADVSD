import os
import re
import sqlite3
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student2.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")

# ---- Release 1: shared local MCP + RAG servers ----
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8100")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:8200")
MCP_ENABLED = os.getenv("MCP_ENABLED", "true").lower() == "true"
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"

# Tool boundary: this feature may only call these MCP tools.
ALLOWED_MCP_TOOLS = {"validate_portfolio", "get_exposure_summary"}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.get("/health")
def health():
    return jsonify(status="ok", feature="portfolio-position-tracker",
                   mcp_enabled=MCP_ENABLED, rag_enabled=RAG_ENABLED)


# ---- portfolios: Read ----
@app.get("/portfolios")
def list_portfolios():
    rows = db().execute("SELECT * FROM portfolios").fetchall()
    return jsonify([dict(r) for r in rows])


# ---- positions: full CRUD ----
@app.get("/positions")
def list_positions():
    portfolio_id = request.args.get("portfolio_id")
    sql, params = "SELECT p.*, pf.name as portfolio_name FROM positions p JOIN portfolios pf ON pf.id = p.portfolio_id WHERE 1=1", []
    if portfolio_id:
        sql += " AND p.portfolio_id = ?"
        params.append(portfolio_id)

    rows = db().execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/positions/<int:pid>")
def get_position(pid):
    row = db().execute("SELECT * FROM positions WHERE id=?", (pid,)).fetchone()
    return (jsonify(dict(row)), 200) if row else (jsonify(error="not found"), 404)


@app.post("/positions")
def add_position():
    data = request.get_json(force=True) or {}

    # NEW: reject bad trades before touching the database
    try:
        if not (0 < float(data["entry_price"]) < 1) or int(data["size"]) <= 0 or data["side"] not in ("YES", "NO"):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify(error="market_ticker, side (YES/NO), entry_price (0-1) and size (>0) are required"), 400

    conn = db()
    cur = conn.execute(
        "INSERT INTO positions (portfolio_id, market_ticker, side, entry_price, size) VALUES (?,?,?,?,?)",
        (
            data.get("portfolio_id", 1),
            data["market_ticker"],
            data["side"],
            data["entry_price"],
            data["size"]
        ),
    )

    # seed a day-0 price point so the chart has something to show
    yes = data["entry_price"] if data["side"] == "YES" else 1 - data["entry_price"]
    conn.execute(
        "INSERT INTO price_history (market_ticker, ts, yes_price) VALUES (?, date('now'), ?)",
        (data["market_ticker"], yes),
    )

    conn.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/positions/<int:pid>")
def update_position(pid):
    data = request.get_json(force=True) or {}
    conn = db()
    conn.execute(
        "UPDATE positions SET size=?, entry_price=? WHERE id=?",
        (data.get("size"), data.get("entry_price"), pid),
    )
    conn.commit()
    return jsonify(updated=pid)


@app.delete("/positions/<int:pid>")
def delete_position(pid):
    conn = db()
    conn.execute("DELETE FROM positions WHERE id=?", (pid,))
    conn.commit()
    return jsonify(deleted=pid)


# ---- price history (for the chart + RAG) ----
@app.get("/positions/<int:pid>/history")
def position_history(pid):
    conn = db()
    pos = conn.execute("SELECT * FROM positions WHERE id=?", (pid,)).fetchone()
    if not pos:
        return jsonify(error="not found"), 404
    rows = conn.execute(
        "SELECT ts, yes_price FROM price_history WHERE market_ticker=? ORDER BY ts",
        (pos["market_ticker"],),
    ).fetchall()
    points = []
    for r in rows:
        price = r["yes_price"] if pos["side"] == "YES" else 1 - r["yes_price"]
        points.append({
            "ts": r["ts"],
            "price": round(price, 3),
            "pnl": round((price - pos["entry_price"]) * pos["size"], 2),
        })
    return jsonify(position=dict(pos), points=points)


# ---- trade_history: Read ----
@app.get("/trade-history")
def list_trade_history():
    rows = db().execute(
        "SELECT t.*, p.market_ticker FROM trade_history t "
        "JOIN positions p ON p.id = t.position_id "
        "ORDER BY t.id DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---- MCP: frontend -> this backend -> shared MCP server ----
@app.post("/mcp/execute")
def mcp_execute():
    data = request.get_json(force=True, silent=True) or {}
    tool = data.get("tool")
    params = data.get("parameters") or {}

    if tool not in ALLOWED_MCP_TOOLS:
        return jsonify(status="rejected", error=f"Tool '{tool}' is not permitted for this feature."), 400
    if not MCP_ENABLED:
        return jsonify(status="disabled", error="MCP is disabled in this environment (MCP_ENABLED=false)."), 503

    try:
        resp = requests.post(f"{MCP_SERVER_URL}/mcp/call",
                             json={"tool": tool, "params": params}, timeout=30)
        body = resp.json()
    except Exception as exc:
        return jsonify(status="unavailable", error=f"MCP server unreachable: {exc}"), 502

    if resp.status_code >= 400 or "error" in body:
        return jsonify(status="error", error=body.get("error", f"MCP returned HTTP {resp.status_code}")), 502
    return jsonify(status="ok", tool=tool, result=body.get("result", {}))


# ---- RAG: frontend -> this backend -> shared RAG server ----
@app.post("/rag/ask")
def rag_ask():
    data = request.get_json(force=True, silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify(status="rejected", error="Query is required."), 400
    if len(query) > 500:
        return jsonify(status="rejected", error="Query too long (max 500 chars)."), 400
    if not RAG_ENABLED:
        return jsonify(status="disabled", error="RAG is disabled in this environment (RAG_ENABLED=false)."), 503

    try:
        resp = requests.post(f"{RAG_SERVER_URL}/rag/query", json={"question": query}, timeout=180)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        return jsonify(status="unavailable", error=f"RAG server unreachable: {exc}"), 502

    answer = body.get("answer", "")
    return jsonify(
        status="insufficient_context" if body.get("insufficient_context") else "ok",
        answer=answer,
        confidence=body.get("confidence", "Low"),
        generated=not answer.startswith("AI-Mode is currently unavailable"),
        citations=[
            {"id": f"S{i + 1}", "ref": c.get("id", ""), "source": c.get("source", ""),
             "snippet": c.get("excerpt", "")}
            for i, c in enumerate(body.get("citations", []))
        ],
    )


REFUSAL = re.compile(
    r"(can(?:no|\u2019|')t|unable to|not able to|won't)[^.]*\b(financial|investment)\b[^.]*advice"
    r"|not a (licensed |certified )?financial (advisor|adviser)"
    r"|consult (a|with a|your) (licensed |qualified )?(financial|professional)",
    re.I,
)
 
RISK_TASK = (
    "You are a portfolio analytics tool describing SIMULATED demo data. "
    "Describe this prediction-market portfolio's risk profile: which categories it is concentrated in, "
    "which outcomes it is betting for or against, and its largest possible loss. "
    "Use the exact tickers and dollar figures given. This is descriptive analysis, not advice, "
    "so do not add disclaimers. Maximum 3 sentences."
)
RISK_TASK_STRICT = (
    "State facts only, no disclaimers, no refusals. In 3 sentences, using the exact tickers and dollar "
    "figures below: (1) the biggest category by cost and its share, (2) the largest single position, "
    "(3) the total amount that could be lost."
)
 
 
def _strip_disclaimers(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(s for s in sentences if not REFUSAL.search(s)).strip()
 
 
def _call_ai(task, context):
    try:
        resp = requests.post(f"{AI_MODE_URL}/ai/complete",
                             json={"task": task, "context": context}, timeout=120)
        resp.raise_for_status()
        return resp.json().get("output", "").strip(), True
    except Exception:
        return "", False
 
 
@app.post("/ai/analyze-risk")
def ai_analyze_risk():
    trace = []
 
    # PLAN: gather positions and pre-compute the numbers, so the LLM describes
    # real figures instead of inventing them.
    rows = db().execute("SELECT market_ticker, side, entry_price, size FROM positions").fetchall()
    if not rows:
        trace.append({"stage": "Plan", "detail": "No open positions found."})
        trace.append({"stage": "Act", "detail": "Skipped AI-Mode call; no positions to analyze."})
        return jsonify(output="No open positions to analyze.", agentic_trace=trace)
 
    total = sum(r["entry_price"] * r["size"] for r in rows)
    by_cat = {}
    for r in rows:
        cat = r["market_ticker"].split("-")[0]
        by_cat[cat] = by_cat.get(cat, 0) + r["entry_price"] * r["size"]
    biggest = max(rows, key=lambda r: r["entry_price"] * r["size"])
    lines = [
        f"- {r['market_ticker']}: {r['side']} "
        f"({'betting FOR' if r['side'] == 'YES' else 'betting AGAINST'} this outcome), "
        f"{r['size']} contracts at ${r['entry_price']}, cost ${r['entry_price'] * r['size']:.2f}"
        for r in rows
    ]
    cats = ", ".join(f"{c} ${v:.2f} ({v / total:.0%})" for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1]))
    context = (f"Positions:\n" + "\n".join(lines) +
               f"\nTotal cost (maximum possible loss): ${total:.2f}"
               f"\nExposure by category: {cats}"
               f"\nLargest position: {biggest['market_ticker']} (${biggest['entry_price'] * biggest['size']:.2f})")
    known_terms = {r["market_ticker"].lower() for r in rows} | {c.lower() for c in by_cat}
    trace.append({"stage": "Plan", "detail": f"Selected {len(rows)} positions and pre-computed exposure across {len(by_cat)} categories."})
 
    # ACT: ask AI-Mode for a descriptive risk summary
    output, reachable = _call_ai(RISK_TASK, context)
    trace.append({"stage": "Act", "detail": "Called AI-Mode with positions and computed exposure."})
 
    # OBSERVE: is the answer usable, refusal-free and grounded in our tickers?
    def assess(text):
        cleaned = _strip_disclaimers(text)
        grounded = any(t in cleaned.lower() for t in known_terms)
        return cleaned, cleaned != text.strip(), grounded
 
    if not reachable or not output:
        trace.append({"stage": "Observe", "detail": "Received no usable answer from AI-Mode."})
        trace.append({"stage": "Adapt", "detail": "Returned a fallback message since AI-Mode could not be reached."})
        return jsonify(output="AI-Mode is currently unavailable. Please try again shortly.", agentic_trace=trace)
 
    cleaned, had_disclaimer, grounded = assess(output)
    trace.append({"stage": "Observe", "detail": (
        f"Answer received; disclaimer {'detected' if had_disclaimer else 'not present'}; "
        f"{'references' if grounded else 'does NOT reference'} portfolio tickers/categories.")})
 
    # ADAPT: strip disclaimers; retry once with a stricter prompt if the answer is
    # empty or ungrounded; fall back to the computed summary if that also fails.
    if cleaned and grounded:
        trace.append({"stage": "Adapt", "detail": "Removed disclaimer sentence(s) and returned the analysis." if had_disclaimer
                      else "Answer passed checks; returned AI-Mode's analysis."})
        return jsonify(output=cleaned, agentic_trace=trace)
 
    retry, _ = _call_ai(RISK_TASK_STRICT, context)
    retry_clean, _, retry_grounded = assess(retry) if retry else ("", False, False)
    if retry_clean and retry_grounded:
        trace.append({"stage": "Adapt", "detail": "First answer was a refusal/ungrounded; retried with a stricter prompt and returned that."})
        return jsonify(output=retry_clean, agentic_trace=trace)
 
    summary = (f"Your largest category is {max(by_cat, key=by_cat.get)} "
               f"({by_cat[max(by_cat, key=by_cat.get)] / total:.0%} of cost), the largest position is "
               f"{biggest['market_ticker']}, and the maximum possible loss is ${total:.2f}.")
    trace.append({"stage": "Adapt", "detail": "AI answers failed checks twice; returned a computed summary instead."})
    return jsonify(output=summary, agentic_trace=trace)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
