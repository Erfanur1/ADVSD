import os
import requests
from flask import Flask, render_template_string, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API = os.getenv("BACKEND_URL", "http://student-1-backend:5001")

PAGE = """
<!doctype html><html><head>
<meta charset="utf-8"><title>Market Watchlist & Discovery</title>
<link rel="stylesheet" href="http://localhost:8080/css/theme.css?v=r1">
<script src="http://localhost:8080/js/nav.js?v=r1" defer></script>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head><body>
<header><h1>Market Watchlist &amp; Discovery</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>Markets</h2>
    <div class="toolbar">
      <input name="q" placeholder="Search markets or categories..."
             hx-get="/search" hx-target="#markets" hx-trigger="keyup changed delay:300ms, load">
    </div>
    <div id="markets" class="item-grid"></div>
  </section>

  <section>
    <h2>My watchlist</h2>
    <form class="add-row" hx-post="/watchlist/add" hx-target="#watchlist" hx-swap="innerHTML">
      <input name="market_id" placeholder="Market ID" required style="max-width:110px">
      <input name="note" placeholder="Note (optional)">
      <input name="priority" placeholder="Priority 0-3" style="max-width:120px">
      <button type="submit">Add to watchlist</button>
    </form>
    <div id="watchlist" class="entry-list" hx-get="/watchlist-list" hx-trigger="load"></div>
  </section>

  <section>
    <h2>Live market search (MCP)</h2>
    <div class="panel">
      <input name="mcpq" placeholder="Search live markets (e.g. election)" id="mcp-input">
      <button hx-post="/mcp-search" hx-include="#mcp-input" hx-target="#mcp-out" hx-indicator="#mcp-loading">Search Live</button>
      <span id="mcp-loading" class="htmx-indicator empty">Searching&hellip;</span>
      <div id="mcp-out"></div>
    </div>
  </section>

  <section>
    <h2>Ask a grounded question (RAG)</h2>
    <div class="panel">
      <input name="ragq" placeholder="e.g. What's driving sentiment in election markets?" id="rag-input" style="width:60%">
      <button hx-post="/rag-ask" hx-include="#rag-input" hx-target="#rag-out" hx-indicator="#rag-loading">Ask</button>
      <span id="rag-loading" class="htmx-indicator empty">Thinking&hellip;</span>
      <div id="rag-out"></div>
    </div>
  </section>

  <section>
    <h2>AI-Mode: what's trending?</h2>
    <div class="panel">
      <button hx-post="/ai" hx-target="#ai-out" hx-indicator="#ai-loading">Ask AI</button>
      <span id="ai-loading" class="htmx-indicator empty">Thinking&hellip;</span>
      <div id="ai-out"></div>
    </div>
  </section>
</main></body></html>
"""


def render_market(r):
    return f"""
    <article class="item-card">
      <div class="item-meta">
        <span class="pill">{r['category']}</span>
        <span class="prob">{int(r['current_probability']*100)}%</span>
      </div>
      <h3>{r['title']}</h3>
      <div class="item-sub">id {r['id']}</div>
      <div class="item-actions">
        <button hx-post="/watchlist/quick-add/{r['id']}" hx-target="#watchlist" hx-swap="innerHTML">
          + Watchlist
        </button>
      </div>
    </article>
    """


def render_entry(r):
    return f"""
    <div class="entry-row">
      <div class="entry-main">
        <p class="entry-title">{r['title']}</p>
        <p class="entry-context">Priority {r.get('priority', 0)}{' &middot; ' + r['note'] if r.get('note') else ''}</p>
      </div>
      <form class="entry-edit" hx-post="/watchlist/{r['id']}/update" hx-target="#watchlist" hx-swap="innerHTML">
        <input name="note" placeholder="Note" value="{r.get('note', '')}" style="max-width:140px">
        <input name="priority" placeholder="0-3" value="{r.get('priority', 0)}" style="max-width:60px">
        <button type="submit">Save</button>
      </form>
      <button hx-post="/watchlist/{r['id']}/delete" hx-target="#watchlist" hx-swap="innerHTML">
        Remove
      </button>
    </div>
    """


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/search")
def search():
    q = request.args.get("q", "")
    try:
        rows = requests.get(f"{API}/markets", params={"q": q}, timeout=10).json()
    except Exception:
        rows = []
    if not rows:
        return '<p class="empty">No markets match your search.</p>'
    return "".join(render_market(r) for r in rows)


