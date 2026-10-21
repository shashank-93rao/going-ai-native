#!/usr/bin/env python3
"""A deterministic stand-in for a coding agent, so the eval harness itself can be tested.

It is NOT a model of how real agents behave. It reads the task id from
$AUTONOMY_TASK_ID (a back channel only fakes use) and applies a known edit set:

  --policy oracle         apply the reference fix (except tasks listed in --fail)
  --policy harness-aware  apply the reference fix only if every harness file the task
                          `needs` exists in the workdir; otherwise apply the task's naive
                          fix if it has one, else do nothing. This simulates "the agent
                          succeeds when the harness gives it what it needs".
  --policy naive          always apply the naive fix (tamper with tests, swallow errors...)
  --policy noop           change nothing

Usage: fake_agent.py [--policy P] [--fail id,id] WORKDIR PROMPT_FILE
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_suite import apply_edits, load_tasks  # noqa: E402


def decide(policy: str, task, workdir: Path, fail: set[str]) -> tuple[str, list]:
    missing = [n for n in task.needs if not (workdir / n).exists()]
    if policy == "noop":
        return "noop", []
    if policy == "naive":
        return "naive", task.naive
    if policy == "oracle":
        if task.id in fail:
            return ("naive", task.naive) if task.naive else ("gave up", [])
        return "reference fix", task.reference_fix()
    if policy == "harness-aware":
        if not missing:
            return "reference fix", task.reference_fix()
        why = f"missing {', '.join(missing)}"
        return (f"naive fix ({why})", task.naive) if task.naive else (f"gave up ({why})", [])
    raise ValueError(policy)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="oracle", choices=["oracle", "harness-aware", "naive", "noop"])
    ap.add_argument("--fail", default="", help="task ids the oracle policy should fail")
    ap.add_argument("workdir", type=Path)
    ap.add_argument("prompt", type=Path)
    args = ap.parse_args(argv)
    task_id = os.environ["AUTONOMY_TASK_ID"]
    [task] = load_tasks(only=[task_id])
    _ = args.prompt.read_text()  # a real agent would start here
    action, edits = decide(args.policy, task, args.workdir, set(filter(None, args.fail.split(","))))
    apply_edits(args.workdir, edits)
    print(f"fake-agent policy={args.policy} task={task_id}: {action} ({len(edits)} edit(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
