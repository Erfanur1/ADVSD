"""
Planner Agent -- Release 2, Task 1 (shared Multi-Agent Server).

Given a task request, the Planner decides WHAT needs to be done and
WHAT EVIDENCE is required before the Worker acts. It does not call any
live services itself -- it only produces a plan dict.

Student backends submit a `task_type` plus `params`; this module turns
that into a concrete plan. "validate_market_action" is the one built-in
task type, usable by all four features (it only needs a market id and
an optional submitted value to check against the live price). Students
integrating their own feature (Individual Code Task A) are free to call
this task type as-is, or add a new one here if their feature needs a
different kind of plan -- see the README for how to add one.
"""

SUPPORTED_TASK_TYPES = ["validate_market_action"]


def create_plan(task_type, params):
    """
    Returns a plan dict: {task_type, steps: [str], required_evidence: [str]}
    or raises ValueError for an unknown task_type / missing required params.
    """
    if task_type == "validate_market_action":
        return _plan_validate_market_action(params)
    raise ValueError(
        f"unknown task_type '{task_type}'. Supported: {SUPPORTED_TASK_TYPES}"
    )


def _plan_validate_market_action(params):
    feature = params.get("feature", "unspecified-feature")
    market_id = params.get("market_id")
    source = params.get("source", "both")
    submitted_value = params.get("submitted_value")

    if not market_id:
        raise ValueError("params.market_id is required for validate_market_action")

    steps = [
        f"Fetch the current live price/probability for market '{market_id}' "
        f"(source={source}) via the shared MCP server, on behalf of the "
        f"'{feature}' feature.",
    ]
    required_evidence = [
        f"Live market snapshot for '{market_id}' from the MCP server's "
        "get_market_price tool.",
    ]

    if submitted_value is not None:
        steps.append(
            f"Compare the submitted value ({submitted_value}) against the live "
            "probability and flag any gap worth a human's attention."
        )
        required_evidence.append(
            "Numeric delta between submitted_value and the live probability."
        )

    return {
        "task_type": "validate_market_action",
        "feature": feature,
        "steps": steps,
        "required_evidence": required_evidence,
    }