# Prediction Market Intelligence Hub

An Agentic AI microservices application for **prediction-market analysis** (41026 Advanced Software Development, 2026).

Users track, research, and analyse prediction markets (Polymarket / Kalshi style) through a single unified, AI-assisted web portal. All market data is **seeded mock/historical data** so local, CI, and cloud demos do not depend on a live third-party feed.

## Team & feature allocation

| Member | Feature | Owns |
|---|---|---|
| Alex Choi | Market Watchlist & Discovery | `student-1/` |
| Christopher Kumarelil Cherian | Portfolio & Position Tracker | `student-2/` |
| Humza Hussein | Market Research Notes & News Feed | `student-3/` |
| Erfanur Rahman | AI Market Analyst Assistant | `student-4/` |

> Add each member's GitHub username next to their name before the Week 4 submission.

## Architecture (Release 0)

Each student owns one **frontend (HTMX)**, one **backend/API (Python + Flask)**, and one **database (SQLite)** microservice. All frontends link from a shared home page (`shared/frontend/index.html`) with a shared CSS theme. A shared **AI-Mode** service wraps **Ollama** running an approved open-source LLM. Everything runs together via `docker-compose.yml`.

```
User → Frontend (HTMX) → Backend/API (Flask) → AI-Mode → Ollama → LLM
                              ↓
                        Database (SQLite)
```

The team implements the shared **Plan → Act → Observe → Adapt** agentic loop.

## Quick start (local)

Prerequisites: Docker Desktop, Git. (Ollama runs inside Docker Compose.)

```bash
# 1. Pull the LLM into the ollama volume (first run only)
docker compose up -d ollama
docker compose exec ollama ollama pull llama3.1:8b

# 2. Start the whole stack
docker compose up --build

# 3. Open the app
open http://localhost:8080        # unified home page
```

Individual services default to:

| Service | Port |
|---|---|
| Shared home page | 8080 |
| Student 1 frontend / backend | 5101 / 5001 |
| Student 2 frontend / backend | 5102 / 5002 |
| Student 3 frontend / backend | 5103 / 5003 |
| Student 4 frontend / backend | 5104 / 5004 |
| AI-Mode | 8000 |
| Ollama | 11434 |

## Repository layout

See the ASD 2026 spec §7.1. Top level: `.github/workflows/`, `docs/`, `shared/`, `student-1..4/`, `ai-services/`, `scripts/`, `docker-compose.yml`.

## Releases

| Release | Focus | Due |
|---|---|---|
| Release 0 | Agentic AI foundations, microservices, DevOps | 30 Aug 2026 |
| Release 1 | MCP, RAG, intelligent agent integration | 27 Sep 2026 |
| Release 2 | Multi-agent systems, testing, cloud deployment | 18 Oct 2026 |

## Approved AI stack

- **Ollama** runtime, **Llama 3.1 8B** (or Qwen2.5 7B) — approved open-source LLM only.
