# Project Handoff — Prediction Market Intelligence Hub

**Written by**: Claude Code, on Erfanur's Mac, 2026-09-03, because Docker kept
OOM-crashing on that machine's 8GB RAM and Erfanur is moving to a PC with more
RAM to continue. This file exists so a fresh Claude Code session (or a human)
can pick the project up with zero lost context.

**Read this file first in any new session on this project.** Then read the
two source-of-truth PDFs in `docs/reference/` before doing anything else —
this file summarises them but they are the actual authority.

---

## 1. What this project is

**ASD 2026 (41026 Advanced Software Development)** semester group project.
Topic: **Prediction Market Intelligence Hub** — an Agentic AI microservices
app for prediction-market analysis (Polymarket/Kalshi-style). Users track,
research, and analyse prediction markets through one unified AI-assisted web
portal. All market data is **seeded mock data** — deliberately not a live
third-party feed, so CI/local/cloud demos don't depend on external APIs.

- Full unit spec: `docs/reference/ASD_2026_Project_Specifications.pdf`
- This team's registered feature descriptions: `docs/reference/ASD2026_Registration_Form_PredictionMarketHub.pdf`
- **Repo**: https://github.com/Erfanur1/ADVSD

### Releases (graded incrementally)

| Release | Focus | Weight | Due |
|---|---|---|---|
| Release 0 | Agentic AI foundations, microservices, DevOps | 20% | 30 Aug 2026 (team is treating this as due end of the week it's actually being finished — deadline flexibility confirmed by Erfanur directly, not by the tutor) |
| Release 1 | MCP, RAG, intelligent agent integration | 30% | 27 Sep 2026 |
| Release 2 | Multi-agent systems, testing, cloud deployment | 30% | 18 Oct 2026 |

**We are currently finishing Release 0.**

### Team (4 members — confirmed pre-approved four-person structure per the
registration form template itself: *"N/A — this team has four (4) members
(approved four-person project structure)"*)

| Member | Feature | Owns |
|---|---|---|
| Alex Choi | Market Watchlist & Discovery | `student-1/` |
| Christopher (Christian) Kumarelil Cherian | Portfolio & Position Tracker | `student-2/` |
| Humza Hussein | Market Research Notes & News Feed | `student-3/` |
| **Erfanur Rahman (Erfy) — the user in this session** | AI Market Analyst Assistant | `student-4/` |

There is no student-5. This is intentional and already accounted for
(`.github/workflows/` only has student-1..4.yml, no student-5.yml — correct).

---

## 2. ⚠️ Important unresolved finding: naming drift from the registration form

The registration form PDF specifies **exact** table names and endpoint paths
per feature. **None of the four implementations match it exactly** — this was
discovered while writing this handoff and has not yet been raised with the
team or decided on. Flag this to Erfanur early in the next session rather
than silently "fixing" it — it affects all four students' already-merged
code, not just his.

| Feature | Registration form says | What's actually built |
|---|---|---|
| Student 1 (Watchlist) | `markets`, `watchlist`, `categories`; `/markets`, `/watchlist`, `/ai/trending` | **Matches closely** — this is the one that lines up |
| Student 2 (Portfolio) | `positions`, `portfolio_snapshots`, `position_categories`; `/positions`, `/portfolio/summary`, `/ai/portfolio-summary` | Built: `portfolios`, `positions`, `trade_history`; `/positions`, `/ai/analyze-risk`. **`portfolio_snapshots` and `position_categories` don't exist at all**, no `/portfolio/summary` |
| Student 3 (Research/News) | `notes`, `news_items`, `tags`; `/notes`, `/news`, `/ai/notes-summary` | Built: `research_notes`, `news_articles`, `sources`; `/notes`, `/news`, `/ai/briefing`. `tags` (evidence tags) doesn't exist — `sources` is a different concept (news publishers, not tags) |
| Student 4 (AI Analyst — Erfanur's own) | `analysis_reports`, `flags`, `ai_runs`; `/analysis`, `/ai/analyse`, `/analysis/flags` | Built: `markets`, `analyses`, `chat_messages`; `/analyses`, `/ai/analyze`, `/ai/chat`. **`flags` and `ai_runs` tables don't exist** — mispricing is folded into a `verdict` column instead of a separate flags table with type/score/rationale, and the Plan→Act→Observe→Adapt trace is returned in the API response but never persisted to a table |

This may or may not matter for grading depending on how literally the tutor
checks against the registration form vs. the general spec's phrasing
("≥3 tables, ≥10 records, CRUD, one AI endpoint" — which all four *do*
satisfy under their actual names). **This needs a team decision, not a
unilateral fix.** Options: leave as-is and note the deviation in the report,
or reconcile names/add the missing tables before Release 0 submission.

---

## 3. Current implementation status (verified, not assumed)

All of this was actually run and tested this session, not just read.

### student-1 (Alex) — Market Watchlist & Discovery — ✅ solid
Reference implementation the rest of the team mirrors. Full CRUD on
markets/watchlist, `/ai/trending` with proper Plan→Act→Observe→Adapt trace +
graceful fallback, tests passing, CI passing.

### student-4 (Erfanur) — AI Market Analyst Assistant — ✅ solid, merged (PR #3)
Built from scratch this session. 3 tables (`markets`, `analyses`,
`chat_messages`), full CRUD, `/ai/analyze` + `/ai/chat` both with proper
Plan→Act→Observe→Adapt trace + fallback, 7/7 tests passing, verified live
with a **real** LLM response (not just fallback) through the full Docker
stack. One real bug was found and fixed during manual testing: `/ai/chat`'s
history query wasn't scoped to `market_id`, so answers about different
markets bled into each other's context — fixed, verified, tests still pass.
Merged to `main`.

### student-3 (Humza) — Market Research Notes & News Feed — ✅ solid, merged (PR #4)
Independently verified by running his actual test suite: 4/4 passing.
Matches the reference pattern closely — proper PAOA trace, full CRUD on
`news_articles`/`research_notes`, `sources` as read-only reference data
(same pattern as student-1's `categories`), all 3 tables seeded 10+.
Also merged **PR #6 "unified theme redesign"** which restyled the shared
`theme.css`/`index.html` and touched student-1/3/4's frontend `app.py`
files' embedded HTML — verified this didn't break anything (student-4's
7 tests still pass, live-smoke-tested the new markup renders real data
correctly).

### student-2 (Christian) — Portfolio & Position Tracker — ⚠️ was broken, now fixed but NOT YET MERGED
His original PR #5 merged to `main` with real, confirmed-by-running bugs:
- `/api/positions` (frontend/tests) vs `/positions` (backend) route
  mismatch — his own test suite failed, and his frontend's positions table
  silently rendered empty
- No `init_db.py` / no DB seeding step in the Dockerfile — the container
  would never have created its tables in a real deployment
- `portfolios` only had 3 seeded rows (needs 10+), `trade_history` had
  **0 rows and zero endpoints** despite existing in the schema
- No `.github/workflows/student-2.yml` at all — confirmed via the GitHub
  Actions API that `student-2-ci` has **never run once**, which is why none
  of the above was caught before merge
- `/ai/analyze-risk` didn't implement the Plan→Act→Observe→Adapt trace
  pattern the rest of the team uses

**All of the above has been fixed** on branch `fix/student-2-release-0`
(committed as `eebb73d`, pushed to origin). Also fixed a second bug that
only surfaced once trade_history had real data: deleting a position with
trade history threw an unhandled `IntegrityError` (no `ON DELETE CASCADE`)
— fixed in schema, verified live (delete now returns 200 and cascades
correctly). 6/6 tests passing, verified live.

**⚠️ This branch is pushed but NO PULL REQUEST HAS BEEN OPENED YET.**
That's the very next action item — see §6.

---

## 4. Architecture facts worth knowing

- Each student has an **isolated SQLite DB** — not shared. student-4's
  `markets` table is its own copy, not a live query against student-1's.
- Shared services: `ollama` (LLM runtime), `ai-mode` (the one entry point
  every backend calls — `POST /ai/complete` with `{task, context}`, returns
  `{output, trace}`), `home` (unified index.html + shared CSS on :8080).
- Port map: student-N backend on 500N, frontend on 510N. ai-mode on 8000,
  ollama on 11434, home on 8080.
- **`LLM_MODEL` default was changed from `llama3.1:8b` to `llama3.2:3b`**
  this session (in `docker-compose.yml` and noted in root `README.md`).
  Reason: `llama3.1:8b` needs more RAM than a typical 8GB machine's Docker
  VM allocation and gets OOM-killed on load (`signal: killed` in ollama's
  logs — diagnosed and confirmed this session). `llama3.2:3b` fits
  comfortably. **This is shared config affecting all four backends' AI
  calls — the whole team should know about this change**, not just
  Erfanur. Worth a heads-up message to the group.
- The shared Plan→Act→Observe→Adapt pattern (as actually implemented,
  consistently, in student-1/3/4 and now student-2): a `trace`/
  `agentic_trace` array of `{stage, detail}` objects — Plan (what context
  was gathered), Act (call ai-mode), Observe (did we get a usable answer),
  Adapt (graceful fallback message if not, or confirmation if so).

---

## 5. Environment gotchas (Mac-specific, won't carry to the PC)

- Docker Desktop hung twice this session: once from disk being 99% full
  (fixed by clearing ~10GB of duplicate installers from Downloads), once
  from Ollama OOM-killing `llama3.1:8b` on 8GB RAM (fixed by the model
  swap above). **The PC should not have either problem** if it has more
  RAM and disk headroom, but worth checking `docker info` responds and
  `df -h` isn't near-full before assuming a Docker hang is code-related.
- No Homebrew, no `gh` CLI on this Mac — PRs were created by pasting the
  GitHub compare URL and clicking through the web UI, not `gh pr create`.
  If the PC has `gh` installed, that's a faster path.
- Local Python venvs used for testing without Docker were thrown together
  at `/tmp/s{1,2,3,4}venv` — these don't persist across shell sessions on
  this machine and definitely won't exist on the PC. Recreate as needed:
  `python3 -m venv <path> && <path>/bin/pip install -r backend/requirements.txt -r frontend/requirements.txt`.

---

## 6. Outstanding action items, roughly in priority order

1. **Open a PR for `fix/student-2-release-0`** (pushed, not yet a PR) and
   merge it — this fixes real, currently-broken code sitting on `main`.
2. **Raise the registration-form naming-drift finding (§2) with the team**
   — needs a decision, not a unilateral fix.
3. **Tell the team about the `LLM_MODEL` change** (§4) if it hasn't
   already reached them.
4. Erfanur's own remaining individual report deliverables (per the official
   spec, not yet started): Report §2.4–2.7 (his own ERD, just his 3
   tables) and §4 (his own architecture diagram).
5. The "up for grabs" team workload items Erfanur claimed: the shared
   Plan→Act→Observe→Adapt loop write-up (§9–10 of the report — largely
   already done in substance via this session's verification work, mostly
   needs writing up) and owning `docker-compose.yml` end-to-end (mostly
   done now that all 4 students' blocks are wired).
6. **The team's actual report document** — Erfanur shared a OneDrive
   (`.docx`) link to it, but it requires Microsoft account auth this
   session couldn't access (no OneDrive/Microsoft connector available,
   401 Unauthorized on fetch). Either get it downloaded/shared as a
   readable file, or confirm what's actually in it another way.
7. Tutor email was drafted earlier in this conversation (questions about
   team size confirmation, whether "local only" deployment blocks any
   external API use, data-source consistency across teammates, whether
   changing a registered feature's data source needs re-approval, and
   the AI Agent Configuration Guide) — **status unknown, may not have
   been sent.** Worth checking.
8. `docs/architecture/`, `docs/release-0/`, `docs/release-1/`,
   `docs/release-2/`, `docs/reports/` are all still empty 1-line
   placeholder READMEs, for the whole team, not just Erfanur.

---

## 7. How to actually run this

```bash
git clone https://github.com/Erfanur1/ADVSD.git
cd ADVSD
git checkout fix/student-2-release-0   # or main, once that PR is merged

# First run only — pull the LLM:
docker compose up -d ollama
docker compose exec ollama ollama pull llama3.2:3b

# Bring up everything:
docker compose up -d --build

# Open:
open http://localhost:8080   # unified home page, all 4 features linked
```

Run one student's tests locally without Docker:
```bash
cd student-4  # or 1/2/3
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt -r frontend/requirements.txt
PYTHONPATH=$PWD .venv/bin/python -m pytest tests/ -v
```

---

## 8. A note on how Erfanur likes to work (from this session)

- Wants things **actually verified**, not just read/assumed — ran test
  suites, hit live endpoints, checked real HTTP responses repeatedly
  rather than trusting code-read alone. Match that standard.
- Prefers being asked before consequential/team-visible actions (merging
  to `main`, deleting files not created this session) but is comfortable
  moving fast on his own branch/feature work once a plan is clear.
- Is pragmatic under time pressure (e.g. explicitly chose to fix a
  teammate's bugs directly rather than wait on slow team coordination,
  given the deadline) — but still wants teammates' individually-graded
  work flagged to them, not silently absorbed.
