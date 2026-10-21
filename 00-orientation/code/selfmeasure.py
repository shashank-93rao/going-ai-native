"""CLI for a personal, randomized AI / no-AI experiment.

    export SELFMEASURE_SEED="$(openssl rand -hex 16)"   # keep it private; the log stores only a fingerprint
    python selfmeasure.py register PAY-412 --size M --est 120 --kind bugfix --title "idempotency key collision"
    python selfmeasure.py register PAY-415 --size M --est 90  --kind feature --title "retry budget for webhook sender"
    python selfmeasure.py assign                       # assigns every pending task at once
    python selfmeasure.py start PAY-412
    python selfmeasure.py merge PAY-412 --pr "#8812" --active 95
    python selfmeasure.py perceive PAY-412 --other 150  # how long you think the other arm would have taken
    python selfmeasure.py rework PAY-412 --kind fix --minutes 40
    python selfmeasure.py summary

The log path defaults to ./selfmeasure.jsonl; override with --log or SELFMEASURE_LOG.
Every subcommand accepts --ts to backfill an event (ISO-8601, e.g. from `gh pr view N --json mergedAt`).
"""

from __future__ import annotations

import argparse
import os
import sys

from selfmeasure_log import SIZES, LogError, append_event, assign_pending, fold, read_events
from selfmeasure_stats import render, summarize


def _seed() -> str:
    seed = os.environ.get("SELFMEASURE_SEED")
    if not seed:
        raise LogError("set SELFMEASURE_SEED to a private random string before assigning tasks")
    return seed


def _event(args: argparse.Namespace, **fields: object) -> dict:
    ev = {"task_id": args.task_id, **{k: v for k, v in fields.items() if v is not None}}
    if args.ts:
        ev["ts"] = args.ts
    return ev


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=os.environ.get("SELFMEASURE_LOG", "selfmeasure.jsonl"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    def task_cmd(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("task_id")
        p.add_argument("--ts", help="ISO-8601 timestamp to backfill (default: now, UTC)")
        return p

    p = task_cmd("register", "add a task with your estimate, BEFORE it is assigned")
    p.add_argument("--size", choices=SIZES, required=True)
    p.add_argument("--est", type=float, required=True, help="estimated minutes of work (pre-assignment)")
    p.add_argument("--kind", default="feature")
    p.add_argument("--title", default="")

    sub.add_parser("assign", help="randomly assign every registered, unassigned task")
    task_cmd("start", "you began work")
    p = task_cmd("merge", "the PR merged")
    p.add_argument("--pr")
    p.add_argument("--active", type=float, help="active minutes you spent, if you track them")
    p = task_cmd("rework", "a fix, revert or follow-up caused by this change")
    p.add_argument("--kind", choices=["fix", "revert", "followup"], required=True)
    p.add_argument("--minutes", type=float, required=True)
    p = task_cmd("abandon", "you stopped; the task stays in the analysis")
    p.add_argument("--reason", required=True)
    p = task_cmd("perceive", "your guess: minutes the other arm would have taken")
    p.add_argument("--other", type=float, required=True)

    p = sub.add_parser("summary", help="print the analysis")
    p.add_argument("--outcome", choices=["wall", "active"], default="wall")
    p.add_argument("--rework-days", type=float, default=14)
    sub.add_parser("status", help="list tasks and their current state")
    return ap


def run(argv: list[str]) -> str:
    args = build_parser().parse_args(argv)
    log = args.log
    if args.cmd == "register":
        append_event(log, _event(args, event="register", size=args.size, est_minutes=args.est, kind=args.kind, title=args.title))
        return f"registered {args.task_id}; run `assign` once your batch is registered"
    if args.cmd == "assign":
        got = assign_pending(log, _seed())
        return "\n".join(f"{tid}: {arm}" for tid, arm in got.items()) or "nothing pending"
    if args.cmd == "start":
        append_event(log, _event(args, event="start"))
    elif args.cmd == "merge":
        append_event(log, _event(args, event="merge", pr=args.pr, active_minutes=args.active))
    elif args.cmd == "rework":
        append_event(log, _event(args, event="rework", rework_kind=args.kind, minutes=args.minutes))
    elif args.cmd == "abandon":
        append_event(log, _event(args, event="abandon", reason=args.reason))
    elif args.cmd == "perceive":
        append_event(log, _event(args, event="perceive", perceived_other_arm_minutes=args.other))
    elif args.cmd == "summary":
        return render(summarize(fold(read_events(log)), outcome=args.outcome, rework_days=args.rework_days), args.outcome)
    elif args.cmd == "status":
        rows = []
        for t in fold(read_events(log)).values():
            state = "abandoned" if t.abandoned else "merged" if t.merged else "started" if t.started else "assigned" if t.arm else "registered"
            rows.append(f"{t.task_id:<12}{t.size:<3}{(t.arm or '-'):<7}{state:<11}{t.title}")
        return "\n".join(rows) or "empty log"
    return f"logged {args.cmd} for {args.task_id}"


def main() -> None:
    try:
        print(run(sys.argv[1:]))
    except LogError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
