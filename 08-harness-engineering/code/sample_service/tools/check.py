#!/usr/bin/env python3
"""The fast local gate: invariant lint, docs freshness, then tests. Target: under 5 seconds.

    python tools/check.py          # what "done" means for any change in this repo

Prints only failures plus one summary line, so the agent's context is not
flooded with passing output. Exit code 0 means done; anything else means not done.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> tuple[int, str]:
    script = ROOT / cmd[1]
    if cmd[1].startswith("tools/") and not script.exists():
        return 0, f"(skipped: {cmd[1]} not present)"
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    t0 = time.time()
    lint_rc, lint_out = run([sys.executable, "tools/lint_invariants.py"])
    if lint_rc:
        print(lint_out)
    docs_rc, docs_out = run([sys.executable, "tools/check_docs.py"])
    if docs_rc:
        print(docs_out)
    test_rc, test_out = run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"])
    if test_rc:
        print("\n".join(test_out.splitlines()[-30:]))
    status = "PASS" if not (lint_rc or docs_rc or test_rc) else "FAIL"
    tests_line = test_out.splitlines()[-1] if test_out else "no output"
    print(f"check: {status} lint={'ok' if not lint_rc else 'FAIL'} docs={'ok' if not docs_rc else 'FAIL'} tests=({tests_line}) in {time.time() - t0:.1f}s")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
