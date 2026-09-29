"""
Shared MCP (Model Context Protocol) Server -- Release 1, Task 2.

Runs locally, NOT containerised (per spec). Exposes a small set of
registered tools that every student feature's backend/API can call
over local HTTP.

Run: python app.py   (listens on port 8100 by default)
"""
import os
import sys
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

# import the shared live-data layer (Task 1)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import market_data  # noqa: E402

app = Flask(__name__)
PORT = int(os.getenv("MCP_PORT", "8100"))

NOTES_LOG_PATH = os.path.join(os.path.dirname(__file__), "analysis_notes.json")


# ---------------- Tool registry ----------------
# Each tool has: a name, an input schema (for validation/documentation),
# and a handler function that returns a structured (dict) result.

def tool_get_market_price(params):
    market_id = params.get("market_id")
    source = params.get("source", "both")
    if not market_id:
        return {"error": "market_id is required"}, 400
    market, meta = market_data.get_market_by_id(market_id, source=source)
    if not market:
        return {"error": f"market_id '{market_id}' not found", "meta": meta}, 404
    return {"result": market, "meta": meta}, 200


def tool_search_markets(params):
    query = params.get("query")
    category = params.get("category")
    source = params.get("source", "both")
    markets, meta = market_data.fetch_markets(source=source, query=query, category=category, limit=10)
    return {"result": markets, "meta": meta}, 200


def tool_get_market_history(params):
    # Neither Polymarket's nor Manifold's free-tier endpoints reliably
    # expose full history without extra calls; this tool returns the
    # current snapshot as a single-point "history" for now, with a
    # clear note, rather than fabricating data.
    market_id = params.get("market_id")
    source = params.get("source", "both")
    if not market_id:
        return {"error": "market_id is required"}, 400
    market, meta = market_data.get_market_by_id(market_id, source=source)
    if not market:
        return {"error": f"market_id '{market_id}' not found", "meta": meta}, 404
    return {
        "result": {
            "market_id": market_id,
            "points": [{"probability": market["probability"], "as_of": "latest"}],
            "note": "Only the latest snapshot is available; full historical series is a Release 2 stretch goal.",
        },
        "meta": meta,
    }, 200


def tool_log_analysis_note(params):
    market_id = params.get("market_id")
    note_text = params.get("note_text")
    if not market_id or not note_text:
        return {"error": "market_id and note_text are required"}, 400
    notes = []
    if os.path.exists(NOTES_LOG_PATH):
        try:
            with open(NOTES_LOG_PATH, "r") as f:
                notes = json.load(f)
        except (json.JSONDecodeError, OSError):
            notes = []
    entry = {"market_id": market_id, "note_text": note_text}
    notes.append(entry)
    try:
        with open(NOTES_LOG_PATH, "w") as f:
            json.dump(notes, f, indent=2)
    except OSError:
        return {"error": "failed to persist note"}, 500
    return {"result": {"saved": True, "entry": entry, "total_notes": len(notes)}}, 201


# ---------------- Student 2: Portfolio & Position Tracker tools ----------------
# Boundary: READ-ONLY. These tools only issue GET requests to the student-2
# backend's published port; they never write to the portfolio database.
PORTFOLIO_API_URL = os.getenv("PORTFOLIO_API_URL", "http://localhost:5002")
CONCENTRATION_LIMIT = 0.5  # warn if one position is >50% of a portfolio's cost


