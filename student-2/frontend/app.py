import os
import requests
from flask import Flask, render_template_string, request

app = Flask(__name__)
# Uses internal Docker DNS name when running in compose, otherwise localhost
BACKEND_URL = os.environ.get("BACKEND_URL", "http://student-2-backend:5002")

PAGE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Portfolio & Position Tracker</title>
    <link rel="stylesheet" href="http://localhost:8080/css/theme.css">
    <style>
      form input, form select { flex: 1 1 0; min-width: 0; margin: 0; }
      form select { flex: 0 0 90px; }
      form button { flex: 0 0 auto; white-space: nowrap; margin: 0; }
    </style>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<header>
    <h1>Portfolio &amp; Position Tracker</h1>
    <a href="http://localhost:8080/">&larr; Home</a>
</header>
<main>
  
  <!-- Open New Position Form -->
  <section>
    <h2>Open New Position</h2>
    <div class="panel">
      <form hx-post="/positions/add" hx-target="#positions" hx-swap="innerHTML"
      style="display:flex; gap:10px; align-items:stretch; margin:0;">
        <input type="text" name="market_ticker" placeholder="Ticker (e.g. BTC-100K)" required>
        <select name="side">
            <option value="YES">YES</option>
            <option value="NO">NO</option>
        </select>
        <input type="number" step="0.01" name="entry_price" placeholder="Entry Price" required>
        <input type="number" name="size" placeholder="Size" required>
        <button type="submit">Execute Trade</button>
      </form>
    </div>
  </section>

  <!-- Active Portfolio & Chart Container -->
  <section>
    <h2>Active Portfolio</h2>
    <div id="chart-container"></div>
    <div id="positions" class="entry-list" hx-get="/positions-list" hx-trigger="load"></div>
  </section>

  <!-- Market Intelligence (RAG) -->
  <section>
    <h2>Market Intelligence</h2>
    <div class="panel">
      <input type="text" id="rag-query" name="query" placeholder="Ask about historical asset performance..." style="width: 100%; margin-bottom: 10px; padding: 8px;">
      <button hx-post="/rag/ask" hx-include="#rag-query" hx-target="#rag-out" hx-swap="innerHTML" hx-indicator="#rag-loading">
        Query Knowledge Base
      </button>
      <span id="rag-loading" class="htmx-indicator empty" style="display:none;">Retrieving context&hellip;</span>
      <div id="rag-out" style="margin-top: 15px;">
        <p class="empty">Grounded answers and citations will appear here.</p>
      </div>
    </div>
  </section>

  <!-- Portfolio Validation (MCP) -->
  <section>
    <h2>Portfolio Validation</h2>
    <div class="panel">
      <button hx-post="/mcp/run-tool" hx-target="#mcp-out" hx-swap="innerHTML" hx-indicator="#mcp-loading">
        Run Portfolio Validation Tool
      </button>
      <span id="mcp-loading" class="htmx-indicator empty" style="display:none;">Executing tool&hellip;</span>
      <div id="mcp-out" style="margin-top: 15px;">
        <p class="empty">Structured tool outputs will appear here.</p>
      </div>
    </div>
  </section>

  <!-- Risk Analysis (AI-Mode) -->
  <section>
    <h2>Risk Analysis</h2>
    <div class="panel">
      <button hx-post="/ai/analyze-risk" hx-target="#ai-out" hx-swap="innerHTML" hx-indicator="#ai-loading">
        Analyze My Portfolio Risk
      </button>
      <span id="ai-loading" class="htmx-indicator empty" style="display:none;">Thinking&hellip;</span>
      <div id="ai-out" style="margin-top: 15px;">
        <p class="empty">Run an analysis to see the AI's take on your portfolio risk.</p>
      </div>
    </div>
  </section>

