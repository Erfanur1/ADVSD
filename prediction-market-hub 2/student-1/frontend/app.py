import os
import requests
from flask import Flask, render_template_string, request

app = Flask(__name__)
API = os.getenv("BACKEND_URL", "http://student-1-backend:5001")

PAGE = """
<!doctype html><html><head>
<meta charset="utf-8"><title>Market Watchlist & Discovery</title>
<link rel="stylesheet" href="http://localhost:8080/css/theme.css">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head><body>
<header><h1>Market Watchlist &amp; Discovery</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <input name="q" placeholder="Search markets..."
           hx-get="/search" hx-target="#markets" hx-trigger="keyup changed delay:300ms">
    <div id="markets" hx-get="/search" hx-trigger="load"></div>
  </section>
  <section>
    <h2>AI-Mode: what's trending?</h2>
    <button hx-post="/ai" hx-target="#ai-out">Ask AI</button>
    <pre id="ai-out"></pre>
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
        f"<li><b>{r['title']}</b> — {r['category']} (p={r['current_probability']})</li>"
        for r in rows
    )
    return f"<ul>{items or '<li>No markets.</li>'}</ul>"

@app.post("/ai")
def ai():
    try:
        data = requests.post(f"{API}/ai/trending", timeout=120).json()
        return data.get("output", "(no output)")
    except Exception as exc:  # noqa: BLE001
        return f"AI error: {exc}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5101)
