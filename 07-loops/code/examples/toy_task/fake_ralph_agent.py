"""A stand-in for `claude -p` in Ralph loops, so ralph.py / ralph.sh run offline.

Reads the prompt from stdin (and ignores it), works in the current directory, then exits.
FAKE_AGENT_MODE picks the behaviour:
  fix      do the first unchecked fix_plan item correctly and tick it (a good iteration)
  noop     change nothing (a stuck agent)
  lie      tick every item without fixing anything (premature completion claim)
  regress  break the code (the harness should revert)
  crash    exit 1 without doing anything
  blocked  write .ralph/BLOCKED and exit
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve()
sys.path[:0] = [str(_here.parents[1]), str(_here.parents[2]), str(_here.parents[4] / "shared")]
from toy_task import apply_fix  # noqa: E402


def main() -> int:
    sys.stdin.read()
    mode = os.environ.get("FAKE_AGENT_MODE", "fix")
    ws = Path.cwd()
    plan = ws / "fix_plan.md"
    text = plan.read_text()
    if mode == "crash":
        print("fake agent: crashing")
        return 1
    if mode == "blocked":
        (ws / ".ralph").mkdir(exist_ok=True)
        (ws / ".ralph" / "BLOCKED").write_text("spec contradicts itself on refill semantics")
        return 0
    if mode == "noop":
        print("fake agent: looked around, changed nothing")
        return 0
    if mode == "lie":
        plan.write_text(text.replace("- [ ]", "- [x]"))
        print("fake agent: all done!")
        return 0
    if mode == "regress":
        f = ws / "tokenbucket.py"
        f.write_text(f.read_text().replace('raise ValueError("n must be positive")', "return False"))
        print("fake agent: refactored try_acquire")
        return 0
    m = re.search(r"^- \[ \] (\S+)", text, re.M)
    if not m:
        print("fake agent: nothing to do")
        return 0
    item = m.group(1)
    apply_fix(ws, item)
    plan.write_text(text.replace(f"- [ ] {item}", f"- [x] {item}", 1))
    print(f"fake agent: fixed {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
