import os
import requests
from flask import Flask, render_template_string, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
API = os.getenv("BACKEND_URL", "http://student-3-backend:5003")

PAGE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Research Notes &amp; News Feed</title>
<link rel="stylesheet" href="http://localhost:8080/css/theme.css">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
  /* Page-specific styling built on the shared theme's tokens (--bg, --panel, --ink,
     --muted, --accent, --line). No new palette is introduced. */

  .sr-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
  .sr-toolbar input { flex: 1; max-width: 420px; }

  .sr-feed { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }

  .sr-article { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
                padding: 16px; display: flex; flex-direction: column; gap: 8px; }
  .sr-article-meta { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .sr-pill { font-size: .78rem; padding: 2px 9px; border-radius: 999px;
             border: 1px solid var(--line); color: var(--muted); }
  .sr-article h3 { margin: 0; font-size: 1rem; line-height: 1.35; font-weight: 600; }
  .sr-article-source { font-size: .82rem; color: var(--muted); }
  .sr-article-summary { font-size: .88rem; color: var(--muted); margin: 0; flex-grow: 1; }
  .sr-article-actions { display: flex; justify-content: flex-end; }
  .sr-article-actions button { font-size: .85rem; padding: 6px 12px; }

  .sr-empty { color: var(--muted); font-size: .9rem; padding: 18px 0; }

  .sr-add-note { display: grid; grid-template-columns: 110px 1fr 1.6fr 1fr auto;
                 gap: 10px; margin-bottom: 18px; }
  .sr-add-note input { width: 100%; }

  .sr-notes { display: flex; flex-direction: column; gap: 10px; }
  .sr-note { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--accent);
             border-radius: 8px; padding: 12px 16px; display: flex; flex-wrap: wrap;
             align-items: center; gap: 10px 16px; }
  .sr-note-main { flex: 1 1 260px; min-width: 0; }
  .sr-note-title { font-weight: 600; margin: 0 0 2px; }
  .sr-note-context { font-size: .82rem; color: var(--muted); margin: 0; }
  .sr-tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .sr-tag { font-size: .74rem; color: var(--accent); border: 1px solid var(--line); border-radius: 999px;
            padding: 1px 8px; }
  .sr-note-edit { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .sr-note-edit input { width: 140px; }
  .sr-note-edit button, .sr-note > button { font-size: .82rem; padding: 6px 12px; }

  .sr-briefing-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
                        padding: 18px; }
  .sr-briefing-panel p.sr-empty { margin: 10px 0 0; }
  #ai-out:empty { display: none; }
  #ai-out { margin-top: 14px; font-family: inherit; font-size: .92rem; line-height: 1.5; }

  @media (max-width: 640px) {
    .sr-add-note { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <h1>Market Research Notes &amp; News Feed</h1>
  <a href="http://localhost:8080/">&larr; Home</a>
</header>
<main>

  <section>
    <h2>News feed</h2>
    <div class="sr-toolbar">
      <input name="q" placeholder="Search headlines..."
             hx-get="/search" hx-target="#news" hx-trigger="keyup changed delay:300ms, load">
    </div>
    <div id="news" class="sr-feed"></div>
  </section>

  <section>
    <h2>My research notes</h2>
    <form class="sr-add-note" hx-post="/notes/add" hx-target="#notes" hx-swap="innerHTML">
      <input name="article_id" placeholder="Article ID" required>
      <input name="title" placeholder="Note title">
      <input name="content" placeholder="What did you find?">
      <input name="tags" placeholder="tags, comma, separated">
      <button type="submit">Add note</button>
    </form>
    <div id="notes" class="sr-notes" hx-get="/notes-list" hx-trigger="load"></div>
  </section>

  <section>
    <h2>AI-Mode: research briefing</h2>
    <div class="sr-briefing-panel">
      <button hx-post="/ai" hx-target="#ai-out" hx-indicator="#ai-loading">
        Ask for a briefing
      </button>
      <span id="ai-loading" class="htmx-indicator sr-empty">Thinking&hellip;</span>
      <div id="ai-out"></div>
    </div>
  </section>

</main>
</body>
</html>
"""


def render_article(r):
    return f"""
    <article class="sr-article">
      <div class="sr-article-meta">
        <span class="sr-pill">{r['category']}</span>
        <span class="sr-article-source">{r['published_date']}</span>
      </div>
      <h3>{r['headline']}</h3>
      <p class="sr-article-summary">{r['summary']}</p>
      <div class="sr-article-source">Source: {r['source_name']} &middot; id {r['id']}</div>
      <div class="sr-article-actions">
        <button hx-post="/notes/quick-add/{r['id']}" hx-target="#notes" hx-swap="innerHTML">
          + Note
        </button>
      </div>
    </article>
    """


def render_note(r):
    tags = [t.strip() for t in (r.get("tags") or "").split(",") if t.strip()]
    tag_html = "".join(f'<span class="sr-tag">{t}</span>' for t in tags)
    title_val = (r.get("title") or "").replace('"', "&quot;")
    tags_val = (r.get("tags") or "").replace('"', "&quot;")
    content_val = (r.get("content") or "").replace('"', "&quot;")
    return f"""
    <div class="sr-note">
      <div class="sr-note-main">
        <p class="sr-note-title">{r.get('title') or '(untitled note)'}</p>
        <p class="sr-note-context">On: {r.get('headline', '')}</p>
        <div class="sr-tags">{tag_html}</div>
      </div>
      <form class="sr-note-edit" hx-post="/notes/{r['id']}/update" hx-target="#notes" hx-swap="innerHTML">
        <input name="title" placeholder="Title" value="{title_val}">
        <input name="content" placeholder="Note content" value="{content_val}">
        <input name="tags" placeholder="tags, comma, separated" value="{tags_val}">
        <button type="submit">Save</button>
      </form>
      <button hx-post="/notes/{r['id']}/delete" hx-target="#notes" hx-swap="innerHTML">
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
        rows = requests.get(f"{API}/news", params={"q": q}, timeout=10).json()
    except Exception:
        rows = []
    if not rows:
        msg = "No headlines match your search." if q else "No articles yet."
        return f'<p class="sr-empty">{msg}</p>'
    return "".join(render_article(r) for r in rows)


@app.get("/notes-list")
def notes_list():
    try:
        rows = requests.get(f"{API}/notes", timeout=10).json()
    except Exception:
        rows = []
    if not rows:
        return '<p class="sr-empty">No notes yet — add one from a headline above.</p>'
    return "".join(render_note(r) for r in rows)


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
    payload = {
        "title": request.form.get("title", ""),
        "content": request.form.get("content", ""),
        "tags": request.form.get("tags", ""),
    }
    try:
        requests.put(f"{API}/notes/{nid}", json=payload, timeout=10)
    except Exception:
        pass
    return notes_list()


@app.post("/ai")
def ai():
    try:
        data = requests.post(f"{API}/ai/briefing", timeout=120).json()
        output = data.get("output", "").strip()
        if not output:
            return '<p class="sr-empty">The assistant had nothing to add right now.</p>'
        return f"<div>{output}</div>"
    except Exception:
        return '<p class="sr-empty">Couldn\'t reach AI-Mode. Try again shortly.</p>'


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5103)
