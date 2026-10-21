#!/usr/bin/env bash
# Runs each module's tests in its own pytest process, offline (AINATIVE_FAKE=1).
# Separate processes keep module code dirs independent (no import-name collisions).
set -u
cd "$(dirname "$0")"
PY="${PY:-.venv/bin/python}"
export AINATIVE_FAKE=1
fail=0
for d in shared/tests */code; do
  [ -d "$d" ] || continue
  if find "$d" -name 'test_*.py' | grep -q .; then
    if out=$("$PY" -m pytest -q "$d" 2>&1); then
      echo "PASS $d  ($(echo "$out" | tail -1))"
    else
      echo "FAIL $d"; echo "$out" | tail -20; fail=1
    fi
  fi
done
exit $fail
