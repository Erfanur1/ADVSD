import os
import json
import requests
from flask import Flask, render_template_string, request
from markupsafe import escape
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API = os.getenv("BACKEND_URL", "http://student-4-backend:5004")

PAGE = """
<!doctype html><html><head>
<meta charset="utf-8"><title>AI Market Analyst Assistant</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="http://localhost:8080/css/theme.css?v=r1">
<script src="http://localhost:8080/js/nav.js?v=r1" defer></script>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
  .ai-forms{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}
  .ai-forms form, .row{display:flex;gap:10px;flex-wrap:wrap;margin:0}
  .row input{flex:1 1 220px;min-width:0}
  #ai-out:empty{display:none}
  .hint{font-size:.85rem;color:var(--muted);margin:8px 0 0}
  .pair-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
  @media (max-width:640px){.pair-grid{grid-template-columns:1fr}}
  .pair-grid h3{margin:0 0 8px;font-size:.95rem}
  .pick{display:flex;gap:8px;align-items:flex-start;padding:8px;border:1px solid var(--line);
        border-radius:8px;margin-bottom:6px;cursor:pointer;font-size:.88rem}
  .pick:hover{border-color:var(--line-strong);background:var(--panel-raised)}
  .pick:has(input:checked){border-color:var(--accent);background:var(--panel-raised)}
  .pick input{margin-top:3px;width:auto;flex:0 0 auto}
  .pick .num{color:var(--muted);font-size:.8rem}
  .picks{max-height:340px;overflow-y:auto;padding-right:4px}
  .compare-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px}
  .compare-head .direction{color:var(--muted);font-size:.9rem}
  .price-grid{display:grid;grid-template-columns:1fr 1fr .8fr;gap:12px}
  @media (max-width:760px){.price-grid{grid-template-columns:1fr}}
  .price-card{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:var(--panel)}
  .price-card.gap{background:var(--panel-raised)}
  .price-card .label{font-size:.75rem;color:var(--muted);font-weight:500}
  .price-card .price{font-size:1.6rem;font-weight:600;letter-spacing:-.02em;margin:4px 0 2px}
  .price-card .sub{font-size:.78rem;color:var(--muted)}
  .price-card .market{font-size:.84rem;margin:10px 0 6px;line-height:1.4}
  .kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:8px 0;font-size:.9rem}
  .status{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:.8rem;
          text-transform:uppercase;letter-spacing:.04em}
  .status.mispriced{background:var(--err-soft);color:var(--err)}
  .status.watch{background:var(--warn-soft);color:var(--warn)}
  .status.fair{background:var(--ok-soft);color:var(--ok)}
  .conf-High{color:var(--ok)}.conf-Medium{color:var(--warn)}.conf-Low{color:var(--err)}
  .cite{font-size:.85rem;margin-bottom:6px}
  .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
  details.trace{margin-top:10px;font-size:.85rem}
  details.trace li{margin-bottom:3px}
  .result{margin-top:12px}
  .result:empty{display:none}
</style>
</head><body>
<header><h1>AI Market Analyst Assistant</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>Cross-exchange mispricing</h2>
    <div class="panel">
      <form class="row" hx-post="/mispricing/search" hx-target="#pair-picker" hx-swap="innerHTML"
            hx-indicator="#pair-loading">
        <input name="q" placeholder="Search Polymarket and Kalshi (e.g. fed rate, bitcoin, pope)" required maxlength="120">
        <button type="submit">Search both exchanges</button>
      </form>
      <p class="hint">Live data via the shared MCP server. Pick the same event on each exchange, then compare.
         <b>Mispriced</b> means the order books don't overlap: one exchange's bid is above the other's ask.</p>
      <span id="pair-loading" class="htmx-indicator empty">Searching both exchanges&hellip;</span>
      <div id="pair-picker"></div>
      <div id="compare-out" class="result"></div>
    </div>
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
    <div id="analyses" class="entry-list" hx-get="/analyses-list" hx-trigger="load, analyses-changed from:body"></div>
  </section>

  <section>
    <h2>Ask with sources</h2>
    <div class="panel">
      <form class="row" hx-post="/rag/ask" hx-target="#rag-out" hx-swap="innerHTML" hx-indicator="#rag-loading">
        <input name="query" placeholder="e.g. What are bitcoin markets pricing for year end?" required maxlength="500">
        <button type="submit">Ask</button>
      </form>
      <p class="hint">Answers come only from sources retrieved by the shared RAG server, with citations and a
         confidence level. If nothing relevant is found, it says so instead of guessing.</p>
      <span id="rag-loading" class="htmx-indicator empty">Retrieving sources &amp; generating answer&hellip;</span>
      <div id="rag-out" class="result"></div>
    </div>
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
  <section>
    <h2>Stored markets</h2>
    <div class="toolbar">
      <input name="q" placeholder="Search markets..."
             hx-get="/search" hx-target="#markets" hx-trigger="keyup changed delay:300ms, load">
    </div>
    <div id="markets" class="item-grid"></div>
  </section>
</main></body></html>
"""


