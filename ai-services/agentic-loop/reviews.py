"""
Release 2 review modes for the shared agentic loop.

Three modes, each following the Plan -> Act -> Observe -> Adapt structure
used by the Release 1 MCP/RAG validation modes:

  multi-agent-review       reviews the Multi-Agent Server's workflow history
                           (Planner -> Worker -> Reviewer -> Human Review)
  testing-review           reviews pre-commit security scan results and
                           post-commit CI/CD endpoint test results
  cloud-deployment-review  reviews the Azure deployment and records the
                           final human release decision

Every mode prints its trace to the terminal and writes two evidence files
to docs/release-2/review-logs/ (committed, unlike validation_logs/):
  <mode>_<timestamp>.json   full trace, inputs, findings and verdict
  <mode>_<timestamp>.md     human-readable report for the technical report

Runs locally, NOT containerised.
"""
import datetime
import json
import os
import shutil
import subprocess  # noqa: S404 -- fixed, hardcoded tool commands only (see _run)
import sys
import tempfile
import xml.etree.ElementTree as ET  # noqa: S405 -- parses our own pytest JUnit output only

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REVIEW_LOG_DIR = os.path.join(REPO_ROOT, "docs", "release-2", "review-logs")

MULTI_AGENT_URL = os.getenv("MULTI_AGENT_URL", "http://localhost:8300")
DEFAULT_HISTORY = os.path.join(REPO_ROOT, "ai-services", "multi-agent-server", "workflow_history.json")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Erfanur1/ADVSD")
STUDENTS = ["student-1", "student-2", "student-3", "student-4"]
AI_APP_MARKERS = ("ai-mode", "aimode", "ollama", "mcp", "rag", "multi-agent")

# How each Multi-Agent reviewer recommendation is expected to be resolved by a human.
APPROVE_RECS = {"approve", "approve_with_caution"}
REJECT_RECS = {"reject_insufficient_evidence", "reject_invalid_positions"}


