import os
import json
import requests
from flask import Flask, render_template_string, request
from markupsafe import escape

app = Flask(__name__)
# Uses internal Docker DNS name when running in compose, otherwise localhost
BACKEND_URL = os.environ.get("BACKEND_URL", "http://student-2-backend:5002")

PAGE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Portfolio & Position Tracker</title>
    <link rel="stylesheet" href="http://localhost:8080/css/theme.css?v=r1">
    <script src="http://localhost:8080/js/nav.js?v=r1" defer></script>
    <style>
      form input, form select { flex: 1 1 0; min-width: 0; margin: 0; }
      form select { flex: 0 0 90px; }
      form button { flex: 0 0 auto; white-space: nowrap; margin: 0; }
      .row { display: flex; gap: 10px; align-items: stretch; }
      .row input { flex: 1 1 auto; min-width: 0; }
      .row select { flex: 0 0 220px; }
      .row button { flex: 0 0 auto; white-space: nowrap; }
      .result { margin-top: 15px; }
      .ok { color: var(--ok); } .warn { color: var(--warn); } .err { color: var(--err); }
      .kv { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 8px 0; }
      .cite { font-size: 0.9em; opacity: 0.85; margin-bottom: 6px; }
      .trace li { margin-bottom: 4px; }
      .result p, .result ol, .result ul { margin: 6px 0; }
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
        <input type="number" step="0.01" min="0.01" max="0.99" name="entry_price" placeholder="Entry Price" required>
        <input type="number" min="1" name="size" placeholder="Size" required>
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
      <form class="row" hx-post="/rag/ask" hx-target="#rag-out" hx-swap="innerHTML" hx-indicator="#rag-loading" style="margin:0;">
        <input type="text" name="query" required maxlength="500"
               placeholder="e.g. Why is my POL-TRUMP-2026 position down?">
        <button type="submit">Query Knowledge Base</button>
      </form>
      <span id="rag-loading" class="htmx-indicator empty">Retrieving context &amp; generating answer&hellip;</span>
      <div id="rag-out" class="result">
        <p class="empty">Grounded answers, citations and a confidence level will appear here.</p>
      </div>
    </div>
  </section>

  <!-- Portfolio Validation (MCP) -->
  <section>
    <h2>Portfolio Validation</h2>
    <div class="panel">
      <form class="row" hx-post="/mcp/run-tool" hx-target="#mcp-out" hx-swap="innerHTML" hx-indicator="#mcp-loading" style="margin:0;">
        <select name="portfolio_id">
          {% for p in portfolios %}<option value="{{ p.id }}">{{ p.name }}</option>{% endfor %}
        </select>
        <button type="submit" name="tool" value="validate_portfolio">Run Portfolio Validation Tool</button>
        <button type="submit" name="tool" value="get_exposure_summary">Exposure by Category</button>
      </form>
      <span id="mcp-loading" class="htmx-indicator empty">Executing tool&hellip;</span>
      <div id="mcp-out" class="result">
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
      <span id="ai-loading" class="htmx-indicator empty">Thinking&hellip;</span>
      <div id="ai-out" class="result">
        <p class="empty">Run an analysis to see the AI's take on your portfolio risk and its Plan &rarr; Act &rarr; Observe &rarr; Adapt trace.</p>
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
        <p class="entry-title">{escape(r['market_ticker'])} <span class="pill">{escape(r['side'])}</span></p>
        <p class="entry-context">Entry ${escape(r['entry_price'])} &middot; Size {escape(r['size'])}</p>
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


def backend_error(data, fallback):
    """Turn a backend {status, error} payload into a readable message."""
    status = data.get("status", "error")
    cls = "warn" if status in ("disabled", "unavailable") else "err"
    return f'<p class="{cls}"><strong>{escape(status.title())}:</strong> {escape(data.get("error", fallback))}</p>'


@app.get("/")
def home():
    try:
        portfolios = requests.get(f"{BACKEND_URL}/portfolios", timeout=10).json()
    except Exception:
        portfolios = [{"id": 1, "name": "Main Portfolio"}]
    return render_template_string(PAGE, portfolios=portfolios)


@app.get("/positions-list")
def positions_list_route():
    return positions_list()


@app.get("/portfolio-options")
def portfolio_options():
    try:
        rows = requests.get(f"{BACKEND_URL}/portfolios", timeout=10).json()
    except Exception:
        rows = [{"id": 1, "name": "Main Portfolio"}]
    return "".join(f'<option value="{int(r["id"])}">{escape(r["name"])}</option>' for r in rows)


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
      <h3>{escape(pos.get('market_ticker', ''))} ({escape(pos.get('side', ''))}) &mdash; last {len(points)} days</h3>
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


