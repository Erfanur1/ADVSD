"""
Human Review -- Release 2, Task 1 (shared Multi-Agent Server).

Persists Multi-Agent runs to a local JSON history file and applies a
human's final decision to a pending run. This is deliberately simple
file-based storage (matching the pattern already used by
ai-services/mcp-server/app.py for analysis_notes.json) -- no database,
since this is a local, non-containerised service.
"""
import os
import json
import datetime
import uuid

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "workflow_history.json")
LOG_DIR = os.path.join(os.path.dirname(__file__), "multi_agent_logs")

VALID_DECISIONS = {"approve", "correct", "partial", "reject"}


def _load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(history):
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def _write_evidence_log(run):
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"{run['run_id']}.json")
    with open(path, "w") as f:
        json.dump(run, f, indent=2)
    return path


def create_run(task_type, params, plan, worker_output, review_result):
    run = {
        "run_id": uuid.uuid4().hex[:12],
        "task_type": task_type,
        "params": params,
        "plan": plan,
        "worker_output": worker_output,
        "review": review_result,
        "status": "pending_human_review",
        "human_decision": None,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "decided_at": None,
    }
    history = _load_history()
    history.append(run)
    _save_history(history)
    run["_evidence_log_path"] = _write_evidence_log(run)
    return run


def get_run(run_id):
    for run in _load_history():
        if run["run_id"] == run_id:
            return run
    return None


def list_runs():
    return [
        {k: r[k] for k in ("run_id", "task_type", "status", "created_at", "decided_at")}
        for r in _load_history()
    ]


def apply_decision(run_id, decision, notes=None, corrected_output=None):
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(VALID_DECISIONS)}")

    history = _load_history()
    target = None
    for run in history:
        if run["run_id"] == run_id:
            target = run
            break
    if target is None:
        return None
    if target["status"] != "pending_human_review":
        raise ValueError(f"run '{run_id}' already decided (status={target['status']})")

    target["status"] = {
        "approve": "approved",
        "correct": "corrected",
        "partial": "partially_accepted",
        "reject": "rejected",
    }[decision]
    target["human_decision"] = {
        "decision": decision,
        "notes": notes,
        "corrected_output": corrected_output,
    }
    target["decided_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    _save_history(history)
    target["_evidence_log_path"] = _write_evidence_log(target)
    return target