def _portfolio_get(path, **query):
    resp = requests.get(f"{PORTFOLIO_API_URL}{path}", params=query, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _cost(p):
    return p["entry_price"] * p["size"]


def tool_validate_portfolio(params):
    try:
        portfolio_id = int(params.get("portfolio_id"))
    except (TypeError, ValueError):
        return {"error": "portfolio_id must be an integer"}, 400
    if not 1 <= portfolio_id <= 100000:
        return {"error": "portfolio_id must be between 1 and 100000"}, 400
    try:
        positions = _portfolio_get("/positions", portfolio_id=portfolio_id)
    except requests.RequestException as exc:
        return {"error": f"portfolio service unavailable: {exc}"}, 502

    errors, warnings, seen = [], [], set()
    for p in positions:
        tag = f"#{p['id']} {p['market_ticker']}"
        if not 0 < p["entry_price"] < 1:
            errors.append(f"{tag}: entry price {p['entry_price']} must be between 0 and 1")
        if p["size"] <= 0:
            errors.append(f"{tag}: size must be positive")
        if p["side"] not in ("YES", "NO"):
            errors.append(f"{tag}: side must be YES or NO")
        key = (p["market_ticker"], p["side"])
        if key in seen:
            warnings.append(f"{tag}: duplicate {p['side']} position on the same market")
        if (p["market_ticker"], "NO" if p["side"] == "YES" else "YES") in seen:
            warnings.append(f"{tag}: holds both YES and NO on this market (self-hedged)")
        seen.add(key)

    cost_basis = sum(_cost(p) for p in positions)
    max_payout = sum(p["size"] for p in positions)  # each contract pays $1
    if cost_basis > 0:
        for p in positions:
            share = _cost(p) / cost_basis
            if share > CONCENTRATION_LIMIT:
                warnings.append(f"#{p['id']} {p['market_ticker']}: {share:.0%} of portfolio cost "
                                f"(limit {CONCENTRATION_LIMIT:.0%})")

    return {"result": {
        "portfolio_id": portfolio_id,
        "valid": not errors,
        "positions_checked": len(positions),
        "errors": errors,
        "warnings": warnings,
        "totals": {
            "cost_basis": round(cost_basis, 2),
            "max_payout": round(max_payout, 2),
            "max_loss": round(cost_basis, 2),
            "max_profit": round(max_payout - cost_basis, 2),
        },
    }}, 200


def tool_get_exposure_summary(params):
    try:
        positions = _portfolio_get("/positions")
    except requests.RequestException as exc:
        return {"error": f"portfolio service unavailable: {exc}"}, 502
    by_cat = {}
    for p in positions:
        cat = p["market_ticker"].split("-")[0]
        by_cat[cat] = by_cat.get(cat, 0) + _cost(p)
    total = sum(by_cat.values())
    return {"result": {
        "total_exposure": round(total, 2),
        "by_category": [
            {"category": c, "exposure": round(v, 2), "share": round(v / total, 3) if total else 0}
            for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
    }}, 200


TOOLS = {
    "get_market_price": {
        "handler": tool_get_market_price,
        "input_schema": {"market_id": "string (required)", "source": "polymarket|manifold|both (optional)"},
    },
    "search_markets": {
        "handler": tool_search_markets,
        "input_schema": {"query": "string (optional)", "category": "string (optional)", "source": "polymarket|manifold|both (optional)"},
    },
    "get_market_history": {
        "handler": tool_get_market_history,
        "input_schema": {"market_id": "string (required)", "source": "polymarket|manifold|both (optional)"},
    },
    "log_analysis_note": {
        "handler": tool_log_analysis_note,
        "input_schema": {"market_id": "string (required)", "note_text": "string (required)"},
    },
    # Student 2 -- Portfolio & Position Tracker
    "validate_portfolio": {
        "handler": tool_validate_portfolio,
        "input_schema": {"portfolio_id": "integer (required)"},
    },
    "get_exposure_summary": {
        "handler": tool_get_exposure_summary,
        "input_schema": {},
    },
}


@app.get("/health")
def health():
    return {"status": "ok", "service": "mcp-server", "tools_registered": list(TOOLS.keys())}


@app.get("/mcp/tools")
def list_tools():
    """Returns the registered tool catalogue (name + input schema) for discovery."""
    return jsonify({
        name: {"input_schema": t["input_schema"]}
        for name, t in TOOLS.items()
    })


@app.post("/mcp/call")
def call_tool():
    """
    Body: {"tool": "<tool name>", "params": {...}}
    Returns a structured result, or a structured error if the tool
    or its parameters are invalid (enforces tool boundaries).
    """
    body = request.get_json(force=True) or {}
    tool_name = body.get("tool")
    params = body.get("params", {})

    if tool_name not in TOOLS:
        return jsonify({"error": f"unknown tool '{tool_name}'", "available_tools": list(TOOLS.keys())}), 400

    handler = TOOLS[tool_name]["handler"]
    result, status_code = handler(params)
    result["tool"] = tool_name
    return jsonify(result), status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)