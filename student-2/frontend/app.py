import os
import requests
from flask import Flask, render_template_string

app = Flask(__name__)
# Uses internal Docker DNS name when running in compose, otherwise localhost
BACKEND_URL = os.environ.get("BACKEND_URL", "http://student-2-backend:5002")

PAGE = """
<!doctype html><html><head>
<meta charset="utf-8"><title>Portfolio & Position Tracker</title>
<link rel="stylesheet" href="http://localhost:8080/css/theme.css">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head><body>
<header><h1>Portfolio &amp; Position Tracker</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>Open positions</h2>
    <div id="positions" class="entry-list" hx-get="/positions-list" hx-trigger="load"></div>
  </section>

  <section>
    <h2>Agentic AI Risk Analyst</h2>
    <div class="panel">
      <button hx-post="/ai/analyze-risk" hx-target="#ai-out" hx-swap="innerHTML" hx-indicator="#ai-loading">
        Analyze My Portfolio Risk
      </button>
      <span id="ai-loading" class="htmx-indicator empty">Thinking&hellip;</span>
      <div id="ai-out">
        <p class="empty">Run an analysis to see the AI's take on your portfolio risk and its Plan &rarr; Act &rarr; Observe &rarr; Adapt trace.</p>
      </div>
    </div>
  </section>
</main></body></html>
"""


def render_position(r):
    return f"""
    <div class="entry-row" id="pos-{r['id']}">
      <div class="entry-main">
        <p class="entry-title">{r['market_ticker']} <span class="pill">{r['side']}</span></p>
        <p class="entry-context">Entry ${r['entry_price']} &middot; Size {r['size']}</p>
      </div>
      <button hx-post="/positions/{r['id']}/close" hx-target="#positions" hx-swap="innerHTML">
        Close Position
      </button>
    </div>
    """


def positions_list():
    try:
        rows = requests.get(f"{BACKEND_URL}/positions", timeout=10).json()
    except Exception:
        rows = []
    if not rows:
        return '<p class="empty">No open positions.</p>'
    return "".join(render_position(r) for r in rows)


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/positions-list")
def positions_list_route():
    return positions_list()


@app.post("/positions/<int:pos_id>/close")
def close_position(pos_id):
    try:
        requests.delete(f"{BACKEND_URL}/positions/{pos_id}", timeout=10)
    except Exception:
        pass
    return positions_list()


@app.post("/ai/analyze-risk")
def ai_analyze_risk():
    try:
        data = requests.post(f"{BACKEND_URL}/ai/analyze-risk", timeout=120).json()
        output = data.get("output", "").strip()
        return f"<div>{output}</div>" if output else '<p class="empty">No output.</p>'
    except Exception as exc:  # noqa: BLE001
        return f'<p class="empty">AI error: {exc}</p>'


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5102)