# ---------------------------------------------------------------- shared helpers
class Trace:
    """Collects Plan/Act/Observe/Adapt stages and prints them as they happen."""

    def __init__(self, title):
        self.stages = []
        print(f"=== Agentic Loop: {title} ===")

    def add(self, stage, detail):
        self.stages.append({"stage": stage, "detail": detail})
        print(f"  [{stage}] {detail}")


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def save_review(mode, trace, result, markdown):
    """Write the JSON log and Markdown report; return their paths."""
    os.makedirs(REVIEW_LOG_DIR, exist_ok=True)
    ts = _timestamp()
    json_path = os.path.join(REVIEW_LOG_DIR, f"{mode}_{ts}.json")
    md_path = os.path.join(REVIEW_LOG_DIR, f"{mode}_{ts}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"mode": mode, "timestamp": ts, "trace": trace.stages, "result": result}, f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"\n[saved validation log: {os.path.relpath(json_path, REPO_ROOT)}]")
    print(f"[saved review report:  {os.path.relpath(md_path, REPO_ROOT)}]")
    return json_path, md_path


def _run(args, cwd=None, env=None, timeout=300):
    """Run a fixed developer-tool command. Returns (exit_code, combined_output).
    exit_code is None when the tool is missing or timed out."""
    try:
        proc = subprocess.run(  # noqa: S603 -- args are hardcoded tool invocations, never user input
            args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return None, f"tool not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s: {' '.join(args[:4])}"


def _parse_time(value):
    try:
        return datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _bullets(items, empty="None."):
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


def _trace_md(trace):
    return "\n".join(f"| {s['stage']} | {s['detail']} |" for s in trace.stages)


# ================================================================ 1. MULTI-AGENT REVIEW
def load_runs(history_path=None):
    """Full run records: from the live Multi-Agent Server, else its history file."""
    try:
        summary = requests.get(f"{MULTI_AGENT_URL}/multi-agent/runs", timeout=10).json()
        runs = []
        for s in summary:
            r = requests.get(f"{MULTI_AGENT_URL}/multi-agent/runs/{s['run_id']}", timeout=10)
            if r.status_code == 200:
                runs.append(r.json())
        return runs, f"Multi-Agent Server at {MULTI_AGENT_URL}"
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    path = history_path or DEFAULT_HISTORY
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f), f"history file {os.path.relpath(path, REPO_ROOT)}"
    return [], "no source available (server unreachable and no history file)"


def analyse_runs(runs):
    """Pure analysis of Multi-Agent run records -> findings dict."""
    by_status, by_task, by_feature = {}, {}, {}
    incomplete, unsupported_overrides, missing_notes = [], [], []
    agreements = overrides = 0
    latencies = []
    weak_evidence = 0

    for run in runs:
        rid = run.get("run_id", "?")
        status = run.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_task[run.get("task_type", "?")] = by_task.get(run.get("task_type", "?"), 0) + 1
        feature = (run.get("params") or {}).get("feature") or (run.get("plan") or {}).get("feature") or "?"
        by_feature[feature] = by_feature.get(feature, 0) + 1

        plan, worker, review = run.get("plan") or {}, run.get("worker_output") or {}, run.get("review") or {}
        missing = [name for name, ok in (
            ("Planner steps", bool(plan.get("steps"))),
            ("Worker evidence", "evidence_gathered" in worker),
            ("Reviewer recommendation", bool(review.get("recommendation"))),
        ) if not ok]
        if missing:
            incomplete.append(f"{rid}: missing {', '.join(missing)}")
        if review and not review.get("evidence_satisfied", True):
            weak_evidence += 1

        decision = (run.get("human_decision") or {}).get("decision")
        if not decision:
            continue
        rec = review.get("recommendation")
        if (rec in APPROVE_RECS and decision in ("approve", "partial")) or (rec in REJECT_RECS and decision == "reject"):
            agreements += 1
        else:
            overrides += 1
            if rec in REJECT_RECS and decision == "approve" and not (run.get("human_decision") or {}).get("notes"):
                unsupported_overrides.append(f"{rid}: approved despite '{rec}' with no justification")
        if decision in ("correct", "partial", "reject") and not (run.get("human_decision") or {}).get("notes"):
            missing_notes.append(f"{rid}: '{decision}' recorded without notes")
        created, decided = _parse_time(run.get("created_at")), _parse_time(run.get("decided_at"))
        if created and decided:
            latencies.append((decided - created).total_seconds())

    decided_count = agreements + overrides
    return {
        "total_runs": len(runs),
        "by_status": by_status,
        "by_task_type": by_task,
        "by_feature": by_feature,
        "completed_cycles": decided_count,
        "pending_human_review": by_status.get("pending_human_review", 0),
        "incomplete_runs": incomplete,
        "runs_with_insufficient_evidence": weak_evidence,
        "human_agreed_with_reviewer": agreements,
        "human_overrode_reviewer": overrides,
        "agreement_rate": round(agreements / decided_count, 2) if decided_count else None,
        "unsupported_overrides": unsupported_overrides,
        "decisions_missing_notes": missing_notes,
        "avg_decision_seconds": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }


def recommend_multi_agent(f):
    recs, verdict = [], "pass"
    if f["total_runs"] == 0:
        return "fail", ["No Multi-Agent runs found: run at least one workflow from a frontend or cli.py."]
    if f["completed_cycles"] == 0:
        verdict = "attention"
        recs.append("No run has a human decision yet: complete at least one Planner -> Worker -> Reviewer -> Human cycle.")
    if f["incomplete_runs"]:
        verdict = "attention"
        recs.append(f"{len(f['incomplete_runs'])} run(s) are missing an agent stage: check the Planner/Worker/Reviewer pipeline.")
    if f["pending_human_review"]:
        recs.append(f"{f['pending_human_review']} run(s) still await a human decision: decide or reject them.")
    if f["runs_with_insufficient_evidence"]:
        recs.append(f"{f['runs_with_insufficient_evidence']} run(s) had insufficient evidence: "
                    "usually the MCP server or the feature backend was down during the run.")
    if f["unsupported_overrides"]:
        verdict = "attention"
        recs.append("Humans approved Reviewer rejections without notes: require a justification for overrides.")
    if f["decisions_missing_notes"]:
        recs.append("Some correct/partial/reject decisions have no notes: add notes so the audit trail explains them.")
    if len(f["by_task_type"]) < 2:
        recs.append("Only one task type has been exercised: run other features' task types to show cross-feature use.")
    if not recs:
        recs.append("Workflow history is complete and consistent; no action needed.")
    return verdict, recs


def run_multi_agent_review(history_path=None):
    t = Trace("Multi-Agent Workflow Review Mode")
    t.add("Plan", "Review the Multi-Agent Server's workflow history: every run must show Planner, Worker and "
                  "Reviewer stages and a recorded human decision.")
    runs, source = load_runs(history_path)
    t.add("Act", f"Loaded {len(runs)} run record(s) from {source}.")
    f = analyse_runs(runs)
    t.add("Observe", f"{f['completed_cycles']} completed cycle(s), {f['pending_human_review']} pending, "
                     f"{len(f['incomplete_runs'])} incomplete; human agreed with the Reviewer in "
                     f"{f['human_agreed_with_reviewer']} of {f['completed_cycles']} decision(s).")
    verdict, recs = recommend_multi_agent(f)
    t.add("Adapt", f"Verdict: {verdict.upper()}. {len(recs)} recommendation(s) produced.")

    for r in recs:
        print(f"    - {r}")
    result = {"source": source, "findings": f, "verdict": verdict, "recommendations": recs}
    md = f"""# Multi-Agent Workflow Review

**Verdict:** {verdict.upper()} · **Source:** {source} · **Generated:** {datetime.datetime.now():%Y-%m-%d %H:%M}

| Stage | Detail |
| --- | --- |
{_trace_md(t)}

## Findings

| Measure | Value |
| --- | --- |
| Total runs | {f['total_runs']} |
| Completed cycles (human decided) | {f['completed_cycles']} |
| Pending human review | {f['pending_human_review']} |
| Runs by status | {', '.join(f'{k}: {v}' for k, v in f['by_status'].items()) or '-'} |
| Runs by task type | {', '.join(f'{k}: {v}' for k, v in f['by_task_type'].items()) or '-'} |
| Runs by feature | {', '.join(f'{k}: {v}' for k, v in f['by_feature'].items()) or '-'} |
| Human agreed with Reviewer | {f['human_agreed_with_reviewer']} (rate {f['agreement_rate']}) |
| Human overrode Reviewer | {f['human_overrode_reviewer']} |
| Runs with insufficient evidence | {f['runs_with_insufficient_evidence']} |
| Average time to human decision | {f['avg_decision_seconds']} s |

**Incomplete runs**
{_bullets(f['incomplete_runs'])}

**Unsupported overrides**
{_bullets(f['unsupported_overrides'])}

## Recommendations
{_bullets(recs)}
"""
    save_review("multi-agent-review", t, result, md)
    return verdict != "fail"


# ================================================================ 2. TESTING REVIEW
def _ruff(student):
    paths = [p for p in (os.path.join(student, "backend"), os.path.join(student, "frontend"))
             if os.path.isdir(os.path.join(REPO_ROOT, p))]
    code, out = _run([sys.executable, "-m", "ruff", "check", "--select=S", "--output-format=json", *paths], cwd=REPO_ROOT)
    if code is None:
        return {"status": "unavailable", "detail": out}
    try:
        items = json.loads(out[out.index("["):]) if "[" in out else []
    except ValueError:
        return {"status": "unavailable", "detail": out[:300]}
    rules = {}
    for i in items:
        rules[i.get("code")] = rules.get(i.get("code"), 0) + 1
    return {"status": "clean" if not items else "findings", "count": len(items), "by_rule": rules}


def _detect_secrets(student):
    code, out = _run(["git", "ls-files", student], cwd=REPO_ROOT)
    files = [f for f in out.splitlines() if f.strip()] if code == 0 else []
    if not files:
        return {"status": "unavailable", "detail": "no tracked files found (run from a git checkout)"}
    code, out = _run([sys.executable, "-m", "detect_secrets.pre_commit_hook", "--baseline", ".secrets.baseline", *files],
                     cwd=REPO_ROOT)
    if code is None:
        return {"status": "unavailable", "detail": out}
    return {"status": "clean" if code == 0 else "findings", "files_scanned": len(files),
            "detail": "" if code == 0 else out.strip()[:500]}


def _pip_audit(student):
    results = {}
    for part in ("backend", "frontend"):
        req = os.path.join(REPO_ROOT, student, part, "requirements.txt")
        if not os.path.exists(req):
            continue
        code, out = _run([sys.executable, "-m", "pip_audit", "-r", req, "--progress-spinner", "off"], timeout=240)
        if code is None:
            results[part] = {"status": "unavailable", "detail": out}
        elif code == 0:
            results[part] = {"status": "clean", "vulnerabilities": 0}
        else:
            vulns = [ln for ln in out.splitlines() if " PYSEC-" in ln or " GHSA-" in ln or " CVE-" in ln]
            results[part] = {"status": "findings" if vulns else "unavailable",
                             "vulnerabilities": len(vulns), "detail": out.strip()[-500:]}
    return results


def _pytest(student):
    cwd = os.path.join(REPO_ROOT, student)
    if not os.path.isdir(os.path.join(cwd, "tests")):
        return {"status": "unavailable", "detail": "no tests/ folder"}
    env = dict(os.environ, MCP_ENABLED="false", RAG_ENABLED="false", MULTI_AGENT_ENABLED="false")
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = os.path.join(tmp, "junit.xml")
        code, out = _run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider",
                          f"--junitxml={xml_path}"], cwd=cwd, env=env, timeout=600)
        if code is None or not os.path.exists(xml_path):
            return {"status": "unavailable", "detail": out.strip()[-500:]}
        root = ET.parse(xml_path).getroot()  # noqa: S314 -- our own pytest output
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    tests, failures = int(suite.get("tests", 0)), int(suite.get("failures", 0))
    errors, skipped = int(suite.get("errors", 0)), int(suite.get("skipped", 0))
    passed = tests - failures - errors - skipped
    return {"status": "passed" if failures + errors == 0 else "failed", "tests": tests, "passed": passed,
            "failed": failures + errors, "skipped": skipped}


