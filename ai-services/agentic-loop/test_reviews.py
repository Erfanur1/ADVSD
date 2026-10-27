"""Tests for the Release 2 agentic-loop review modes (offline: no servers, Azure or GitHub needed)."""
import json

import reviews


def _run(rid, rec, decision=None, notes=None, status=None, steps=True, feature="portfolio"):
    run = {
        "run_id": rid, "task_type": "review_portfolio", "params": {"feature": feature},
        "plan": {"steps": ["s1"] if steps else []},
        "worker_output": {"evidence_gathered": ["e1", "e2"]},
        "review": {"recommendation": rec, "evidence_satisfied": not rec.startswith("reject_insufficient")},
        "status": status or ("pending_human_review" if decision is None else "decided"),
        "created_at": "2026-10-28T09:00:00", "decided_at": "2026-10-28T09:01:30" if decision else None,
        "human_decision": {"decision": decision, "notes": notes} if decision else None,
    }
    return run


# ---------------- multi-agent-review
def test_multi_agent_counts_cycles_agreement_and_latency():
    runs = [_run("a", "approve_with_caution", "partial", "trim BTC"),
            _run("b", "reject_invalid_positions", "reject", "bad price"),
            _run("c", "approve")]
    f = reviews.analyse_runs(runs)
    assert f["total_runs"] == 3 and f["completed_cycles"] == 2 and f["pending_human_review"] == 1
    assert f["human_agreed_with_reviewer"] == 2 and f["agreement_rate"] == 1.0
    assert f["avg_decision_seconds"] == 90.0
    verdict, recs = reviews.recommend_multi_agent(f)
    assert verdict == "pass"
    assert any("await a human decision" in r for r in recs)


def test_multi_agent_flags_incomplete_runs_and_unjustified_overrides():
    runs = [_run("x", "reject_invalid_positions", "approve"), _run("y", "approve", "approve", steps=False)]
    f = reviews.analyse_runs(runs)
    assert f["incomplete_runs"] == ["y: missing Planner steps"]
    assert f["unsupported_overrides"] and f["human_overrode_reviewer"] == 1
    verdict, _ = reviews.recommend_multi_agent(f)
    assert verdict == "attention"


def test_multi_agent_with_no_runs_fails():
    verdict, recs = reviews.recommend_multi_agent(reviews.analyse_runs([]))
    assert verdict == "fail" and "No Multi-Agent runs" in recs[0]


def test_multi_agent_falls_back_to_history_file(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews, "MULTI_AGENT_URL", "http://127.0.0.1:9")  # nothing listens here
    history = tmp_path / "workflow_history.json"
    history.write_text(json.dumps([_run("h", "approve", "approve")]))
    runs, source = reviews.load_runs(str(history))
    assert len(runs) == 1 and "history file" in source


# ---------------- testing-review
def _evidence(**over):
    e = {"ruff": {"status": "clean"}, "detect_secrets": {"status": "clean"},
         "pip_audit": {"backend": {"status": "clean", "vulnerabilities": 0}},
         "pytest": {"status": "passed", "tests": 10, "passed": 10, "failed": 0, "skipped": 0},
         "ci": {"status": "success"}}
    e.update(over)
    return e


def test_testing_all_clean_is_low_risk():
    overall, per, recs = reviews.assess_testing({"student-2": _evidence()})
    assert overall == "Low" and per["student-2"]["risk"] == "Low"
    assert "no action needed" in recs[0]


def test_testing_failing_tests_or_secret_is_high_risk():
    overall, per, recs = reviews.assess_testing({
        "student-1": _evidence(pytest={"status": "failed", "tests": 5, "passed": 3, "failed": 2, "skipped": 0}),
        "student-2": _evidence(detect_secrets={"status": "findings"}),
    })
    assert overall == "High"
    assert per["student-1"]["risk"] == per["student-2"]["risk"] == "High"
    assert any("failing tests" in r for r in recs) and any("rotate it" in r for r in recs)


def test_testing_cves_ruff_and_red_ci_are_reported():
    overall, per, recs = reviews.assess_testing({"student-4": _evidence(
        ruff={"status": "findings", "count": 3, "by_rule": {"S110": 3}},
        pip_audit={"backend": {"status": "findings", "vulnerabilities": 8}},
        ci={"status": "failure"})})
    assert overall == "High"  # red CI on main blocks deployment
    assert any("upgrade the vulnerable" in r for r in recs)
    assert any("blocks cloud-deployment.yml" in r for r in recs)


def test_ci_status_picks_latest_completed_run_on_main(monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {"workflow_runs": [
                {"head_branch": "feature", "status": "completed", "conclusion": "failure"},
                {"head_branch": "main", "status": "in_progress", "conclusion": None},
                {"head_branch": "main", "status": "completed", "conclusion": "success", "run_number": 17,
                 "head_sha": "f9187f2abc", "html_url": "https://github.com/x", "updated_at": "2026-10-22T10:00:00Z"},
            ]}

    monkeypatch.setattr(reviews.requests, "get", lambda *a, **k: Resp())
    ci = reviews._ci_status("student-2")
    assert ci == {"status": "success", "run_number": 17, "commit": "f9187f2", "url": "https://github.com/x",
                  "date": "2026-10-22"}


# ---------------- cloud-deployment-review
APPS = [
    {"name": "group29cc-home", "url": "https://home", "external": True, "status": "Running"},
    {"name": "student-2-frontend", "url": "https://s2", "external": True, "status": "Running"},
    {"name": "student-2-backend", "url": "https://s2b", "external": False, "status": "Running"},
]


def test_release_approve_when_everything_healthy():
    frontends = [{"app": "group29cc-home", "ok": True, "ms": 300}, {"app": "student-2-frontend", "ok": True, "ms": 400}]
    probes = [{"check": "Multi-Agent disabled in cloud", "ok": True}, {"check": "CRUD create (open position)", "ok": True}]
    assert reviews.recommend_release(APPS, frontends, probes) == ("approve", [])


def test_release_conditional_when_ai_apps_deployed_or_home_down():
    apps = APPS + [{"name": "group29cc-ai-mode", "url": None, "external": False, "status": "Running"}]
    frontends = [{"app": "group29cc-home", "ok": False, "ms": None}, {"app": "student-2-frontend", "ok": True, "ms": 400}]
    rec, risks = reviews.recommend_release(apps, frontends, [])
    assert rec == "conditional"
    assert any("AI service apps deployed" in r for r in risks) and any("Non-student" in r for r in risks)


def test_release_reject_when_student_frontend_down_or_crud_fails():
    frontends = [{"app": "student-2-frontend", "ok": False, "ms": None}]
    assert reviews.recommend_release(APPS, frontends, [])[0] == "reject"
    ok_fe = [{"app": "student-2-frontend", "ok": True, "ms": 200}]
    assert reviews.recommend_release(APPS, ok_fe, [{"check": "CRUD delete (close position)", "ok": False}])[0] == "reject"


def test_discover_cloud_maps_azure_cli_output(monkeypatch):
    monkeypatch.setattr(reviews, "_az_json", lambda args: [
        {"name": "student-2-frontend", "fqdn": "s2.eastasia.azurecontainerapps.io", "external": True, "status": "Running"},
        {"name": "student-2-backend", "fqdn": "s2b.internal", "external": False, "status": "Running"}])
    apps = reviews.discover_cloud("group29-r2-rg")
    assert apps[0]["url"] == "https://s2.eastasia.azurecontainerapps.io"
    assert [a["name"] for a in apps] == ["student-2-frontend", "student-2-backend"]
