import os
import sqlite3
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student1.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")


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
    conn = db()
    cur = conn.execute(
        "INSERT INTO watchlist (market_id, note, priority) VALUES (?,?,?)",
        (data["market_id"], data.get("note", ""), data.get("priority", 0)),
    )
    conn.commit()
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
    rows = db().execute("SELECT title, category, current_probability, volume "
                        "FROM markets ORDER BY volume DESC LIMIT 6").fetchall()
    context = "\n".join(
        f"- {r['title']} ({r['category']}): p={r['current_probability']}, vol={r['volume']}"
        for r in rows
    )
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={"task": "Summarise which markets are trending and why.", "context": context},
            timeout=120,
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc)), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