def _ci_status(student):
    """Latest completed student-x.yml run on main, from GitHub's public API."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{student}.yml/runs?per_page=30"
    try:
        resp = requests.get(url, timeout=15, headers={"Accept": "application/vnd.github+json"})
        runs = resp.json().get("workflow_runs", []) if resp.status_code == 200 else None
    except (requests.RequestException, ValueError):
        runs = None
    if runs is None:
        return {"status": "unavailable", "detail": "GitHub API unreachable or rate-limited"}
    for r in runs:
        if r.get("head_branch") == "main" and r.get("status") == "completed":
            return {"status": r.get("conclusion"), "run_number": r.get("run_number"),
                    "commit": (r.get("head_sha") or "")[:7], "url": r.get("html_url"),
                    "date": (r.get("updated_at") or "")[:10]}
    return {"status": "none", "detail": "no completed run on main"}


def collect_testing_evidence(students, skip_audit=False, skip_ci=False):
    evidence = {}
    for s in students:
        print(f"    ... scanning {s}")
        evidence[s] = {
            "ruff": _ruff(s),
            "detect_secrets": _detect_secrets(s),
            "pip_audit": {"skipped": True} if skip_audit else _pip_audit(s),
            "pytest": _pytest(s),
            "ci": {"status": "skipped"} if skip_ci else _ci_status(s),
        }
    return evidence


def assess_testing(evidence):
    """Pure risk assessment over collected evidence -> (overall_risk, per_student, recommendations)."""
    order = {"Low": 0, "Medium": 1, "High": 2}
    per_student, recs = {}, []
    for s, e in evidence.items():
        risk, notes = "Low", []

        def bump(level, note):
            nonlocal risk
            if order[level] > order[risk]:
                risk = level
            notes.append(note)

        if e["pytest"].get("status") == "failed":
            bump("High", f"{e['pytest']['failed']} local test(s) failing")
        elif e["pytest"].get("status") == "unavailable":
            bump("Medium", "local tests could not run")
        if e["ci"].get("status") not in ("success", "skipped"):
            bump("High" if e["ci"].get("status") == "failure" else "Medium",
                 f"CI on main: {e['ci'].get('status')}")
        if e["detect_secrets"].get("status") == "findings":
            bump("High", "possible secret committed")
        if e["ruff"].get("status") == "findings":
            bump("Medium", f"{e['ruff']['count']} Ruff security finding(s) {e['ruff']['by_rule']}")
        for part, a in (e["pip_audit"] or {}).items():
            if isinstance(a, dict) and a.get("status") == "findings":
                bump("Medium", f"{a['vulnerabilities']} dependency vulnerability finding(s) in {part}")
        per_student[s] = {"risk": risk, "notes": notes}

        if e["pytest"].get("status") == "failed":
            recs.append(f"{s}: fix the failing tests before the next deployment.")
        if e["ci"].get("status") == "failure":
            recs.append(f"{s}: student-x.yml is red on main, which also blocks cloud-deployment.yml.")
        if e["detect_secrets"].get("status") == "findings":
            recs.append(f"{s}: remove the flagged secret and rotate it; add a baseline entry only if it is a false positive.")
        if any(isinstance(a, dict) and a.get("status") == "findings" for a in (e["pip_audit"] or {}).values()):
            recs.append(f"{s}: upgrade the vulnerable pinned dependencies (pip-audit lists fixed versions).")
        if e["ruff"].get("status") == "findings":
            recs.append(f"{s}: resolve Ruff security findings or document them with a justified noqa.")
    overall = max((v["risk"] for v in per_student.values()), key=lambda r: order[r], default="Low")
    if not recs:
        recs.append("All scans clean and all tests passing; no action needed.")
    return overall, per_student, recs


def _cell_ruff(r):
    return r.get("status") if r.get("status") != "findings" else f"{r['count']} ({', '.join(r['by_rule'])})"


def _cell_audit(a):
    if a.get("skipped"):
        return "skipped"
    return ", ".join(f"{p}: {v.get('status')}" + (f" ({v.get('vulnerabilities')})" if v.get("status") == "findings" else "")
                     for p, v in a.items()) or "-"


def _cell_tests(p):
    return f"{p.get('passed')}/{p.get('tests')} passed" if "tests" in p else p.get("status")


def _cell_ci(c):
    if c.get("run_number"):
        return f"{c['status']} (#{c['run_number']}, {c['commit']})"
    return c.get("status")


def run_testing_review(students=None, skip_audit=False, skip_ci=False):
    students = students or STUDENTS
    t = Trace("Testing Report Review Mode")
    t.add("Plan", f"Review pre-commit security evidence (Ruff S rules, detect-secrets, pip-audit) and post-commit "
                  f"test evidence (pytest + latest student-x.yml run on main) for {', '.join(students)}.")
    t.add("Act", "Running the scans and test suites locally and reading CI status from GitHub Actions.")
    evidence = collect_testing_evidence(students, skip_audit=skip_audit, skip_ci=skip_ci)
    overall, per_student, recs = assess_testing(evidence)
    t.add("Observe", "; ".join(f"{s}: {v['risk']} risk" for s, v in per_student.items()))
    t.add("Adapt", f"Overall risk {overall}. {len(recs)} recommendation(s) produced.")
    for r in recs:
        print(f"    - {r}")

    rows = "\n".join(
        f"| {s} | {_cell_ruff(e['ruff'])} | {e['detect_secrets'].get('status')} | {_cell_audit(e['pip_audit'])} | "
        f"{_cell_tests(e['pytest'])} | {_cell_ci(e['ci'])} | {per_student[s]['risk']} |"
        for s, e in evidence.items())
    md = f"""# Testing Report Review

