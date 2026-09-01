import os
import requests
from flask import Flask, render_template_string, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API = os.getenv("BACKEND_URL", "http://student-3-backend:5003")

PAGE = """
<!doctype html><html><head>
<meta charset="utf-8"><title>Market Research Notes & News Feed</title>
<link rel="stylesheet" href="http://localhost:8080/css/theme.css">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head><body>
<header><h1>Market Research Notes &amp; News Feed</h1>
<a href="http://localhost:8080/">&larr; Home</a></header>
<main>
  <section>
    <h2>News Feed</h2>
    <input name="q" placeholder="Search headlines..."
           hx-get="/search" hx-target="#news" hx-trigger="keyup changed delay:300ms">
    <div id="news" hx-get="/search" hx-trigger="load"></div>
  </section>

  <section>
    <h2>My Research Notes</h2>
    <form hx-post="/notes/add" hx-target="#notes" hx-swap="innerHTML">
      <input name="article_id" placeholder="Article ID" required style="width:90px">
      <input name="title" placeholder="Note title">
      <input name="content" placeholder="Content">
      <input name="tags" placeholder="tags,comma,separated">
      <button type="submit">Add Note</button>
    </form>
    <div id="notes" hx-get="/notes-list" hx-trigger="load"></div>
  </section>

  <section>
    <h2>AI-Mode: research briefing</h2>
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
        rows = requests.get(f"{API}/news", params={"q": q}, timeout=10).json()
    except Exception:
        rows = []
    items = "".join(
        f"<li><b>{r['headline']}</b> (id={r['id']}) — {r['category']} / {r['source_name']} "
        f"<button hx-post='/notes/quick-add/{r['id']}' hx-target='#notes' hx-swap='innerHTML'>+ Note</button></li>"
        for r in rows
    )
    return f"<ul>{items or '<li>No articles.</li>'}</ul>"


@app.get("/notes-list")
def notes_list():
    try:
        rows = requests.get(f"{API}/notes", timeout=10).json()
    except Exception:
        rows = []

    items = "".join(
        f"""
        <li>
            <b>{r.get('title', '')}</b> — on: {r.get('headline', '')}
            | tags: {r.get('tags', '')}

            <form hx-post="/notes/{r['id']}/update"
                  hx-target="#notes"
                  hx-swap="innerHTML"
                  style="display:inline">
                <input name="content"
                       placeholder="New content"
                       value="{r.get('content', '')}"
                       style="width:160px">

                <button type="submit">Save</button>
            </form>

            <button
                hx-post="/notes/{r['id']}/delete"
                hx-target="#notes"
                hx-swap="innerHTML">
                Remove
            </button>
        </li>
        """
        for r in rows
    )

    return f"<ul>{items or '<li>No notes yet.</li>'}</ul>"


@app.post("/notes/add")
def notes_add():
    payload = {
        "article_id": request.form.get("article_id"),
        "title": request.form.get("title", ""),
        "content": request.form.get("content", ""),
        "tags": request.form.get("tags", ""),
    }
    try:
        requests.post(f"{API}/notes", json=payload, timeout=10)
    except Exception:
        pass
    return notes_list()


@app.post("/notes/quick-add/<int:article_id>")
def notes_quick_add(article_id):
    try:
        requests.post(f"{API}/notes", json={"article_id": article_id, "title": "", "content": "", "tags": ""}, timeout=10)
    except Exception:
        pass
    return notes_list()


@app.post("/notes/<int:nid>/delete")
def notes_delete(nid):
    try:
        requests.delete(f"{API}/notes/{nid}", timeout=10)
    except Exception:
        pass
    return notes_list()


@app.post("/notes/<int:nid>/update")
def notes_update(nid):
    payload = {"content": request.form.get("content", "")}
    try:
        requests.put(f"{API}/notes/{nid}", json=payload, timeout=10)
    except Exception:
        pass
    return notes_list()


@app.post("/ai")
def ai():
    try:
        data = requests.post(f"{API}/ai/briefing", timeout=120).json()
        return data.get("output", "(no output)")
    except Exception as exc:  # noqa: BLE001
        return f"AI error: {exc}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5103)
