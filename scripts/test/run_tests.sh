#!/usr/bin/env bash
# Run every student's pytest suite locally.
set -euo pipefail
for n in 1 2 3 4; do
  echo "== student-$n =="
  ( cd "student-$n" && PYTHONPATH="$PWD" python -m pytest tests/ -q ) || exit 1
done