**Overall risk:** {overall} · **Generated:** {datetime.datetime.now():%Y-%m-%d %H:%M}

| Stage | Detail |
| --- | --- |
{_trace_md(t)}

## Evidence by student

| Student | Ruff (S rules) | detect-secrets | pip-audit | Local pytest | CI on main | Risk |
| --- | --- | --- | --- | --- | --- | --- |
{rows}

## Risk notes
{chr(10).join(f"- **{s}:** {'; '.join(v['notes']) or 'no issues'}" for s, v in per_student.items())}

## Recommendations
{_bullets(recs)}
"""
    result = {"evidence": evidence, "overall_risk": overall, "per_student": per_student, "recommendations": recs}
    save_review("testing-review", t, result, md)
    return overall != "High"


# ================================================================ 3. CLOUD DEPLOYMENT REVIEW
def _az_json(args):
    # On Windows the Azure CLI is az.cmd, which subprocess can't find by the bare
    # name "az", so resolve the full path first.
    az = shutil.which("az")
    if not az:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 -- fixed Azure CLI query, never user input
            [az, *args, "-o", "json"], capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        print(f"  (az failed: {(proc.stderr or '').strip()[:200]})")
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None

def discover_cloud(resource_group):
    """Container App inventory from Azure CLI -> list of {name, url, status}."""
    apps = _az_json(["containerapp", "list", "-g", resource_group,
                     "--query", "[].{name:name, fqdn:properties.configuration.ingress.fqdn, "
                                "external:properties.configuration.ingress.external, "
                                "status:properties.runningStatus}"])
    if apps is None:
        return None
    return [{"name": a["name"], "url": f"https://{a['fqdn']}" if a.get("fqdn") else None,
             "external": a.get("external"), "status": a.get("status")} for a in apps]


def _http(method, url, **kw):
    start = datetime.datetime.now()
    try:
        r = requests.request(method, url, timeout=30, **kw)
        ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        return r.status_code, ms, r.text
    except requests.RequestException as exc:
        return None, None, str(exc)


def check_frontends(apps):
    checks = []
    for a in apps:
        if not a.get("url") or a.get("external") is False or "backend" in a["name"]:
            continue
        code, ms, _ = _http("GET", a["url"] + "/")
        checks.append({"app": a["name"], "url": a["url"], "http_status": code, "ms": ms,
                       "ok": code is not None and code < 400})
    return checks


def check_ai_disabled_behaviour(student2_url):
    """Student 2's AI-backed routes must fall back cleanly when the services are off."""
    probes = []
    for path, data, label in (("/multi-agent/validate", {"portfolio_id": "1"}, "Multi-Agent"),
                              ("/mcp/run-tool", {"tool": "validate_portfolio", "portfolio_id": "1"}, "MCP")):
        code, _, body = _http("POST", student2_url + path, data=data)
        lowered = (body or "").lower()
        degraded = code is not None and code < 500 and ("unavailable" in lowered or "disabled" in lowered)
        probes.append({"check": f"{label} disabled in cloud", "http_status": code, "ok": degraded})
    return probes


