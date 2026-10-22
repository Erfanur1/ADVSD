"""
Reviewer Agent -- Release 2, Task 1 (shared Multi-Agent Server).

Checks the Worker's output against the Planner's plan and required
evidence, flags risks, and produces a recommendation for the human
reviewer. The Reviewer never has the final say -- per the Release 2
spec, every run still goes to Human Review -- but a clear
recommendation is what makes that review fast instead of a blind
rubber stamp.
"""

DRIFT_WARN_THRESHOLD = 0.05  # 5 probability points
CATEGORY_CONCENTRATION_LIMIT = 0.5  # Student 2: one category > 50% of total exposure
LARGE_GAP_WARN_THRESHOLD = 20.0  # Student 4: a gap this big is more likely a market-definition mismatch


def review(plan, worker_output):
    """
    Returns a review dict: {risks: [str], recommendation: str,
    confidence: "High"|"Medium"|"Low", evidence_satisfied: bool}
    """
    if plan.get("task_type") == "review_portfolio":
        return _review_portfolio(plan, worker_output)
    if plan.get("task_type") == "review_mispricing_analysis":
        return _review_mispricing_analysis(plan, worker_output)

    risks = []
    evidence_satisfied = True

    if not worker_output.get("mcp_reachable", False):
        risks.append("MCP server was unreachable, so no live price evidence was gathered.")
        evidence_satisfied = False

    delta = worker_output.get("delta")
    if delta is not None and delta >= DRIFT_WARN_THRESHOLD:
        risks.append(
            f"Submitted value drifted {delta:.2%} from the live market price "
            f"(threshold {DRIFT_WARN_THRESHOLD:.0%}) -- value may be stale or mistyped."
        )

    for note in worker_output.get("notes", []):
        risks.append(note)

    required = len(plan.get("required_evidence", []))
    gathered = len(worker_output.get("evidence_gathered", []))
    if required and gathered < required:
        risks.append(
            f"Only {gathered}/{required} pieces of required evidence were gathered."
        )
        evidence_satisfied = False

    if not evidence_satisfied:
        recommendation = "reject_insufficient_evidence"
        confidence = "Low"
    elif risks:
        recommendation = "approve_with_caution"
        confidence = "Medium"
    else:
        recommendation = "approve"
        confidence = "High"

    return {
        "risks": risks,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence_satisfied": evidence_satisfied,
    }


# ---------------- Student 4: AI Market Analyst Assistant ----------------
def _review_mispricing_analysis(plan, worker_output):
    risks = []
    comparison = worker_output.get("comparison")
    evidence_satisfied = worker_output.get("mcp_reachable", False) and comparison is not None

    for note in worker_output.get("notes", []):
        risks.append(note)
    if not evidence_satisfied:
        risks.append("MCP server was unreachable, so the comparison could not be re-checked live.")
        return {
            "risks": risks,
            "recommendation": "reject_insufficient_evidence",
            "confidence": "Low",
            "evidence_satisfied": False,
        }

    status = comparison["status"]
    if comparison["basis"].startswith("last-trade"):
        risks.append(
            "Based on last-trade prices, not a live order book (one side's book was incomplete) -- "
            "treat the gap as indicative only, not an executable price."
        )
    if comparison["abs_gap_points"] > LARGE_GAP_WARN_THRESHOLD:
        risks.append(
            f"Unusually large gap ({comparison['abs_gap_points']} pts, threshold {LARGE_GAP_WARN_THRESHOLD}) -- "
            "verify both markets resolve on the exact same event/terms before acting; large gaps are often "
            "a market-definition mismatch, not real mispricing."
        )

    if status == "fair":
        recommendation, confidence = "reject_not_actionable", "High"
    elif status == "mispriced" and not risks:
        recommendation, confidence = "approve", "High"
    else:
        recommendation, confidence = "approve_with_caution", "Medium"

    return {
        "risks": risks,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence_satisfied": evidence_satisfied,
    }


# ---------------- Student 2: Portfolio & Position Tracker ----------------
def _review_portfolio(plan, worker_output):
    risks = []
    validation = worker_output.get("validation")
    exposure = worker_output.get("exposure")

    for note in worker_output.get("notes", []):
        risks.append(note)

    required = len(plan.get("required_evidence", []))
    gathered = len(worker_output.get("evidence_gathered", []))
    evidence_satisfied = validation is not None and gathered >= required
    if gathered < required:
        risks.append(f"Only {gathered}/{required} pieces of required evidence were gathered.")

    errors = (validation or {}).get("errors", [])
    for err in errors:
        risks.append(f"Validation error: {err}")
    for warn in (validation or {}).get("warnings", []):
        risks.append(f"Validation warning: {warn}")

    top = ((exposure or {}).get("by_category") or [None])[0]
    if top and top.get("share", 0) > CATEGORY_CONCENTRATION_LIMIT:
        risks.append(
            f"{top['category']} is {top['share']:.0%} of total exposure "
            f"(limit {CATEGORY_CONCENTRATION_LIMIT:.0%}) -- consider diversifying."
        )

    if not evidence_satisfied:
        recommendation, confidence = "reject_insufficient_evidence", "Low"
    elif errors:
        recommendation, confidence = "reject_invalid_positions", "High"
    elif risks:
        recommendation, confidence = "approve_with_caution", "Medium"
    else:
        recommendation, confidence = "approve", "High"

    return {
        "risks": risks,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence_satisfied": evidence_satisfied,
    }