# ---- RAG: grounded answer + citations + confidence ----
@app.post("/rag/ask")
def frontend_rag_ask():
    query = request.form.get("query", "")
    try:
        data = requests.post(f"{BACKEND_URL}/rag/ask", json={"query": query}, timeout=200).json()
    except Exception as exc:
        return f'<p class="err">Error reaching backend: {escape(exc)}</p>'

    status = data.get("status")
    if status == "insufficient_context":
        return f"""
          <p class="warn"><strong>Insufficient context.</strong> {escape(data.get('answer', ''))}</p>
          <p class="empty">Confidence: Insufficient &middot; no sources matched this question.</p>"""
    if status != "ok":
        return backend_error(data, "RAG request failed")

    conf = data.get("confidence", "Low")
    cls = {"High": "ok", "Medium": "warn"}.get(conf, "err")
    cites = "".join(
        f'<li class="cite"><strong>[{escape(c["id"])}]</strong> {escape(c["source"])} &middot; '
        f'<code>{escape(c["ref"])}</code><br>{escape(c["snippet"])}</li>'
        for c in data.get("citations", [])
    )
    note = "" if data.get("generated", True) else '<p class="empty">(AI-Mode offline: showing retrieved facts only)</p>'
    return f"""
      <p><strong>Answer:</strong> {escape(data.get('answer', ''))}</p>
      {note}
      <p><strong>Confidence:</strong> <span class="{cls}">{escape(conf)}</span></p>
      <p><strong>Sources:</strong></p>
      <ul>{cites or '<li>None</li>'}</ul>"""


# ---- MCP: structured tool result ----
@app.post("/mcp/run-tool")
def frontend_mcp_run():
    tool = request.form.get("tool", "validate_portfolio")
    params = {}
    if tool == "validate_portfolio":
        params["portfolio_id"] = int(request.form.get("portfolio_id", 1))
    try:
        data = requests.post(f"{BACKEND_URL}/mcp/execute",
                             json={"tool": tool, "parameters": params}, timeout=40).json()
    except Exception as exc:
        return f'<p class="err">Error reaching backend: {escape(exc)}</p>'
    if data.get("status") != "ok":
        return backend_error(data, "MCP request failed")

    res = data.get("result", {})
    header = f'<p class="empty">MCP tool <code>{escape(tool)}</code> returned:</p>'

    if tool == "validate_portfolio":
        t = res.get("totals", {})
        verdict = ('<span class="ok">VALID</span>' if res.get("valid")
                   else '<span class="err">INVALID</span>')
        issues = "".join(f'<li class="err">{escape(e)}</li>' for e in res.get("errors", [])) + \
                 "".join(f'<li class="warn">{escape(w)}</li>' for w in res.get("warnings", []))
        return f"""{header}
          <p><strong>Portfolio {escape(res.get('portfolio_id'))}:</strong> {verdict}
             &middot; {escape(res.get('positions_checked'))} positions checked</p>
          <div class="kv">
            <span>Cost basis</span><span>${escape(t.get('cost_basis'))}</span>
            <span>Max payout</span><span>${escape(t.get('max_payout'))}</span>
            <span>Max loss</span><span>${escape(t.get('max_loss'))}</span>
            <span>Max profit</span><span>${escape(t.get('max_profit'))}</span>
          </div>
          <ul>{issues or '<li class="ok">No issues found.</li>'}</ul>
          <details><summary>Raw JSON</summary><pre>{escape(json.dumps(res, indent=2))}</pre></details>"""

    rows = "".join(
        f'<span>{escape(c["category"])}</span><span>${escape(c["exposure"])} ({c["share"]:.0%})</span>'
        for c in res.get("by_category", [])
    )
    return f"""{header}
      <p><strong>Total exposure:</strong> ${escape(res.get('total_exposure'))}</p>
      <div class="kv">{rows}</div>
      <details><summary>Raw JSON</summary><pre>{escape(json.dumps(res, indent=2))}</pre></details>"""


# ---- AI-Mode risk analysis + agentic trace ----
@app.post("/ai/analyze-risk")
def ai_analyze_risk():
    try:
        data = requests.post(f"{BACKEND_URL}/ai/analyze-risk", timeout=120).json()
    except Exception as exc:  # noqa: BLE001
        return f'<p class="err">AI error: {escape(exc)}</p>'
    output = (data.get("output") or "").strip()
    trace = "".join(
        f'<li><strong>{escape(t.get("stage"))}:</strong> {escape(t.get("detail"))}</li>'
        for t in data.get("agentic_trace", [])
    )
    return f"""
      <p>{escape(output) if output else '<span class="empty">No output.</span>'}</p>
      <p><strong>Agentic trace:</strong></p>
      <ol class="trace">{trace}</ol>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5102)
