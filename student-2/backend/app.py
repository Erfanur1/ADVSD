import os
import sqlite3
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student2.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.get("/health")
def health():
    return jsonify(status="ok", feature="portfolio-position-tracker")


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


# ---- trade_history: Read ----
@app.get("/trade-history")
def list_trade_history():
    rows = db().execute(
        "SELECT t.*, p.market_ticker FROM trade_history t "
        "JOIN positions p ON p.id = t.position_id "
        "ORDER BY t.id DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---- AI: risk analysis via shared AI-Mode ----
@app.post("/ai/analyze-risk")
def ai_analyze_risk():
    trace = []

    # PLAN: decide what data to use as context for the AI
    rows = db().execute("SELECT market_ticker, side, entry_price, size FROM positions").fetchall()
    context = "\n".join(
        f"- {r['size']} shares of {r['market_ticker']} ({r['side']} at ${r['entry_price']})"
        for r in rows
    )
    trace.append({"stage": "Plan", "detail": f"Selected {len(rows)} open positions as context."})

    if not rows:
        trace.append({"stage": "Act", "detail": "Skipped AI-Mode call; no positions to analyze."})
        return jsonify(output="No open positions to analyze.", agentic_trace=trace)

    # ACT: call the shared AI-Mode service
    trace.append({"stage": "Act", "detail": "Called AI-Mode with the gathered context."})
    ai_reachable = True
    output = ""
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={
                "task": "Analyze the risk of this prediction market portfolio and suggest any rebalancing. Keep the analysis strictly under 3 sentences.",
                "context": context,
            },
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
        trace.append({"stage": "Adapt", "detail": "Returned AI-Mode's risk analysis to the user."})

    return jsonify(output=output, agentic_trace=trace)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