# ---------------- helpers ----------------

def pct(p):
    return "&mdash;" if p is None else f"{p * 100:.1f}%"


def cents(p):
    return "&mdash;" if p is None else f"{p * 100:.1f}&cent;"


def render_trace(trace):
    if not trace:
        return ""
    items = "".join(f"<li><strong>{escape(t.get('stage'))}:</strong> {escape(t.get('detail'))}</li>" for t in trace)
    return f'<details class="trace"><summary>Plan &rarr; Act &rarr; Observe &rarr; Adapt</summary><ol>{items}</ol></details>'


def backend_error(data, fallback):
    status = data.get("status", "error")
    cls = "warn" if status in ("disabled", "unavailable") else "err"
    return (f'<p class="{cls}"><strong>{escape(status.title())}:</strong> {escape(data.get("error", fallback))}</p>'
            + render_trace(data.get("agentic_trace")))


def post_backend(path, payload, timeout=60):
    """POST JSON to the backend; returns the decoded body or a synthetic error payload."""
    try:
        return requests.post(f"{API}{path}", json=payload, timeout=timeout).json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": f"Backend unreachable: {exc}"}


def render_market(r):
    return f"""
    <article class="item-card">
      <div class="item-meta">
        <span class="pill">{escape(r['category'])}</span>
        <span class="prob">{int(r['current_probability'] * 100)}%</span>
      </div>
      <h3>{escape(r['title'])}</h3>
      <div class="item-sub">id {escape(r['id'])}</div>
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
        summary = f" &middot; {escape(r['summary'])}" if r.get("summary") else ""
        items.append(f"""
        <div class="entry-row">
          <div class="entry-main">
            <p class="entry-title">{escape(r['title'])}</p>
            <p class="entry-context">
              <span class="pill">{escape(verdict)}</span>
              confidence {escape(r.get('confidence', ''))}{summary}
            </p>
          </div>
          <form class="entry-edit" hx-post="/analyses/{int(r['id'])}/update" hx-target="#analyses" hx-swap="innerHTML">
            <select name="verdict">{options}</select>
            <button type="submit">Save</button>
          </form>
          <button hx-post="/analyses/{int(r['id'])}/delete" hx-target="#analyses" hx-swap="innerHTML">
            Remove
          </button>
        </div>
        """)
    return "".join(items)


# ---------------- Release 0 pages ----------------

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


def render_ai(data):
    output = (data.get("output") or "").strip()
    if data.get("error") and not output:
        return f'<p class="err">{escape(data["error"])}</p>'
    body = f"<p>{escape(output)}</p>" if output else '<p class="empty">No output.</p>'
    return body + render_trace(data.get("agentic_trace"))


@app.post("/ai/analyze-market")
def ai_analyze_market():
    market_id = request.form.get("market_id")
    return render_ai(post_backend("/ai/analyze", {"market_id": market_id}, timeout=120))


@app.post("/ai/ask")
def ai_ask():
    payload = {
        "message": request.form.get("message", ""),
        "market_id": request.form.get("market_id") or None,
    }
    return render_ai(post_backend("/ai/chat", payload, timeout=120))


# ---------------- Release 1: cross-exchange mispricing (MCP) ----------------

def render_pick_list(data, field, label):
    if data.get("status") != "ok":
        return f"<div><h3>{label}</h3>{backend_error(data, 'Search failed')}</div>"
    rows = data.get("result") or []
    if not rows:
        return f'<div><h3>{label}</h3><p class="empty">No matching {label} markets.</p></div>'
    picks = "".join(f"""
      <label class="pick">
        <input type="radio" name="{field}" value="{escape(m['id'])}" required>
        <span>{escape(m['title'])}<br>
          <span class="num">{pct(m.get('probability'))} &middot; bid {cents(m.get('yes_bid'))} / ask {cents(m.get('yes_ask'))}</span>
        </span>
      </label>""" for m in rows)
    return f'<div><h3>{label}</h3><div class="picks">{picks}</div></div>'


@app.post("/mispricing/search")
def mispricing_search():
    q = (request.form.get("q") or "").strip()[:120]
    if not q:
        return '<p class="empty">Enter something to search for.</p>'
    results = {src: post_backend("/mcp/execute", {"tool": "search_markets",
                                                  "parameters": {"query": q, "source": src}})
               for src in ("polymarket", "kalshi")}
    return f"""
      <form hx-post="/mispricing/compare" hx-target="#compare-out" hx-swap="innerHTML" hx-indicator="#pair-loading">
        <div class="pair-grid">
          {render_pick_list(results['polymarket'], 'polymarket_id', 'Polymarket')}
          {render_pick_list(results['kalshi'], 'kalshi_ticker', 'Kalshi')}
        </div>
        <div class="actions"><button type="submit">Compare selected pair</button></div>
      </form>
      {render_trace(results['kalshi'].get('agentic_trace'))}"""


def render_side(m, name):
    return f"""
      <div class="price-card">
        <div class="label">{name} &middot; YES</div>
        <div class="price">{pct(m.get('probability'))}</div>
        <div class="sub">bid {cents(m.get('yes_bid'))} &middot; ask {cents(m.get('yes_ask'))}</div>
        <p class="market">{escape(m['title'])}</p>
        <code>{escape(m['id'])}</code>
      </div>"""


@app.post("/mispricing/compare")
def mispricing_compare():
    params = {"polymarket_id": request.form.get("polymarket_id", ""),
              "kalshi_ticker": request.form.get("kalshi_ticker", "")}
    data = post_backend("/mcp/execute", {"tool": "compare_markets", "parameters": params})
    if data.get("status") != "ok":
        return backend_error(data, "Comparison failed")

    res = data["result"]
    poly, kalshi, c = res["polymarket"], res["kalshi"], res["comparison"]
    edge = (f"edge after spread {c['edge_after_spread'] * 100:.1f} pts"
            if c["status"] == "mispriced" else "books overlap")
    # State the measured result so the model explains the real comparison instead of assuming a gap.
    question = (f"Polymarket prices \"{poly['title']}\" at {poly['probability']:.1%} and Kalshi prices the same "
                f"event at {kalshi['probability']:.1%}: {c['abs_gap_points']} points apart, rated {c['status']}. "
                f"Using only the sources, explain what this comparison shows and what could cause any difference.")
    return f"""
      <div class="compare-head">
        <span class="status {escape(c['status'])}">{escape(c['status'])}</span>
        <span class="direction">{escape(c['direction'])}</span>
      </div>
      <div class="price-grid">
        {render_side(poly, 'Polymarket')}
        {render_side(kalshi, 'Kalshi')}
        <div class="price-card gap">
          <div class="label">Gap</div>
          <div class="price">{escape(c['abs_gap_points'])} pts</div>
          <div class="sub">{edge}</div>
          <p class="market">Compared on {escape(c['basis'])}.</p>
        </div>
      </div>
      <div class="actions">
        <button class="primary" hx-post="/mispricing/save" hx-vals="{escape(json.dumps(params))}"
                hx-target="#save-status" hx-swap="innerHTML">Save as analysis</button>
        <button hx-post="/rag/ask" hx-vals="{escape(json.dumps({'query': question, 'market_ids': poly['id'] + ',' + kalshi['id']}))}"
                hx-target="#rag-out" hx-swap="innerHTML" hx-indicator="#rag-loading"
                onclick="document.getElementById('rag-out').scrollIntoView({{behavior:'smooth'}})">Explain this gap (RAG)</button>
      </div>
      <div id="save-status" class="result"></div>
      {render_trace(data.get('agentic_trace'))}"""


@app.post("/mispricing/save")
def mispricing_save():
    params = {"polymarket_id": request.form.get("polymarket_id", ""),
              "kalshi_ticker": request.form.get("kalshi_ticker", "")}
    data = post_backend("/mispricing/save", params)
    if data.get("status") != "ok":
        return backend_error(data, "Save failed")
    html = (f'<p class="ok">Saved as analysis #{int(data["analysis_id"])} on market #{int(data["market_id"])}: '
            f'<span class="pill">{escape(data["verdict"])}</span> (confidence {escape(data["confidence"])})</p>'
            + render_trace(data.get("agentic_trace")))
    return html, 200, {"HX-Trigger": "analyses-changed"}


# ---------------- Release 1: grounded answers (RAG) ----------------

@app.post("/rag/ask")
def rag_ask():
    payload = {"query": request.form.get("query", "")}
    if request.form.get("market_ids"):
        payload["market_ids"] = request.form["market_ids"].split(",")
    data = post_backend("/rag/ask", payload, timeout=200)
    status = data.get("status")
    asked = f'<p class="hint">Q: {escape(payload["query"])}</p>'

    if status == "insufficient_context":
        return (asked + f'<p class="warn"><strong>Insufficient context.</strong> {escape(data.get("answer", ""))}</p>'
                '<p class="empty">Confidence: Low &middot; no relevant sources were found, so no answer was generated.</p>'
                + render_trace(data.get("agentic_trace")))
    if status != "ok":
        return asked + backend_error(data, "RAG request failed")

    conf = data.get("confidence", "Low")
    cites = "".join(
        f'<li class="cite"><strong>[{escape(c["id"])}]</strong> {escape(c["source"])} &middot; '
        f'<code>{escape(c["ref"])}</code><br>{escape(c["snippet"])}</li>'
        for c in data.get("citations", [])
    )
    offline = "" if data.get("generated", True) else \
        '<p class="warn">AI-Mode is offline, so only the retrieved sources are shown.</p>'
    return f"""{asked}
      <p><strong>Answer:</strong> {escape(data.get('answer', ''))}</p>
      {offline}
      <p><strong>Confidence:</strong> <span class="conf-{escape(conf)}">{escape(conf)}</span></p>
      <p><strong>Sources:</strong></p>
      <ul>{cites or '<li>None</li>'}</ul>
      {render_trace(data.get('agentic_trace'))}"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5104)
