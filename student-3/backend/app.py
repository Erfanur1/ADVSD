import os
import sqlite3
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/student3.db")
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://ai-mode:8000")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8100")
RAG_URL = os.getenv("RAG_URL", "http://localhost:8200")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@app.get("/health")
def health():
    return jsonify(status="ok", feature="research-notes-news-feed")


# ---- sources: Read ----
@app.get("/sources")
def list_sources():
    rows = db().execute("SELECT * FROM sources ORDER BY reliability_score DESC").fetchall()
    return jsonify([dict(r) for r in rows])


# ---- news_articles: Read / search / filter ----
@app.get("/news")
def list_news():
    category = request.args.get("category")
    q = request.args.get("q")
    sql = ("SELECT n.*, s.name AS source_name FROM news_articles n "
           "JOIN sources s ON s.id = n.source_id WHERE 1=1")
    params = []
    if category:
        sql += " AND n.category = ?"; params.append(category)
    if q:
        sql += " AND n.headline LIKE ?"; params.append(f"%{q}%")
    rows = db().execute(sql + " ORDER BY n.published_date DESC", params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/news/<int:nid>")
def get_news(nid):
    row = db().execute(
        "SELECT n.*, s.name AS source_name FROM news_articles n "
        "JOIN sources s ON s.id = n.source_id WHERE n.id=?", (nid,)
    ).fetchone()
    return (jsonify(dict(row)), 200) if row else (jsonify(error="not found"), 404)


@app.post("/news")
def create_news():
    data = request.get_json(force=True) or {}
    conn = db()
    cur = conn.execute(
        "INSERT INTO news_articles (headline, source_id, category, published_date, summary) "
        "VALUES (?,?,?,?,?)",
        (
            data.get("headline"),
            data.get("source_id"),
            data.get("category"),
            data.get("published_date"),
            data.get("summary"),
        ),
    )
    conn.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/news/<int:nid>")
def update_news(nid):
    data = request.get_json(force=True) or {}
    conn = db()
    existing = conn.execute("SELECT * FROM news_articles WHERE id=?", (nid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute(
        "UPDATE news_articles SET headline=?, source_id=?, category=?, published_date=?, summary=? WHERE id=?",
        (
            data.get("headline", existing["headline"]),
            data.get("source_id", existing["source_id"]),
            data.get("category", existing["category"]),
            data.get("published_date", existing["published_date"]),
            data.get("summary", existing["summary"]),
            nid,
        ),
    )
    conn.commit()
    return jsonify(updated=nid)


@app.delete("/news/<int:nid>")
def delete_news(nid):
    conn = db()
    existing = conn.execute("SELECT * FROM news_articles WHERE id=?", (nid,)).fetchone()
    if existing is None:
        return jsonify(error="not found"), 404
    conn.execute("DELETE FROM news_articles WHERE id=?", (nid,))
    conn.commit()
    return jsonify(deleted=nid)


# ---- research_notes: full CRUD ----
@app.get("/notes")
def list_notes():
    rows = db().execute(
        "SELECT r.*, n.headline FROM research_notes r "
        "JOIN news_articles n ON n.id = r.article_id "
        "ORDER BY r.created_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/notes")
def add_note():
    data = request.get_json(force=True) or {}
    conn = db()
    cur = conn.execute(
        "INSERT INTO research_notes (article_id, title, content, tags) VALUES (?,?,?,?)",
        (data["article_id"], data.get("title", ""), data.get("content", ""), data.get("tags", "")),
    )
    conn.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/notes/<int:nid>")
def update_note(nid):
    data = request.get_json(force=True) or {}
    conn = db()
    conn.execute(
        "UPDATE research_notes SET title=?, content=?, tags=? WHERE id=?",
        (data.get("title", ""), data.get("content", ""), data.get("tags", ""), nid),
    )
    conn.commit()
    return jsonify(updated=nid)


@app.delete("/notes/<int:nid>")
def delete_note(nid):
    conn = db()
    conn.execute("DELETE FROM research_notes WHERE id=?", (nid,))
    conn.commit()
    return jsonify(deleted=nid)


# ---- AI: research briefing via shared AI-Mode ----
@app.post("/ai/briefing")
def ai_briefing():
    trace = []

    # PLAN: decide what data to use as context for the AI
    rows = db().execute(
        "SELECT headline, category, published_date, summary "
        "FROM news_articles ORDER BY published_date DESC LIMIT 6"
    ).fetchall()
    context = "\n".join(
        f"- {r['headline']} ({r['category']}, {r['published_date']}): {r['summary']}"
        for r in rows
    )
    trace.append({"stage": "Plan", "detail": f"Selected the {len(rows)} most recent articles as context."})

    # ACT: call the shared AI-Mode service
    trace.append({"stage": "Act", "detail": "Called AI-Mode with the gathered context."})
    ai_reachable = True
    output = ""
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={"task": "Write a short research briefing summarising these news items and what to watch.", "context": context},
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
        trace.append({"stage": "Adapt", "detail": "Returned AI-Mode's briefing to the user."})

    return jsonify(output=output, agentic_trace=trace)


# ---- MCP: search live markets via the shared MCP server ----
# Lets a user look up a live market to write a research note about,
# rather than only relying on the seeded/local news_articles table.
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


# ---- RAG: grounded Q&A over research notes + news via the shared RAG server ----
@app.post("/rag/ask")
def rag_ask():
    trace = []
    data = request.get_json(force=True) or {}
    question = data.get("question", "")

    # PLAN
    trace.append({"stage": "Plan", "detail": f"Decided to ask the shared RAG server, grounded in research notes and news: '{question}'."})

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

    return jsonify(answer=answer, citations=citations, confidence=confidence,
                    insufficient_context=insufficient, agentic_trace=trace)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
