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


# ---- AI: risk analysis via shared AI-Mode ----
@app.post("/ai/analyze-risk")
def ai_analyze_risk():
    rows = db().execute("SELECT market_ticker, side, entry_price, size FROM positions").fetchall()
    
    if not rows:
        return jsonify(response="No open positions to analyze."), 200

    context = "\n".join(
        f"- {r['size']} shares of {r['market_ticker']} ({r['side']} at ${r['entry_price']})"
        for r in rows
    )
    
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={
                "task": "Analyze the risk of this prediction market portfolio and suggest any rebalancing. Keep the analysis strictly under 3 sentences.", 
                "context": context
            },
            timeout=120,
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc)), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
