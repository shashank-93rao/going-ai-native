#!/usr/bin/env python3
"""Deterministic repro scenarios for the failure modes in INVARIANTS.md.

Each scenario drives the real code against the FakeBroker and prints one line:
`PASS <scenario>` or `FAIL <scenario>: <what broke>`. Use them as step 1 of the
bug-fix protocol (reproduce), before writing the failing test.

    python tools/repro.py all
    python tools/repro.py republish     # relay crash between publish and mark
    python tools/repro.py broker-blip   # publish fails mid-batch, then recovers
    python tools/repro.py retry         # client retries create with the same key
    python tools/repro.py double-cancel # two cancels with different keys
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orders import api  # noqa: E402
from orders.broker import FakeBroker  # noqa: E402
from orders.consumer import drain, get_stats  # noqa: E402
from orders.db import connect  # noqa: E402
from orders.outbox import TOPIC, relay_once  # noqa: E402


def republish() -> str | None:
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "cust_1", 1000)
    relay_once(conn, broker)
    conn.execute("UPDATE outbox SET published_at = NULL")  # simulate: crashed before marking
    drain(conn, broker)
    count, total = get_stats(conn, "cust_1")
    return None if (count, total) == (1, 1000) else f"stats={count},{total} want 1,1000 after republish"


def broker_blip() -> str | None:
    conn, broker = connect(), FakeBroker()
    order = api.create_order(conn, "k1", "cust_1", 1000)
    api.cancel_order(conn, "k2", order["order_id"])
    broker.fail_when(lambda key, value: value["type"] == "OrderPlaced")
    relay_once(conn, broker)
    broker.fail_when(None)
    relay_once(conn, broker)
    relay_once(conn, broker)
    types = [m.value["type"] for m in broker.messages(TOPIC) if m.key == order["order_id"]]
    return None if types == ["OrderPlaced", "OrderCancelled"] else f"per-key order {types}"


def retry() -> str | None:
    conn = connect()
    first = api.create_order(conn, "k1", "cust_1", 1000)
    try:
        again = api.create_order(conn, "k1", "cust_1", 1000)
    except api.IdempotencyConflict:
        return "identical retry raised IdempotencyConflict"
    rows = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    return None if again == first and rows == 1 else f"retry changed response or emitted {rows} events"


def double_cancel() -> str | None:
    conn = connect()
    order = api.create_order(conn, "k1", "cust_1", 1000)
    api.cancel_order(conn, "k2", order["order_id"])
    try:
        api.cancel_order(conn, "k3", order["order_id"])
    except api.InvalidTransition:
        return None
    return "second cancel with a new key succeeded (expected InvalidTransition)"


SCENARIOS = {"republish": republish, "broker-blip": broker_blip, "retry": retry, "double-cancel": double_cancel}


def main(argv: list[str]) -> int:
    names = list(SCENARIOS) if not argv or argv[0] == "all" else argv
    failed = 0
    for name in names:
        problem = SCENARIOS[name]()
        print(f"PASS {name}" if problem is None else f"FAIL {name}: {problem}")
        failed += problem is not None
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
