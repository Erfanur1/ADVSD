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