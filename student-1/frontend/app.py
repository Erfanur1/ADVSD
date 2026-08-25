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
<link rel="stylesheet" href="http://localhost:8080/css/theme.css">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head><body>
<header><h1>Market Watchlist &amp; Discovery</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>Markets</h2>
    <input name="q" placeholder="Search markets..."
           hx-get="/search" hx-target="#markets" hx-trigger="keyup changed delay:300ms">
    <div id="markets" hx-get="/search" hx-trigger="load"></div>
  </section>

  <section>
    <h2>My Watchlist</h2>
    <form hx-post="/watchlist/add" hx-target="#watchlist" hx-swap="innerHTML">
      <input name="market_id" placeholder="Market ID" required style="width:90px">
      <input name="note" placeholder="Note (optional)">
      <input name="priority" placeholder="Priority (0-3)" style="width:110px">
      <button type="submit">Add to Watchlist</button>
    </form>
    <div id="watchlist" hx-get="/watchlist-list" hx-trigger="load"></div>
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
        f"<li><b>{r['title']}</b> (id={r['id']}) — {r['category']} (p={r['current_probability']}) "
        f"<button hx-post='/watchlist/quick-add/{r['id']}' hx-target='#watchlist' hx-swap='innerHTML'>+ Watchlist</button></li>"
        for r in rows
    )
    return f"<ul>{items or '<li>No markets.</li>'}</ul>"


@app.get("/watchlist-list")
def watchlist_list():
    try:
        rows = requests.get(f"{API}/watchlist", timeout=10).json()
    except Exception:
        rows = []

    items = "".join(
        f"""
        <li>
            <b>{r['title']}</b>
            — note: {r.get('note', '')}
            | priority: {r.get('priority', 0)}

            <form hx-post="/watchlist/{r['id']}/update"
                  hx-target="#watchlist"
                  hx-swap="innerHTML"
                  style="display:inline">
                <input name="note"
                       placeholder="New note"
                       value="{r.get('note', '')}"
                       style="width:120px">

                <input name="priority"
                       placeholder="0-3"
                       value="{r.get('priority', 0)}"
                       style="width:50px">

                <button type="submit">Save</button>
            </form>

            <button
                hx-post="/watchlist/{r['id']}/delete"
                hx-target="#watchlist"
                hx-swap="innerHTML">
                Remove
            </button>
        </li>
        """
        for r in rows
    )

    return f"<ul>{items or '<li>Your watchlist is empty.</li>'}</ul>"



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
        return data.get("output", "(no output)")
    except Exception as exc:  # noqa: BLE001
        return f"AI error: {exc}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5101)