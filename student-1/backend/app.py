import os
import sqlite3
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student1.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8100")
RAG_URL = os.getenv("RAG_URL", "http://localhost:8200")
MULTI_AGENT_URL = os.getenv("MULTI_AGENT_URL", "http://localhost:8300")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.get("/health")
def health():
    return jsonify(status="ok", feature="market-watchlist-discovery")


# ---- markets: Read / search / filter ----
@app.get("/markets")
def list_markets():
    category = request.args.get("category")
    q = request.args.get("q")
    sql, params = "SELECT * FROM markets WHERE 1=1", []
    if category:
        sql += " AND category = ?"; params.append(category)
    if q:
        sql += " AND (title LIKE ? OR category LIKE ?)"; params.extend([f"%{q}%", f"%{q}%"])
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


# ---- watchlist: full CRUD ----
@app.get("/watchlist")
def list_watchlist():
    rows = db().execute(
        "SELECT w.*, m.title, m.category, m.current_probability "
        "FROM watchlist w JOIN markets m ON m.id = w.market_id "
        "ORDER BY w.priority DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/watchlist")
def add_watchlist():
    data = request.get_json(force=True) or {}
    if "market_id" not in data:
        return jsonify(error="market_id is required"), 400
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO watchlist (market_id, note, priority) VALUES (?,?,?)",
            (data["market_id"], data.get("note", ""), data.get("priority", 0)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify(error=f"market {data['market_id']} does not exist"), 404
    return jsonify(id=cur.lastrowid), 201


@app.put("/watchlist/<int:wid>")
def update_watchlist(wid):
    data = request.get_json(force=True) or {}
    conn = db()
    conn.execute(
        "UPDATE watchlist SET note=?, priority=? WHERE id=?",
        (data.get("note", ""), data.get("priority", 0), wid),
    )
    conn.commit()
    return jsonify(updated=wid)


@app.delete("/watchlist/<int:wid>")
def delete_watchlist(wid):
    conn = db()
    conn.execute("DELETE FROM watchlist WHERE id=?", (wid,))
    conn.commit()
    return jsonify(deleted=wid)


# ---- AI: trending summary via shared AI-Mode ----
@app.post("/ai/trending")
def ai_trending():
    trace = []

    # PLAN: decide what data to use as context for the AI
    rows = db().execute("SELECT title, category, current_probability, volume "
                        "FROM markets ORDER BY volume DESC LIMIT 6").fetchall()
    context = "\n".join(
        f"- {r['title']} ({r['category']}): p={r['current_probability']}, vol={r['volume']}"
        for r in rows
    )
    trace.append({"stage": "Plan", "detail": f"Selected top {len(rows)} markets by volume as context."})

    # ACT: call the shared AI-Mode service
    trace.append({"stage": "Act", "detail": "Called AI-Mode with the gathered context."})
    ai_reachable = True
    output = ""
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={"task": "Summarise which markets are trending and why.", "context": context},
            timeout=120,
        )
        resp.raise_for_status()
        output = resp.json().get("output", "")
    except Exception:
        ai_reachable = False

    # OBSERVE: check whether we got a usable answer
    got_answer = ai_reachable and bool(output)
    trace.append({"stage": "Observe", "detail": f"Received {'a' if got_answer else 'no'} usable answer from AI-Mode."})

    # ADAPT: fall back gracefully if AI-Mode was unreachable or returned nothing
    if not got_answer:
        output = "AI-Mode is currently unavailable. Please try again shortly."
        trace.append({"stage": "Adapt", "detail": "Returned a fallback message since AI-Mode could not be reached."})
    else:
        trace.append({"stage": "Adapt", "detail": "Returned AI-Mode's summary to the user."})

    return jsonify(output=output, agentic_trace=trace)


