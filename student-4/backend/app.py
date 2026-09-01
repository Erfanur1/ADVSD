import os
import sqlite3
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student4.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.get("/health")
def health():
    return jsonify(status="ok", feature="ai-market-analyst")


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