def check_crud(student2_url):
    """Open then close a position through the Student 2 cloud frontend."""
    ticker = f"REVIEW-{_timestamp()[-6:]}"
    code, _, body = _http("POST", student2_url + "/positions/add",
                          data={"market_ticker": ticker, "side": "YES", "entry_price": "0.5", "size": "1"})
    created = code == 200 and ticker in (body or "")
    closed = False
    if created:
        marker = body.split(ticker)[0].rsplit('id="pos-', 1)
        if len(marker) == 2:
            pid = marker[1].split('"', 1)[0]
            code2, _, body2 = _http("POST", f"{student2_url}/positions/{pid}/close")
            closed = code2 == 200 and ticker not in (body2 or "")
    return [{"check": "CRUD create (open position)", "ok": created},
            {"check": "CRUD delete (close position)", "ok": closed}]


def recommend_release(apps, frontends, probes):
    """Pure release recommendation -> (recommendation, risks)."""
    risks = []
    ai_apps = [a["name"] for a in apps if any(m in a["name"].lower() for m in AI_APP_MARKERS)]
    if ai_apps:
        risks.append(f"AI service apps deployed ({', '.join(ai_apps)}): baseline requires them disabled "
                     "unless a bonus profile is being claimed.")
    down_students = [f["app"] for f in frontends if not f["ok"] and "student" in f["app"]]
    down_other = [f["app"] for f in frontends if not f["ok"] and "student" not in f["app"]]
    if down_students:
        risks.append(f"Student frontends not responding: {', '.join(down_students)}.")
    if down_other:
        risks.append(f"Non-student apps not responding: {', '.join(down_other)}.")
    not_running = [a["name"] for a in apps if a.get("status") and a["status"] != "Running"]
    if not_running:
        risks.append(f"Container Apps not in Running state: {', '.join(not_running)}.")
    slow = [f["app"] for f in frontends if f["ok"] and f["ms"] and f["ms"] > 5000]
    if slow:
        risks.append(f"Slow first response (>5 s, likely cold start): {', '.join(slow)}.")
    for p in probes:
        if not p["ok"]:
            risks.append(f"Check failed: {p['check']}.")

    if down_students or any(not p["ok"] for p in probes if "CRUD" in p["check"]):
        return "reject", risks
    if risks:
        return "conditional", risks
    return "approve", risks