@app.get("/watchlist-list")
def watchlist_list():
    try:
        rows = requests.get(f"{API}/watchlist", timeout=10).json()
    except Exception:
        rows = []
    if not rows:
        return '<p class="empty">Your watchlist is empty — add a market above.</p>'
    return "".join(render_entry(r) for r in rows)


@app.post("/watchlist/add")
def watchlist_add():
    payload = {
        "market_id": request.form.get("market_id"),
        "note": request.form.get("note", ""),
        "priority": request.form.get("priority", 0) or 0,
    }
    try:
        requests.post(f"{API}/watchlist", json=payload, timeout=10)
    except Exception:
        pass
    return watchlist_list()


@app.post("/watchlist/quick-add/<int:market_id>")
def watchlist_quick_add(market_id):
    try:
        requests.post(f"{API}/watchlist", json={"market_id": market_id, "note": "", "priority": 0}, timeout=10)
    except Exception:
        pass
    return watchlist_list()


@app.post("/watchlist/<int:wid>/delete")
def watchlist_delete(wid):
    try:
        requests.delete(f"{API}/watchlist/{wid}", timeout=10)
    except Exception:
        pass
    return watchlist_list()


@app.post("/watchlist/<int:wid>/update")
def watchlist_update(wid):
    payload = {
        "note": request.form.get("note", ""),
        "priority": request.form.get("priority", 0) or 0,
    }
    try:
        requests.put(f"{API}/watchlist/{wid}", json=payload, timeout=10)
    except Exception:
        pass
    return watchlist_list()


@app.post("/ai")
def ai():
    try:
        data = requests.post(f"{API}/ai/trending", timeout=120).json()
        output = data.get("output", "").strip()
        return f"<div>{output}</div>" if output else '<p class="empty">Nothing to report right now.</p>'
    except Exception:
        return '<p class="empty">Couldn\'t reach AI-Mode. Try again shortly.</p>'


@app.post("/mcp-search")
def mcp_search():
    query = request.form.get("mcpq", "")
    try:
        data = requests.post(f"{API}/mcp/search", json={"query": query}, timeout=20).json()
        markets = data.get("markets", [])
    except Exception:
        markets = []
    if not markets:
        return '<p class="empty">No live results (check MCP server is running, or try a different search).</p>'
    items = "".join(
        f'<article class="item-card"><div class="item-meta">'
        f'<span class="pill">{m.get("source","")}</span>'
        f'<span class="prob">{int(m.get("probability",0)*100)}%</span>'
        f'</div><h3>{m.get("title","")}</h3></article>'
        for m in markets
    )
    return items


@app.post("/rag-ask")
def rag_ask():
    question = request.form.get("ragq", "")
    try:
        data = requests.post(f"{API}/rag/ask", json={"question": question}, timeout=60).json()
    except Exception:
        return '<p class="empty">Couldn\'t reach the RAG service. Try again shortly.</p>'

    answer = data.get("answer", "")
    citations = data.get("citations", [])
    confidence = data.get("confidence", "Low")
    insufficient = data.get("insufficient_context", True)

    citation_html = "".join(f"<li>[{c.get('source','')}] {c.get('excerpt','')}</li>" for c in citations)
    badge = "insufficient-context" if insufficient else f"confidence-{confidence.lower()}"

    return f"""
    <div class="rag-answer">
      <p>{answer}</p>
      <p class="pill {badge}">Confidence: {confidence}{' (insufficient context)' if insufficient else ''}</p>
      {f'<ul class="citations">{citation_html}</ul>' if citation_html else ''}
    </div>
    """


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5101)
