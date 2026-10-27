"""
Shared Agentic Loop -- Release 1, Task 4.

Extends the Release 0 Plan -> Act -> Observe -> Adapt loop with two
new validation modes:
  --mode mcp   exercises the shared MCP server end-to-end
  --mode rag   exercises the shared RAG server end-to-end

Runs locally, NOT containerised. Prints a structured trace to the
terminal (capture this output as Release 1 evidence), and also writes
it to a timestamped log file for the report.

Run:
  python loop.py --mode mcp
  python loop.py --mode rag

Release 2 adds three review modes (implemented in reviews.py):
  python loop.py --mode multi-agent-review
  python loop.py --mode testing-review [--students student-2] [--skip-audit] [--skip-ci]
  python loop.py --mode cloud-deployment-review --resource-group group29-r2-rg [--crud-check]
                 [--decision approve|conditional|reject --notes "..."]
Review logs and Markdown reports are written to docs/release-2/review-logs/.
"""
import os
import sys
import json
import argparse
import datetime
import requests

MCP_URL = os.getenv("MCP_URL", "http://localhost:8100")
RAG_URL = os.getenv("RAG_URL", "http://localhost:8200")

LOG_DIR = os.path.join(os.path.dirname(__file__), "validation_logs")


def log_trace(mode, trace, result):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOG_DIR, f"{mode}_validation_{ts}.json")
    with open(path, "w") as f:
        json.dump({"mode": mode, "trace": trace, "result": result, "timestamp": ts}, f, indent=2)
    print(f"\n[saved evidence log: {path}]")


def print_stage(stage, detail):
    print(f"  [{stage}] {detail}")


def run_mcp_validation():
    print("=== Agentic Loop: MCP Validation Mode ===")
    trace = []

    # PLAN
    tool_name = "search_markets"
    params = {"query": "election", "source": "both"}
    detail = f"Decided to validate the MCP server by calling '{tool_name}' with {params}."
    trace.append({"stage": "Plan", "detail": detail})
    print_stage("Plan", detail)

    # ACT
    detail = f"Calling MCP server at {MCP_URL}/mcp/call"
    trace.append({"stage": "Act", "detail": detail})
    print_stage("Act", detail)
    result = None
    reachable = True
    try:
        resp = requests.post(f"{MCP_URL}/mcp/call", json={"tool": tool_name, "params": params}, timeout=15)
        result = resp.json()
    except Exception as exc:
        reachable = False
        result = {"error": str(exc)}

    # OBSERVE
    got_result = reachable and "result" in result
    detail = f"MCP server {'returned a structured result' if got_result else 'did not return a usable result'}."
    trace.append({"stage": "Observe", "detail": detail})
    print_stage("Observe", detail)

    # ADAPT
    if got_result:
        detail = "MCP validation passed: tool call returned a structured result."
    else:
        detail = "MCP validation failed: check that the MCP server is running on the expected port."
    trace.append({"stage": "Adapt", "detail": detail})
    print_stage("Adapt", detail)

    print("\n--- Raw result ---")
    print(json.dumps(result, indent=2))

    log_trace("mcp", trace, result)
    return got_result


def run_rag_validation():
    print("=== Agentic Loop: RAG Validation Mode ===")
    trace = []

    # PLAN
    question = "What is driving sentiment in election markets right now?"
    detail = f"Decided to validate the RAG server with a grounded question: '{question}'"
    trace.append({"stage": "Plan", "detail": detail})
    print_stage("Plan", detail)

    # ACT
    detail = f"Calling RAG server at {RAG_URL}/rag/query"
    trace.append({"stage": "Act", "detail": detail})
    print_stage("Act", detail)
    result = None
    reachable = True
    try:
        resp = requests.post(f"{RAG_URL}/rag/query", json={"question": question}, timeout=60)
        result = resp.json()
    except Exception as exc:
        reachable = False
        result = {"error": str(exc)}

    # OBSERVE
    got_answer = reachable and "answer" in result
    has_citations = got_answer and len(result.get("citations", [])) > 0
    detail = (
        f"RAG server returned an answer with confidence={result.get('confidence')}, "
        f"{len(result.get('citations', []))} citation(s), "
        f"insufficient_context={result.get('insufficient_context')}."
        if got_answer else "RAG server did not return a usable answer."
    )
    trace.append({"stage": "Observe", "detail": detail})
    print_stage("Observe", detail)

    # ADAPT
    if got_answer and has_citations:
        detail = "RAG validation passed: grounded answer with citations and a confidence category was returned."
    elif got_answer:
        detail = "RAG validation partial: an answer was returned but without citations (check insufficient_context handling)."
    else:
        detail = "RAG validation failed: check that the RAG server (and AI-Mode) are running."
    trace.append({"stage": "Adapt", "detail": detail})
    print_stage("Adapt", detail)

    print("\n--- Raw result ---")
    print(json.dumps(result, indent=2))

    log_trace("rag", trace, result)
    return got_answer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shared agentic loop: Release 1 validation + Release 2 review modes")
    parser.add_argument("--mode", required=True, choices=[
        "mcp", "rag", "multi-agent-review", "testing-review", "cloud-deployment-review"])
    parser.add_argument("--history", help="multi-agent-review: workflow_history.json to use if the server is down")
    parser.add_argument("--students", nargs="+", help="testing-review: limit to these folders, e.g. student-2")
    parser.add_argument("--skip-audit", action="store_true", help="testing-review: skip pip-audit (offline)")
    parser.add_argument("--skip-ci", action="store_true", help="testing-review: skip the GitHub Actions lookup")
    parser.add_argument("--resource-group", default=os.getenv("RESOURCE_GROUP", "group29-r2-rg"))
    parser.add_argument("--url", action="append", default=[], metavar="NAME=URL",
                        help="cloud-deployment-review: app URL when Azure CLI is unavailable (repeatable)")
    parser.add_argument("--crud-check", action="store_true",
                        help="cloud-deployment-review: open and close a test position on Student 2")
    parser.add_argument("--decision", choices=["approve", "conditional", "reject"],
                        help="cloud-deployment-review: human release decision (prompted if omitted)")
    parser.add_argument("--notes", help="cloud-deployment-review: one-line justification")
    args = parser.parse_args()

    if args.mode == "mcp":
        ok = run_mcp_validation()
    elif args.mode == "rag":
        ok = run_rag_validation()
    else:
        import reviews
        if args.mode == "multi-agent-review":
            ok = reviews.run_multi_agent_review(args.history)
        elif args.mode == "testing-review":
            ok = reviews.run_testing_review(args.students, skip_audit=args.skip_audit, skip_ci=args.skip_ci)
        else:
            urls = dict(u.split("=", 1) for u in args.url if "=" in u)
            ok = reviews.run_cloud_deployment_review(args.resource_group, urls=urls, crud=args.crud_check,
                                                     decision=args.decision, notes=args.notes)

    sys.exit(0 if ok else 1)