</main>
</body>
</html>
"""

def render_position(r):
    return f"""
    <div class="entry-row" id="pos-{r['id']}">
      <div class="entry-main">
        <p class="entry-title">{r['market_ticker']} <span class="pill">{r['side']}</span></p>
        <p class="entry-context">Entry ${r['entry_price']} &middot; Size {r['size']}</p>
      </div>
      <div style="display: flex; gap: 10px;">
          <button hx-get="/positions/{r['id']}/chart" hx-target="#chart-container" hx-swap="innerHTML">
            Manage / View Graph
          </button>
          <button hx-post="/positions/{r['id']}/close" hx-target="#positions" hx-swap="innerHTML">
            Close Position
          </button>
      </div>
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


@app.post("/positions/add")
def add_position():
    data = {
        "portfolio_id": 1,
        "market_ticker": request.form.get("market_ticker"),
        "side": request.form.get("side"),
        "entry_price": float(request.form.get("entry_price")),
        "size": int(request.form.get("size"))
    }
    try:
        requests.post(f"{BACKEND_URL}/positions", json=data, timeout=10)
    except Exception:
        pass
    return positions_list()


@app.post("/positions/<int:pos_id>/close")
def close_position(pos_id):
    try:
        requests.delete(f"{BACKEND_URL}/positions/{pos_id}", timeout=10)
    except Exception:
        pass
    return positions_list()


import json
from markupsafe import escape

@app.get("/positions/<int:pos_id>/chart")
def view_chart(pos_id):
    try:
        data = requests.get(f"{BACKEND_URL}/positions/{pos_id}/history", timeout=10).json()
    except Exception as exc:
        return f'<p class="empty">Could not load history: {escape(exc)}</p>'
    points = data.get("points", [])
    pos = data.get("position", {})
    if not points:
        return '<p class="empty">No price history for this position yet.</p>'

    payload = json.dumps({
        "labels": [p["ts"] for p in points],
        "pnl": [p["pnl"] for p in points],
        "price": [p["price"] for p in points],
    }).replace("</", "<\\/")
    cid = f"chart-{pos_id}"
    return f"""
    <div class="panel" style="margin-bottom: 20px;">
      <h3>{escape(pos.get('market_ticker', ''))} ({escape(pos.get('side', ''))}) — last {len(points)} days</h3>
      <canvas id="{cid}" height="100"></canvas>
      <script>
        (function () {{
          const d = {payload};
          new Chart(document.getElementById('{cid}'), {{
            type: 'line',
            data: {{
              labels: d.labels,
              datasets: [
                {{ label: 'P&L ($)', data: d.pnl, yAxisID: 'y', tension: 0.2 }},
                {{ label: 'Contract price', data: d.price, yAxisID: 'y1', tension: 0.2 }}
              ]
            }},
            options: {{ scales: {{ y1: {{ position: 'right', min: 0, max: 1 }} }} }}
          }});
        }})();
      </script>
      <button onclick="document.getElementById('chart-container').innerHTML=''">Close Chart</button>
    </div>
    """

@app.post("/rag/ask")
def frontend_rag_ask():
    query = request.form.get("query", "")
    try:
        data = requests.post(f"{BACKEND_URL}/rag/ask", json={"query": query}, timeout=15).json()
        citations_html = "".join(f"<li>{c}</li>" for c in data.get("citations", []))
        return f"""
            <div>
                <p><strong>Answer:</strong> {data.get('answer')}</p>
                <p><strong>Confidence:</strong> {data.get('confidence')}</p>
                <p><strong>Sources:</strong></p>
                <ul>{citations_html if citations_html else '<li>None</li>'}</ul>
            </div>
        """
    except Exception as exc:
        return f'<p class="empty">Error reaching RAG: {exc}</p>'


@app.post("/mcp/run-tool")
def frontend_mcp_run():
    try:
        payload = {"tool": "validate_portfolio", "parameters": {"portfolio_id": 1}}
        data = requests.post(f"{BACKEND_URL}/mcp/execute", json=payload, timeout=15).json()
        if "error" in data:
            return f"<p style='color:red;'>{data['error']}</p>"
        return f"<pre>{data.get('result')}</pre>"
    except Exception as exc:
        return f'<p class="empty">Error reaching MCP: {exc}</p>'


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