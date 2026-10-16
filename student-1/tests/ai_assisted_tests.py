"""
Post-commit AI-assisted unit testing (Student 1).

Sends the source of two endpoints (POST /watchlist and GET /markets) to the
shared AI-Mode service and asks the LLM to propose pytest cases. The proposals
are NEVER executed: each code block is only parsed to check it is valid Python,
then everything is saved to ai_test_suggestions.md for a person to review and
promote into tests/test_endpoints_r2.py.

If AI-Mode is unreachable (as in GitHub Actions, where no LLM runs) the script
says so and exits 0, so CI stays green while the skip is visible in the log.

Run locally:  python tests/ai_assisted_tests.py
"""
import ast
import os
import pathlib
import re
import sys

import requests

AI_MODE_URL = os.getenv("AI_MODE_URL", "http://localhost:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "ai_test_suggestions.md"
TARGETS = {"add_watchlist": "POST /watchlist", "list_markets": "GET /markets"}
TASK = (
    "Write 3 pytest unit test cases for this Flask endpoint: one normal case, "
    "one validation or error case, one edge case. A pytest fixture named "
    "'client' (a Flask test client) is available. Return only Python code."
)


def endpoint_source(func_name):
    """Return the decorator + body of one endpoint function from backend/app.py."""
    text = (ROOT / "backend" / "app.py").read_text()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            decorator = "@" + ast.get_source_segment(text, node.decorator_list[0])
            return decorator + "\n" + ast.get_source_segment(text, node)
    raise ValueError(f"endpoint function {func_name} not found")


def code_blocks(output):
    """Pull fenced code blocks out of the LLM reply (or treat the reply as code)."""
    blocks = re.findall(r"```(?:python)?\n(.*?)```", output, flags=re.DOTALL)
    return blocks or [output]


def ask_ai(source):
    resp = requests.post(
        f"{AI_MODE_URL}/ai/complete",
        json={"task": TASK, "context": source},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json().get("output", "")


def main():
    lines = ["# AI-assisted unit test suggestions (Student 1)", ""]
    any_invalid = False
    for func_name, label in TARGETS.items():
        try:
            output = ask_ai(endpoint_source(func_name))
        except requests.RequestException as exc:
            print(f"AI-Mode unavailable at {AI_MODE_URL} ({type(exc).__name__}); skipping AI-assisted testing.")
            return 0
        blocks = code_blocks(output)
        valid = 0
        test_count = 0
        for block in blocks:
            try:
                tree = ast.parse(block)
            except SyntaxError:
                any_invalid = True
                continue
            valid += 1
            test_count += sum(
                1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
            )
        print(f"{label}: {test_count} suggested test(s), {valid}/{len(blocks)} code block(s) are valid Python")
        lines += [f"## {label}", f"{test_count} suggested test(s); {valid}/{len(blocks)} block(s) valid Python.", "", output, ""]
    REPORT.write_text("\n".join(lines))
    print(f"Saved suggestions to {REPORT}")
    return 1 if any_invalid else 0


if __name__ == "__main__":
    sys.exit(main())