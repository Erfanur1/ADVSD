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


def review(plan, worker_output):
    """
    Returns a review dict: {risks: [str], recommendation: str,
    confidence: "High"|"Medium"|"Low", evidence_satisfied: bool}
    """
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