# ---- MCP: search live markets via the shared MCP server ----
@app.post("/mcp/search")
def mcp_search():
    trace = []
    data = request.get_json(force=True) or {}
    query = data.get("query", "")

    # PLAN
    trace.append({"stage": "Plan", "detail": f"Decided to search live markets via MCP for query: '{query}'."})

    # ACT
    trace.append({"stage": "Act", "detail": "Called the shared MCP server's search_markets tool."})
    mcp_reachable = True
    result = []
    meta = {}
    try:
        resp = requests.post(
            f"{MCP_URL}/mcp/call",
            json={"tool": "search_markets", "params": {"query": query, "source": "both"}},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        result = body.get("result", [])
        meta = body.get("meta", {})
    except Exception:
        mcp_reachable = False

    # OBSERVE
    got_results = mcp_reachable and bool(result)
    trace.append({"stage": "Observe", "detail": f"MCP server returned {len(result)} live market(s)." if got_results else "MCP server returned no usable results."})

    # ADAPT
    if not got_results:
        trace.append({"stage": "Adapt", "detail": "Returning an empty list; frontend will show a fallback message."})
    else:
        trace.append({"stage": "Adapt", "detail": "Returning live market results to the user."})

    return jsonify(markets=result, meta=meta, agentic_trace=trace)


# ---- RAG: grounded Q&A via the shared RAG server ----
@app.post("/rag/ask")
def rag_ask():
    trace = []
    data = request.get_json(force=True) or {}
    question = data.get("question", "")

    # PLAN
    trace.append({"stage": "Plan", "detail": f"Decided to ask the shared RAG server: '{question}'."})

    # ACT
    trace.append({"stage": "Act", "detail": "Called the shared RAG server's /rag/query endpoint."})
    rag_reachable = True
    answer, citations, confidence, insufficient = "", [], "Low", True
    try:
        resp = requests.post(f"{RAG_URL}/rag/query", json={"question": question}, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        answer = body.get("answer", "")
        citations = body.get("citations", [])
        confidence = body.get("confidence", "Low")
        insufficient = body.get("insufficient_context", True)
    except Exception:
        rag_reachable = False

    # OBSERVE
    got_answer = rag_reachable and bool(answer)
    trace.append({"stage": "Observe", "detail": f"RAG server returned an answer with confidence={confidence}, insufficient_context={insufficient}." if got_answer else "RAG server did not return a usable answer."})

    # ADAPT
    if not got_answer:
        answer = "RAG service is currently unavailable. Please try again shortly."
        trace.append({"stage": "Adapt", "detail": "Returned a fallback message since the RAG server could not be reached."})
    else:
        trace.append({"stage": "Adapt", "detail": "Returned the grounded answer, citations, and confidence to the user."})

    return jsonify(answer=answer, citations=citations, confidence=confidence, insufficient_context=insufficient, agentic_trace=trace)

# ---- Multi-Agent: Planner / Worker / Reviewer + human review ----
@app.post("/multi-agent/validate")
def multi_agent_validate():
    """Ask the shared Multi-Agent Server to validate a watchlist item against live market data."""
    trace = []
    data = request.get_json(force=True) or {}
    wid = data.get("watchlist_id")
    if wid is None:
        return jsonify(error="watchlist_id is required"), 400

    row = db().execute(
        "SELECT w.id, w.market_id, m.title, m.current_probability "
        "FROM watchlist w JOIN markets m ON m.id = w.market_id WHERE w.id = ?",
        (wid,),
    ).fetchone()
    if row is None:
        return jsonify(error=f"watchlist item {wid} not found"), 404

    params = {
        "feature": "watchlist",
        "market_id": str(data.get("market_id") or row["market_id"]),
        "source": data.get("source", "polymarket"),
        "submitted_value": row["current_probability"],
    }

    # PLAN
    trace.append({"stage": "Plan", "detail": f"Decided to have the Multi-Agent Server validate watchlist item {wid} ('{row['title']}') against live data."})

    # ACT
    trace.append({"stage": "Act", "detail": "Sent the task to the shared Multi-Agent Server (Planner, Worker, Reviewer)."})
    run = None
    try:
        resp = requests.post(
            f"{MULTI_AGENT_URL}/multi-agent/run",
            json={"task_type": "validate_market_action", "params": params},
            timeout=30,
        )
        resp.raise_for_status()
        run = resp.json()
    except Exception:
        run = None

    # OBSERVE
    if run:
        rec = run.get("review", {}).get("recommendation")
        trace.append({"stage": "Observe", "detail": f"Multi-Agent run {run.get('run_id')} is {run.get('status')} (reviewer recommendation: {rec})."})
    else:
        trace.append({"stage": "Observe", "detail": "Multi-Agent Server did not return a usable run."})

    # ADAPT
    if run:
        trace.append({"stage": "Adapt", "detail": "Returned the run for the human review step; nothing is applied until a person approves."})
    else:
        trace.append({"stage": "Adapt", "detail": "Multi-Agent Server is unavailable (disabled in the cloud build), so no validation was run."})

    return jsonify(run=run, available=run is not None, agentic_trace=trace)


@app.post("/multi-agent/review")
def multi_agent_review():
    """Pass the human decision (approve / correct / partial / reject) to the Multi-Agent Server."""
    data = request.get_json(force=True) or {}
    if not data.get("run_id") or not data.get("decision"):
        return jsonify(error="run_id and decision are required"), 400
    try:
        resp = requests.post(f"{MULTI_AGENT_URL}/multi-agent/review", json=data, timeout=15)
    except Exception:
        return jsonify(error="Multi-Agent Server is unavailable"), 503
    return jsonify(resp.json()), resp.status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)  # noqa: S104 -- required for Docker container networking; see Section 5 known-issue note
