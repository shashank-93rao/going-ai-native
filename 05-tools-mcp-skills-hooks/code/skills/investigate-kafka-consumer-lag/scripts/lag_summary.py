#!/usr/bin/env python3
"""Summarize `kafka-consumer-groups.sh --describe` output into a few lines an agent can act on.

    kafka-consumer-groups.sh --bootstrap-server $B --describe --group G | python3 lag_summary.py [--threshold 1000]

Prints totals, the top partitions, and `shape=` (single_partition | uniform | unassigned | none).
Stdlib only. Exit 1 with a message on unparseable input.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass


@dataclass
class Row:
    group: str
    topic: str
    partition: int
    lag: int
    consumer_id: str


def parse(text: str) -> list[Row]:
    rows: list[Row] = []
    header: list[str] | None = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "GROUP" and "LAG" in parts:
            header = parts
            continue
        if header is None or len(parts) < len(header) - 2:
            continue  # banner lines such as "Consumer group 'x' has no active members."
        rec = dict(zip(header, parts))
        lag_s = rec.get("LAG", "-")
        rows.append(Row(rec["GROUP"], rec["TOPIC"], int(rec["PARTITION"]),
                        int(lag_s) if lag_s.lstrip("-").isdigit() else 0, rec.get("CONSUMER-ID", "-")))
    return rows


def classify(rows: list[Row], threshold: int) -> str:
    total = sum(r.lag for r in rows)
    if total < threshold:
        return "none"
    unassigned_lag = sum(r.lag for r in rows if r.consumer_id == "-")
    if unassigned_lag * 2 >= total:
        return "unassigned"
    if len(rows) > 1 and max(r.lag for r in rows) * 2 >= total:
        return "single_partition"
    return "uniform"


def summarize(text: str, threshold: int = 1000, top: int = 3) -> str:
    rows = parse(text)
    if not rows:
        raise ValueError("no partition rows found; pass the output of `kafka-consumer-groups.sh --describe --group G`")
    total = sum(r.lag for r in rows)
    lags = sorted(r.lag for r in rows)
    median = lags[len(lags) // 2]
    worst = sorted(rows, key=lambda r: -r.lag)[:top]
    unassigned = [r.partition for r in rows if r.consumer_id == "-"]
    groups = sorted({r.group for r in rows})
    topics = sorted({r.topic for r in rows})
    lines = [
        f"group={','.join(groups)} topics={','.join(topics)} partitions={len(rows)} total_lag={total} "
        f"max_lag={lags[-1]} median_lag={median}",
        "top: " + ", ".join(f"{r.topic}[{r.partition}]={r.lag} owner={r.consumer_id[:24]}" for r in worst),
        f"unassigned_partitions={unassigned or 'none'}",
        f"shape={classify(rows, threshold)}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", nargs="?", help="describe output (default: stdin)")
    ap.add_argument("--threshold", type=int, default=1000, help="total lag below this is shape=none")
    a = ap.parse_args(argv)
    text = open(a.file).read() if a.file else sys.stdin.read()
    try:
        print(summarize(text, a.threshold))
    except ValueError as e:
        print(f"lag_summary: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
