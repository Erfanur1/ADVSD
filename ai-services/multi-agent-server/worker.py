"""
Worker Agent -- Release 2, Task 1 (shared Multi-Agent Server).

Executes the plan the Planner produced, using supplied application
evidence. For "validate_market_action" this means calling the shared
MCP server for a live market snapshot, then (if a submitted_value was
given) computing how far it has drifted from the live value.

The Worker never talks to the Reviewer or makes an approve/reject
call itself -- it only gathers evidence and reports what it found.
"""
import os
import requests

MCP_URL = os.getenv("MCP_URL", "http://localhost:8100")


def execute(plan, params):
    """
    Returns a worker_output dict: {evidence_gathered: [...], mcp_reachable: bool,
    live_market: dict|None, delta: float|None, notes: [str]}
    """
    if plan["task_type"] == "validate_market_action":
        return _execute_validate_market_action(params)
    if plan["task_type"] == "review_portfolio":
        return _execute_review_portfolio(plan)
    raise ValueError(f"Worker has no executor for task_type '{plan['task_type']}'")


def _execute_validate_market_action(params):
    market_id = params.get("market_id")
    source = params.get("source", "both")
    submitted_value = params.get("submitted_value")

    evidence_gathered = []
    notes = []
    mcp_reachable = True
    live_market = None

    try:
        resp = requests.post(
            f"{MCP_URL}/mcp/call",
            json={"tool": "get_market_price", "params": {"market_id": market_id, "source": source}},
            timeout=15,
        )
        body = resp.json()
        if resp.status_code == 200 and "result" in body:
            live_market = body["result"]
            evidence_gathered.append(
                f"MCP get_market_price returned probability={live_market.get('probability')} "
                f"for '{market_id}' (source={live_market.get('source')})."
            )
        else:
            mcp_reachable = False
            notes.append(f"MCP server responded but with no usable result: {body}")
    except Exception as exc:
        mcp_reachable = False
        notes.append(f"MCP server unreachable: {exc}")

    delta = None
    if live_market is not None and submitted_value is not None:
        try:
            delta = round(abs(float(submitted_value) - float(live_market["probability"])), 4)
            evidence_gathered.append(
                f"Computed delta between submitted_value ({submitted_value}) and live "
                f"probability ({live_market['probability']}): {delta}."
            )
        except (TypeError, ValueError, KeyError) as exc:
            notes.append(f"Could not compute delta: {exc}")

    return {
        "evidence_gathered": evidence_gathered,
        "mcp_reachable": mcp_reachable,
        "live_market": live_market,
        "delta": delta,
        "notes": notes,
    }


# ---------------- Student 2: Portfolio & Position Tracker ----------------
def _call_mcp(tool, params):
    """Returns (result | None, note | None). Read-only MCP tools only."""
    try:
        resp = requests.post(f"{MCP_URL}/mcp/call", json={"tool": tool, "params": params}, timeout=15)
        body = resp.json()
    except Exception as exc:
        return None, f"MCP server unreachable for {tool}: {exc}"
    if resp.status_code == 200 and "result" in body:
        return body["result"], None
    return None, f"MCP {tool} returned no usable result: {body.get('error', body)}"


def _execute_review_portfolio(plan):
    portfolio_id = plan["portfolio_id"]
    evidence_gathered, notes = [], []

    validation, note = _call_mcp("validate_portfolio", {"portfolio_id": portfolio_id})
    if note:
        notes.append(note)
    else:
        totals = validation.get("totals", {})
        evidence_gathered.append(
            f"validate_portfolio: valid={validation.get('valid')}, "
            f"{validation.get('positions_checked')} positions, "
            f"{len(validation.get('errors', []))} errors, {len(validation.get('warnings', []))} warnings, "
            f"cost basis ${totals.get('cost_basis')}, max loss ${totals.get('max_loss')}."
        )

    exposure, note = _call_mcp("get_exposure_summary", {})
    if note:
        notes.append(note)
    else:
        top = (exposure.get("by_category") or [{}])[0]
        evidence_gathered.append(
            f"get_exposure_summary: total ${exposure.get('total_exposure')}, largest category "
            f"{top.get('category')} at {top.get('share', 0):.0%}."
        )

    return {
        "evidence_gathered": evidence_gathered,
        "mcp_reachable": validation is not None or exposure is not None,
        "validation": validation,
        "exposure": exposure,
        "notes": notes,
    }
