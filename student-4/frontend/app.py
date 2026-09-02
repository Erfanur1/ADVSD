import os
import requests
from flask import Flask, render_template_string, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API = os.getenv("BACKEND_URL", "http://student-4-backend:5004")

PAGE = """
<!doctype html><html><head>
<meta charset="utf-8"><title>AI Market Analyst Assistant</title>
<link rel="stylesheet" href="http://localhost:8080/css/theme.css">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
  .ai-forms{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}
  .ai-forms form{display:flex;gap:10px;flex-wrap:wrap}
  #ai-out:empty{display:none}
</style>
</head><body>
<header><h1>AI Market Analyst Assistant</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>Markets</h2>
    <div class="toolbar">
      <input name="q" placeholder="Search markets..."
             hx-get="/search" hx-target="#markets" hx-trigger="keyup changed delay:300ms, load">
    </div>
    <div id="markets" class="item-grid"></div>
  </section>

  <section>
    <h2>Saved analyses</h2>
    <form class="add-row" hx-post="/analyses/add" hx-target="#analyses" hx-swap="innerHTML">
      <input name="market_id" placeholder="Market ID" required style="max-width:110px">
      <select name="verdict">
        <option value="fair">fair</option>
        <option value="overpriced">overpriced</option>
        <option value="underpriced">underpriced</option>
      </select>
      <input name="summary" placeholder="Summary (optional)">
      <button type="submit">Save analysis</button>
    </form>
    <div id="analyses" class="entry-list" hx-get="/analyses-list" hx-trigger="load"></div>
  </section>

  <section>
    <h2>Ask the analyst</h2>
    <div class="panel">
      <div class="ai-forms">
        <form hx-post="/ai/analyze-market" hx-target="#ai-out" hx-swap="innerHTML" hx-indicator="#ai-loading">
          <input name="market_id" placeholder="Market ID to analyze" required style="max-width:180px">
          <button type="submit">Analyze for mispricing</button>
        </form>
        <form hx-post="/ai/ask" hx-target="#ai-out" hx-swap="innerHTML" hx-indicator="#ai-loading">
          <input name="market_id" placeholder="Market ID (optional)" style="max-width:180px">
          <input name="message" placeholder="Ask the AI analyst..." required style="flex:1;min-width:200px">
          <button type="submit">Ask</button>
        </form>
      </div>
      <span id="ai-loading" class="htmx-indicator empty">Thinking&hellip;</span>
      <div id="ai-out">
        <p class="empty">Ask a question or analyze a market to see the AI's response and its Plan &rarr; Act &rarr; Observe &rarr; Adapt trace.</p>
      </div>
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
    </article>
    """


def render_analyses():
    try:
        rows = requests.get(f"{API}/analyses", timeout=10).json()
    except Exception:
        rows = []

    if not rows:
        return '<p class="empty">No saved analyses yet.</p>'

    items = []
    for r in rows:
        verdict = r.get("verdict", "fair")
        options = "".join(
            f'<option value="{v}" {"selected" if verdict == v else ""}>{v}</option>'
            for v in ("fair", "overpriced", "underpriced")
        )
        items.append(f"""
        <div class="entry-row">
          <div class="entry-main">
            <p class="entry-title">{r['title']}</p>
            <p class="entry-context">
              <span class="pill">{verdict}</span>
              confidence {r.get('confidence', '')}
              {' &middot; ' + r['summary'] if r.get('summary') else ''}
            </p>
          </div>
          <form class="entry-edit" hx-post="/analyses/{r['id']}/update" hx-target="#analyses" hx-swap="innerHTML">
            <select name="verdict">{options}</select>
            <button type="submit">Save</button>
          </form>
          <button hx-post="/analyses/{r['id']}/delete" hx-target="#analyses" hx-swap="innerHTML">
            Remove
          </button>
        </div>
        """)
    return "".join(items)


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


@app.get("/analyses-list")
def analyses_list():
    return render_analyses()


@app.post("/analyses/add")
def analyses_add():
    payload = {
        "market_id": request.form.get("market_id"),
        "verdict": request.form.get("verdict", "fair"),
        "summary": request.form.get("summary", ""),
    }
    try:
        requests.post(f"{API}/analyses", json=payload, timeout=10)
    except Exception:
        pass
    return render_analyses()


@app.post("/analyses/<int:aid>/update")
def analyses_update(aid):
    payload = {"verdict": request.form.get("verdict", "fair")}
    try:
        requests.put(f"{API}/analyses/{aid}", json=payload, timeout=10)
    except Exception:
        pass
    return render_analyses()


@app.post("/analyses/<int:aid>/delete")
def analyses_delete(aid):
    try:
        requests.delete(f"{API}/analyses/{aid}", timeout=10)
    except Exception:
        pass
    return render_analyses()


@app.post("/ai/analyze-market")
def ai_analyze_market():
    market_id = request.form.get("market_id")
    try:
        data = requests.post(f"{API}/ai/analyze", json={"market_id": market_id}, timeout=120).json()
        output = data.get("output", "").strip()
        return f"<div>{output}</div>" if output else '<p class="empty">No output.</p>'
    except Exception as exc:  # noqa: BLE001
        return f'<p class="empty">AI error: {exc}</p>'


@app.post("/ai/ask")
def ai_ask():
    payload = {
        "message": request.form.get("message", ""),
        "market_id": request.form.get("market_id") or None,
    }
    try:
        data = requests.post(f"{API}/ai/chat", json=payload, timeout=120).json()
        output = data.get("output", "").strip()
        return f"<div>{output}</div>" if output else '<p class="empty">No output.</p>'
    except Exception as exc:  # noqa: BLE001
        return f'<p class="empty">AI error: {exc}</p>'


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5104)
