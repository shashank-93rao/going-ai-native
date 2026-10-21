#!/usr/bin/env python3
"""Query the order service's structured logs. Built for agents: short output, grep-able lines.

    python tools/diagnose.py summary
    python tools/diagnose.py grep --event publish.failed --limit 5
    python tools/diagnose.py trace ord_1a2b3c4d5e
    python tools/diagnose.py dupes        # events applied or published more than once
    python tools/diagnose.py gaps         # state changes whose event never reached the consumer
    python tools/diagnose.py conflicts    # idempotency 409s grouped by key

Log source: --log PATH, else $ORDERS_LOG_PATH, else var/log/orders.jsonl.
Every line that reports a problem starts with ERROR or WARN, so `| grep ERROR` works.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

CORRELATION = ("order_id", "event_id", "type", "idem_key", "partition", "offset", "error")


def load(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return sorted(rows, key=lambda r: r.get("ts", 0))


def fmt(r: dict[str, Any]) -> str:
    level = r.get("level", "info").upper()
    tag = f"{level} " if level in ("ERROR", "WARN") else ""
    fields = " ".join(f"{k}={r[k]}" for k in CORRELATION if k in r)
    return f"{tag}{r.get('ts', 0):.3f} {r['component']}.{r['event']} {fields}".rstrip()


def emit(lines: Iterable[str], limit: int) -> list[str]:
    lines = list(lines)
    out = lines[:limit]
    if len(lines) > limit:
        out.append(f"... {len(lines) - limit} more (raise --limit)")
    return out


def cmd_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    if not rows:
        return ["no records"]
    c = Counter((r["component"], r["event"], r.get("level", "info")) for r in rows)
    out = [f"{len(rows)} records, ts {rows[0]['ts']:.3f} .. {rows[-1]['ts']:.3f}"]
    for (comp, ev, lvl), n in sorted(c.items(), key=lambda kv: (kv[0][2] == "info", -kv[1])):
        tag = f"{lvl.upper()} " if lvl in ("error", "warn") else ""
        out.append(f"{tag}{n:6d}  {comp}.{ev}")
    return out


def cmd_grep(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    def keep(r: dict[str, Any]) -> bool:
        return all([
            not args.component or r["component"] == args.component,
            not args.event or r["event"] == args.event,
            not args.level or r.get("level") == args.level,
            not args.order or r.get("order_id") == args.order,
            not args.event_id or r.get("event_id") == args.event_id,
        ])
    return emit((fmt(r) for r in rows if keep(r)), args.limit)


def cmd_trace(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    hits = [fmt(r) for r in rows if r.get("order_id") == args.order_id]
    return emit(hits, args.limit) if hits else [f"no records for order_id={args.order_id}"]


def cmd_dupes(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    applied: dict[str, list[dict[str, Any]]] = defaultdict(list)
    published: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if (r["component"], r["event"]) == ("consumer", "event.applied"):
            applied[r["event_id"]].append(r)
        if (r["component"], r["event"]) == ("relay", "event.published"):
            published[r["event_id"]].append(r)
    out: list[str] = []
    for eid, rs in applied.items():
        if len(rs) > 1:
            where = ", ".join(f"p{r.get('partition')}@{r.get('offset')}" for r in rs)
            out.append(f"ERROR event_id={eid} order_id={rs[0].get('order_id')} applied {len(rs)}x at {where}")
    republished = sum(1 for rs in published.values() if len(rs) > 1)
    out = emit(out, args.limit)
    out.append(f"{sum(1 for rs in applied.values() if len(rs) > 1)} event(s) applied more than once; "
               f"{republished} event(s) published more than once")
    if any(len(rs) > 1 for rs in applied.values()) and republished:
        out.append("hint: duplicates arrive at different offsets => they come from relay republish, which is legal "
                   "(at-least-once). The consumer must dedupe on event_id. See INVARIANTS.md I4.")
    return out


def cmd_gaps(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    state = {("api", "order.placed"): "OrderPlaced", ("api", "order.cancelled"): "OrderCancelled"}
    expected = {(r["order_id"], state[(r["component"], r["event"])]) for r in rows
                if (r["component"], r["event"]) in state}
    seen_pub = {(r.get("order_id"), r.get("type")) for r in rows if r["event"] == "event.published"}
    failed = {r.get("event_id") for r in rows if r["event"] == "publish.failed"}
    missing = sorted(expected - seen_pub)
    out = emit((f"ERROR order_id={o} {t} committed at the API but never published" for o, t in missing), args.limit)
    out.append(f"{len(missing)} committed state change(s) with no published event; "
               f"{len(failed)} distinct event_id(s) had publish failures")
    if missing and failed:
        out.append("hint: compare the outbox rows for these orders (published_at set?) with the relay's "
                   "publish.failed records. A row marked published without a matching event.published is a lost event.")
    return out


def cmd_conflicts(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[str]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["event"] == "idempotency.conflict":
            by_key[r["idem_key"]].append(r)
    out = []
    for key, rs in sorted(by_key.items(), key=lambda kv: -len(kv[1])):
        hashes = {r.get("request_hash") for r in rs}
        out.append(f"WARN idem_key={key} conflicts={len(rs)} distinct_request_hashes={len(hashes)}")
    out = emit(out, args.limit)
    out.append(f"{sum(len(v) for v in by_key.values())} conflict(s) across {len(by_key)} key(s)")
    if any(len({r.get('request_hash') for r in rs}) == len(rs) > 1 for rs in by_key.values()):
        out.append("hint: every retry of the same key hashed differently. A client that changed its body would "
                   "produce one new hash, repeated; a new hash per attempt points at a non-deterministic field in "
                   "request_hash (clock, uuid). See INVARIANTS.md I2.")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Query order-service structured logs.")
    ap.add_argument("--log", default=os.environ.get("ORDERS_LOG_PATH", "var/log/orders.jsonl"))
    ap.add_argument("--limit", type=int, default=20)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary")
    g = sub.add_parser("grep")
    for flag in ("--component", "--event", "--level", "--order", "--event-id"):
        g.add_argument(flag)
    t = sub.add_parser("trace")
    t.add_argument("order_id")
    sub.add_parser("dupes")
    sub.add_parser("gaps")
    sub.add_parser("conflicts")
    args = ap.parse_args(argv)
    path = Path(args.log)
    if not path.exists():
        print(f"ERROR log file not found: {path} (pass --log or set ORDERS_LOG_PATH)")
        return 2
    handler = {"summary": cmd_summary, "grep": cmd_grep, "trace": cmd_trace, "dupes": cmd_dupes,
               "gaps": cmd_gaps, "conflicts": cmd_conflicts}[args.cmd]
    print("\n".join(handler(load(path), args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
