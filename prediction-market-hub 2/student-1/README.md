# Alex Choi — Market Watchlist & Discovery

Owns one frontend (HTMX), one backend/API (Flask), one database (SQLite).

This directory is the **reference implementation** for the team — a complete,
tested vertical slice (schema + seed, backend CRUD, HTMX frontend, pytest).
Students 2–4 mirror this structure for their own features.

Run locally: `docker compose up student-1-backend student-1-frontend`
Test: `cd student-1 && PYTHONPATH=$PWD python -m pytest tests/ -q`

Contents:
- `database/` — schema + seed (markets, watchlist, categories; 10+ rows each)
- `backend/` — Flask API: markets Read/search, watchlist CRUD, `/ai/trending`
- `frontend/` — HTMX page (search + AI-Mode panel), linked from the home page
- `tests/` — pytest suite (health, seeded data, watchlist CRUD)
