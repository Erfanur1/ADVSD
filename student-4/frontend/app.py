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
</head><body>
<header><h1>AI Market Analyst Assistant</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>Markets</h2>
    <input name="q" placeholder="Search markets..."
           hx-get="/search" hx-target="#markets" hx-trigger="keyup changed delay:300ms">
    <div id="markets" hx-get="/search" hx-trigger="load"></div>
  </section>

  <section>
    <h2>Saved Analyses</h2>
    <form hx-post="/analyses/add" hx-target="#analyses" hx-swap="innerHTML">
      <input name="market_id" placeholder="Market ID" required style="width:90px">
      <select name="verdict">
        <option value="fair">fair</option>
        <option value="overpriced">overpriced</option>
        <option value="underpriced">underpriced</option>
      </select>
      <input name="summary" placeholder="Summary (optional)" style="width:260px">
      <button type="submit">Save Analysis</button>
    </form>
    <div id="analyses" hx-get="/analyses-list" hx-trigger="load"></div>
  </section>

  <section>
    <h2>AI Market Analyst</h2>
    <form hx-post="/ai/analyze-market" hx-target="#ai-out" hx-swap="innerHTML">
      <input name="market_id" placeholder="Market ID to analyze" required style="width:160px">
      <button type="submit">Analyze for mispricing</button>
    </form>
    <form hx-post="/ai/ask" hx-target="#ai-out" hx-swap="innerHTML">
      <input name="market_id" placeholder="Market ID (optional)" style="width:160px">
      <input name="message" placeholder="Ask the AI analyst..." style="width:260px" required>
      <button type="submit">Ask</button>
    </form>
    <div id="ai-out"><pre>Ask a question or analyze a market to see the AI's response and its Plan-Act-Observe-Adapt trace.</pre></div>
  </section>
</main></body></html>
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
    items = "".join(
        f"<li><b>{r['title']}</b> (id={r['id']}) — {r['category']} (p={r['current_probability']})</li>"
        for r in rows
    )
    return f"<ul>{items or '<li>No markets.</li>'}</ul>"


def render_analyses():
    try:
        rows = requests.get(f"{API}/analyses", timeout=10).json()
    except Exception:
        rows = []

    items = "".join(
        f"""
        <li>
            <b>{r['title']}</b> — verdict: {r.get('verdict')}
            | confidence: {r.get('confidence')}
            <br>{r.get('summary', '')}
            <form hx-post="/analyses/{r['id']}/update"
                  hx-target="#analyses"
                  hx-swap="innerHTML"
                  style="display:inline">
                <select name="verdict">
                    <option value="fair" {"selected" if r.get('verdict') == 'fair' else ''}>fair</option>
                    <option value="overpriced" {"selected" if r.get('verdict') == 'overpriced' else ''}>overpriced</option>
                    <option value="underpriced" {"selected" if r.get('verdict') == 'underpriced' else ''}>underpriced</option>
                </select>
                <button type="submit">Save</button>
            </form>
            <button
                hx-post="/analyses/{r['id']}/delete"
                hx-target="#analyses"
                hx-swap="innerHTML">
                Remove
            </button>
        </li>
        """
        for r in rows
    )
    return f"<ul>{items or '<li>No saved analyses yet.</li>'}</ul>"


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
        return f"<pre>{data.get('output', '(no output)')}</pre>"
    except Exception as exc:  # noqa: BLE001
        return f"<pre>AI error: {exc}</pre>"


@app.post("/ai/ask")
def ai_ask():
    payload = {
        "message": request.form.get("message", ""),
        "market_id": request.form.get("market_id") or None,
    }
    try:
        data = requests.post(f"{API}/ai/chat", json=payload, timeout=120).json()
        return f"<pre>{data.get('output', '(no output)')}</pre>"
    except Exception as exc:  # noqa: BLE001
        return f"<pre>AI error: {exc}</pre>"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5104)
