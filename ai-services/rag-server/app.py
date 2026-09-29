"""
Shared RAG (Retrieval-Augmented Generation) Server -- Release 1, Task 3.

Runs locally, NOT containerised (per spec). Retrieves relevant context
(live market data + a local notes/news knowledge base) and generates a
grounded answer via the existing Release 0 AI-Mode/Ollama pipeline,
with source citations and a confidence category.

Run: python app.py   (listens on port 8200 by default)
"""
import os
import sys
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import market_data  # noqa: E402

app = Flask(__name__)
PORT = int(os.getenv("RAG_PORT", "8200"))
AI_MODE_URL = os.getenv("AI_MODE_URL", "http://localhost:8000")

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.json")

MIN_RELEVANT_SOURCES = 1  # below this, we return an insufficient-context response


def load_knowledge_base():
    """
    Local knowledge base of research notes / news snippets.
    Intended to be populated from Student 3's Market Research Notes &
    News Feed data; ships with a small placeholder set so the RAG
    server is testable before that integration is wired up.
    """
    if os.path.exists(KNOWLEDGE_PATH):
        try:
            with open(KNOWLEDGE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return [
        {
            "id": "kb-001",
            "market_keywords": ["election", "president", "politics"],
            "text": "Placeholder note: polling aggregates have shown a tightening race in recent weeks.",
            "source": "placeholder-knowledge-base",
        },
        {
            "id": "kb-002",
            "market_keywords": ["bitcoin", "crypto", "btc"],
            "text": "Placeholder note: BTC volatility has increased following recent macro announcements.",
            "source": "placeholder-knowledge-base",
        },
    ]


# ---------------- Student 2: Portfolio & Position Tracker knowledge ----------------
# Live entries built from the student-2 backend (read-only GETs), in the same
# {id, market_keywords, text, source} shape as the knowledge base above.
PORTFOLIO_API_URL = os.getenv("PORTFOLIO_API_URL", "http://localhost:5002")
_GENERIC_TICKER_PARTS = {"pol", "yes", "no", "up", "down"}


def _ticker_keywords(ticker):
    t = ticker.lower()
    parts = [x for x in t.split("-") if x.isalpha() and len(x) >= 3 and x not in _GENERIC_TICKER_PARTS]
    return [t] + parts


def load_portfolio_entries():
    """Returns [] if the portfolio service is down, so RAG keeps working."""
    try:
        positions = requests.get(f"{PORTFOLIO_API_URL}/positions", timeout=10).json()
        trades = requests.get(f"{PORTFOLIO_API_URL}/trade-history", timeout=10).json()
    except (requests.RequestException, ValueError):
        return []

    entries, by_cat = [], {}
    for p in positions:
        ticker = p["market_ticker"]
        cost = p["entry_price"] * p["size"]
        by_cat[ticker.split("-")[0]] = by_cat.get(ticker.split("-")[0], 0) + cost
        text = (f"Portfolio position {ticker} {p['side']} ({p.get('portfolio_name', '')}): "
                f"{p['size']} contracts bought at ${p['entry_price']} (cost ${cost:.2f}, max payout ${p['size']}).")
        try:
            pts = requests.get(f"{PORTFOLIO_API_URL}/positions/{p['id']}/history", timeout=10).json().get("points", [])
        except (requests.RequestException, ValueError):
            pts = []
        if len(pts) >= 2:
            first, last = pts[0], pts[-1]
            prices = [x["price"] for x in pts]
            move = "up" if last["price"] > first["price"] else "down" if last["price"] < first["price"] else "flat"
            text += (f" Price moved {move} from {first['price']} on {first['ts']} to {last['price']} on {last['ts']}"
                     f" (low {min(prices)}, high {max(prices)}); unrealised P&L ${last['pnl']}.")
        t_lines = [f"{t['trade_type']} {t['shares']} @ ${t['price']}" for t in trades if t["market_ticker"] == ticker]
        if t_lines:
            text += " Trades: " + ", ".join(t_lines) + "."
        entries.append({"id": f"portfolio:position#{p['id']}", "market_keywords": _ticker_keywords(ticker),
                        "text": text, "source": "student-2-portfolio"})

    total = sum(by_cat.values())
    if total:
        split = ", ".join(f"{c} ${v:.2f} ({v / total:.0%})" for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1]))
        holdings = "; ".join(f"{p['market_ticker']} {p['side']} x{p['size']} @ ${p['entry_price']}" for p in positions)
        entries.append({"id": "portfolio:exposure-summary",
                        "market_keywords": ["portfolio", "position", "holding", "exposure", "concentrat",
                                            "diversif", "risk", "evaluate", "my bets"],
                        "text": (f"Portfolio exposure: {len(positions)} open positions, total cost ${total:.2f}. "
                                 f"By category: {split}. Holdings: {holdings}."),
                        "source": "student-2-portfolio"})

    if positions:
        latest = max(positions, key=lambda p: p["id"])
        entries.append({"id": f"portfolio:latest-position#{latest['id']}",
                        "market_keywords": ["new position", "latest", "recent", "newest", "just added",
                                            "last trade", "just bought", "new trade"],
                        "text": (f"Most recently opened position: {latest['market_ticker']} {latest['side']}, "
                                 f"{latest['size']} contracts at ${latest['entry_price']} "
                                 f"(cost ${latest['entry_price'] * latest['size']:.2f}, max payout ${latest['size']})."),
                        "source": "student-2-portfolio"})
    return entries

