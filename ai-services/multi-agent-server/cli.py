"""
Multi-Agent Server -- terminal entry point (Release 2, Task 1).

Runs one full Planner -> Worker -> Reviewer cycle directly in-process
(no need for app.py to be running) and then prompts for a human
decision right there in the terminal. This is the "callable from the
terminal" requirement -- the shared agentic loop's own
`--mode multi-agent-review` (a separate Release 2 task) calls the
HTTP API instead and reviews a run's evidence after the fact; this
script is for driving a run start-to-finish by hand.

Run:
  python cli.py --market-id 559651 --source polymarket --feature watchlist
  python cli.py --market-id 559651 --source polymarket --submitted-value 0.2 --feature watchlist --decision approve
"""
import argparse
import json

import planner
import worker
import reviewer
import human_review


def main():
    parser = argparse.ArgumentParser(description="Run one Multi-Agent (Planner/Worker/Reviewer/Human) cycle from the terminal.")
    parser.add_argument("--task-type", default="validate_market_action")
    parser.add_argument("--feature", default="watchlist", help="e.g. watchlist | portfolio | research-notes | market-analyst")
    parser.add_argument("--market-id", required=True)
    parser.add_argument("--source", default="both", choices=["polymarket", "kalshi", "both"])
    parser.add_argument("--submitted-value", type=float, default=None)
    parser.add_argument("--decision", choices=["approve", "correct", "partial", "reject"], default=None,
                         help="If omitted, you'll be prompted interactively.")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    params = {"feature": args.feature, "market_id": args.market_id, "source": args.source}
    if args.submitted_value is not None:
        params["submitted_value"] = args.submitted_value

    print("=== Multi-Agent Workflow: Planner -> Worker -> Reviewer -> Human Review ===\n")

    print("[Plan] Planner Agent is building the task plan and required evidence...")
    plan = planner.create_plan(args.task_type, params)
    for step in plan["steps"]:
        print(f"  - {step}")
    print()

    print("[Act] Worker Agent is executing the plan...")
    worker_output = worker.execute(plan, params)
    for item in worker_output["evidence_gathered"]:
        print(f"  - {item}")
    if worker_output["notes"]:
        print("  Notes:")
        for n in worker_output["notes"]:
            print(f"    - {n}")
    print()

    print("[Observe] Reviewer Agent is checking the Worker's output against the plan...")
    review_result = reviewer.review(plan, worker_output)
    print(f"  Recommendation: {review_result['recommendation']} (confidence: {review_result['confidence']})")
    if review_result["risks"]:
        print("  Risks flagged:")
        for r in review_result["risks"]:
            print(f"    - {r}")
    else:
        print("  No risks flagged.")
    print()

    run = human_review.create_run(args.task_type, params, plan, worker_output, review_result)
    print(f"Run saved as pending human review: run_id={run['run_id']}")
    print(f"Evidence log: {run['_evidence_log_path']}\n")

    decision = args.decision
    if decision is None:
        print("[Adapt] Human Review -- enter a decision for this run.")
        decision = input("  Decision (approve / correct / partial / reject): ").strip()
    notes = args.notes
    if notes is None and args.decision is None:
        notes = input("  Notes (optional, press enter to skip): ").strip() or None

    updated = human_review.apply_decision(run["run_id"], decision, notes=notes)
    print(f"\nFinal status: {updated['status']}")
    print("\n--- Full run record ---")
    print(json.dumps(updated, indent=2))


if __name__ == "__main__":
    main()