def run_cloud_deployment_review(resource_group, urls=None, crud=False, decision=None, notes=None):
    t = Trace("Cloud Deployment Report Review Mode")
    t.add("Plan", f"Review the Azure deployment in resource group '{resource_group}': app inventory, frontend "
                  "reachability, AI services disabled by default, Student 2 CRUD, then record the human release decision.")
    apps = discover_cloud(resource_group)
    if apps is None:
        apps = [{"name": k, "url": v, "external": True, "status": None} for k, v in (urls or {}).items()]
        source = "URLs passed with --url (Azure CLI unavailable or not logged in)"
    else:
        source = f"az containerapp list -g {resource_group}"
    t.add("Act", f"Found {len(apps)} Container App(s) via {source}; probing every external frontend over HTTPS.")
    if not apps:
        t.add("Observe", "No deployment evidence found.")
        t.add("Adapt", "Recommendation: REJECT. Deploy first, or pass URLs with --url name=https://...")
        save_review("cloud-deployment-review", t, {"apps": []}, "# Cloud Deployment Review\n\nNo deployment found.\n")
        return False

    frontends = check_frontends(apps)
    s2 = next((f["url"] for f in frontends if f["app"].startswith("student-2")), None)
    probes = check_ai_disabled_behaviour(s2) if s2 else []
    if crud and s2:
        probes += check_crud(s2)
    ok_count = sum(f["ok"] for f in frontends)
    t.add("Observe", f"{ok_count}/{len(frontends)} frontend(s) responded; "
                     f"{sum(p['ok'] for p in probes)}/{len(probes)} behaviour check(s) passed.")
    recommendation, risks = recommend_release(apps, frontends, probes)
    t.add("Adapt", f"Agent recommendation: {recommendation.upper()} with {len(risks)} risk(s).")
    for r in risks:
        print(f"    - {r}")

    if decision is None and sys.stdin.isatty():
        print("\n[Human release decision] approve / conditional / reject")
        decision = input("  Decision: ").strip().lower() or None
        notes = input("  Justification (one line): ").strip() or None
    human = {"decision": decision or "pending", "notes": notes,
             "decided_at": datetime.datetime.now().isoformat(timespec="seconds") if decision else None}
    t.add("Adapt", f"Human release decision: {human['decision'].upper()}"
                   + (f" -- {notes}" if notes else ""))

    inv = "\n".join(f"| {a['name']} | {a.get('status') or '-'} | {a.get('url') or 'internal'} |" for a in apps)
    fe = "\n".join(f"| {f['app']} | {f['http_status']} | {f['ms']} ms | {'OK' if f['ok'] else 'FAIL'} |"
                   for f in frontends)
    pr = "\n".join(f"| {p['check']} | {'PASS' if p['ok'] else 'FAIL'} |" for p in probes) or "| - | - |"
    md = f"""# Cloud Deployment Review

**Agent recommendation:** {recommendation.upper()} · **Human release decision:** {human['decision'].upper()} · **Generated:** {datetime.datetime.now():%Y-%m-%d %H:%M}

| Stage | Detail |
| --- | --- |
{_trace_md(t)}

## Container App inventory ({source})

| App | Status | URL |
| --- | --- | --- |
{inv}

## Frontend reachability

| App | HTTP | First response | Result |
| --- | --- | --- | --- |
{fe}

## Behaviour checks (Student 2)

| Check | Result |
| --- | --- |
{pr}

## Risks
{_bullets(risks)}

## Human release decision
**{human['decision'].upper()}**{(' -- ' + notes) if notes else ''}
"""
    result = {"resource_group": resource_group, "source": source, "apps": apps, "frontends": frontends,
              "probes": probes, "recommendation": recommendation, "risks": risks, "human_decision": human}
    save_review("cloud-deployment-review", t, result, md)
    return recommendation != "reject"