def retrieve_context(question, market_id=None, source="both", top_k=3):
    """
    Very simple keyword-overlap retrieval (sufficient for Release 1).
    Returns a list of {text, source, citation_id} passages, plus any
    matched live market data as additional grounding context.
    """
    q_lower = question.lower()
    kb = load_knowledge_base() + load_portfolio_entries()
    scored = []
    for entry in kb:
        overlap = sum(1 for kw in entry["market_keywords"] if kw in q_lower)
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: -x[0])
    passages = [e for _, e in scored[:top_k]]

    market_context = None
    if market_id:
        market_context, _ = market_data.get_market_by_id(market_id, source=source)
    elif any(word in q_lower for word in ["market", "price", "probability", "trending"]):
        markets, _ = market_data.fetch_markets(source=source, query=question, limit=3)
        if markets:
            market_context = markets[0]

    return passages, market_context


def compute_confidence(passages, market_context):
    citation_count = len(passages) + (1 if market_context else 0)
    if citation_count >= 2:
        return "High"
    if citation_count == 1:
        return "Medium"
    return "Low"


@app.get("/health")
def health():
    return {"status": "ok", "service": "rag-server"}


@app.post("/rag/query")
def rag_query():
    """
    Body: {"question": "...", "market_id": "<optional>", "source": "polymarket|manifold|both"}
    Returns: {"answer", "citations": [...], "confidence", "insufficient_context": bool}
    """
    body = request.get_json(force=True) or {}
    question = body.get("question", "")
    market_id = body.get("market_id")
    source = body.get("source", "both")

    if not question:
        return jsonify({"error": "question is required"}), 400

    passages, market_context = retrieve_context(question, market_id=market_id, source=source)

    citations = []
    for p in passages:
        citations.append({"id": p["id"], "source": p["source"], "excerpt": p["text"]})
    if market_context:
        citations.append({
            "id": f"market:{market_context['id']}",
            "source": market_context["source"],
            "excerpt": f"{market_context['title']} — probability {market_context['probability']:.2f}, volume {market_context['volume']}",
        })

    # INSUFFICIENT CONTEXT: no unsupported answer is generated
    if len(citations) < MIN_RELEVANT_SOURCES:
        return jsonify({
            "answer": "I don't have enough relevant context to answer that confidently. Try asking about a specific market or a topic covered in our research notes.",
            "citations": [],
            "confidence": "Low",
            "insufficient_context": True,
        }), 200

    context_text = "\n".join([f"- {c['excerpt']}" for c in citations])
    prompt = (
        f"Answer the user's question using ONLY the following context. "
        f"If the context does not fully answer it, say so.\n\n"
        f"Context:\n{context_text}\n\nQuestion: {question}\nAnswer concisely."
    )

    answer = None
    try:
        resp = requests.post(
            f"{AI_MODE_URL}/ai/complete",
            json={"task": "Answer using the provided context only.", "context": prompt},
            timeout=60,
        )
        resp.raise_for_status()
        answer = resp.json().get("output", "").strip()
    except Exception:
        answer = None

    if not answer:
        answer = "AI-Mode is currently unavailable, so I can't generate a grounded answer right now. Here is the relevant context I found instead: " + context_text

    confidence = compute_confidence(passages, market_context)

    return jsonify({
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "insufficient_context": False,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)