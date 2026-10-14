"""
Shared Multi-Agent Server -- Release 2, Task 1.

Runs locally, NOT containerised (per spec). Coordinates a Planner,
Worker and Reviewer agent, with a mandatory Human Review step, for any
student feature's backend/API to call over local HTTP -- the same
pattern as the shared MCP and RAG servers from Release 1.

Run: python app.py   (listens on port 8300 by default)

Endpoints:
  GET  /health
  POST /multi-agent/run      -- Plan -> Act (Worker) -> Observe (Reviewer); returns a
                                 pending_human_review run record
  GET  /multi-agent/runs     -- list all runs (summary)
  GET  /multi-agent/runs/<id>-- full run record
  POST /multi-agent/review   -- submit the human decision for a pending run
"""
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import planner
import worker
import reviewer
import human_review

load_dotenv()

app = Flask(__name__)
PORT = int(os.getenv("MULTI_AGENT_PORT", "8300"))


@app.get("/health")
def health():
    return jsonify(status="ok", service="multi-agent-server", supported_task_types=planner.SUPPORTED_TASK_TYPES)


@app.post("/multi-agent/run")
def run_workflow():
    """
    Body: {"task_type": "validate_market_action", "params": {...}}
    Runs Planner -> Worker -> Reviewer, persists the run as
    pending_human_review, and returns the full run record (including
    run_id, needed to submit the human decision afterwards).
    """
    body = request.get_json(force=True) or {}
    task_type = body.get("task_type")
    params = body.get("params", {})

    # PLAN
    try:
        plan = planner.create_plan(task_type, params)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # ACT
    try:
        worker_output = worker.execute(plan, params)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # OBSERVE
    review_result = reviewer.review(plan, worker_output)

    # record (status becomes pending_human_review until /multi-agent/review is called)
    run = human_review.create_run(task_type, params, plan, worker_output, review_result)
    return jsonify(run), 201


@app.get("/multi-agent/runs")
def list_runs():
    return jsonify(human_review.list_runs())


@app.get("/multi-agent/runs/<run_id>")
def get_run(run_id):
    run = human_review.get_run(run_id)
    if run is None:
        return jsonify({"error": f"run '{run_id}' not found"}), 404
    return jsonify(run)


@app.post("/multi-agent/review")
def submit_human_decision():
    """
    ADAPT (human-in-the-loop): applies the final human decision to a
    pending run.
    Body: {"run_id": "...", "decision": "approve|correct|partial|reject",
           "notes": "..." (optional), "corrected_output": {...} (optional)}
    """
    body = request.get_json(force=True) or {}
    run_id = body.get("run_id")
    decision = body.get("decision")
    notes = body.get("notes")
    corrected_output = body.get("corrected_output")

    if not run_id or not decision:
        return jsonify({"error": "run_id and decision are required"}), 400

    try:
        updated = human_review.apply_decision(run_id, decision, notes=notes, corrected_output=corrected_output)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    if updated is None:
        return jsonify({"error": f"run '{run_id}' not found"}), 404
    return jsonify(updated)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)