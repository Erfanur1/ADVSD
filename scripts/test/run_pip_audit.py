#!/usr/bin/env python3
"""
Pre-commit hook: pip-audit against every requirements.txt that was
staged/changed (pre-commit passes the matching filenames in as argv,
via this hook's `files:` filter in .pre-commit-config.yaml).

Cross-platform on purpose (no bash/chmod needed) so it runs the same
way on Windows, Mac and Linux.
"""
import shutil
import subprocess
import sys


def main():
    if shutil.which("pip-audit") is None:
        print("pip-audit not installed -- run: pip install pip-audit")
        return 1

    failed = False
    for req in sys.argv[1:]:
        print(f"== {req} ==")
        # "pip-audit" is resolved via PATH, same as every other dev-tool
        # pre-commit invokes (ruff, detect-secrets, etc.) -- args are
        # fixed/hardcoded, not user-controlled input, so this is safe.
        result = subprocess.run(["pip-audit", "-r", req])  # noqa: S603,S607
        if result.returncode != 0:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())