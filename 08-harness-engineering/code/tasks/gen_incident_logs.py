#!/usr/bin/env python3
"""Regenerate tasks/inc-*/incident.jsonl by running each incident's *buggy* code.

The logs are real output of the injected bug under a scripted traffic pattern and a
fake clock, so they are deterministic and the diagnose CLI is tested on genuine data.

    python tasks/gen_incident_logs.py            # all incidents
    python tasks/gen_incident_logs.py inc-409-spike
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_suite import build_workspace, load_tasks  # noqa: E402

PRELUDE = '''
import sys, time
sys.path.insert(0, ".")
class Clock:
    def __init__(self, t): self.t = t
    def __call__(self):
        self.t += 0.004
        return self.t
clock = Clock({start})
time.time = clock
from orders import api, obs
from orders.broker import FakeBroker
from orders.consumer import drain
from orders.db import connect
from orders.outbox import relay_once
conn, broker = connect(), FakeBroker()
'''

SCENARIOS = {
    # 2026-10-14 02:10 UTC. Relay OOM-killed after publishing, before marking two rows.
    "inc-stats-drift": (1791943800, '''
for i, (cust, amt) in enumerate([("c_101", 1200), ("c_102", 800), ("c_103", 4500), ("c_101", 300), ("c_102", 999)]):
    api.create_order(conn, f"idem-{i}", cust, amt)
    clock.t += 20
drain(conn, broker)
clock.t += 60
for i, (cust, amt) in enumerate([("c_103", 700), ("c_101", 2500), ("c_102", 150)], start=5):
    api.create_order(conn, f"idem-{i}", cust, amt)
relay_once(conn, broker)
obs.log("relay", "process.killed", level="error", reason="OOMKilled", exit_code=137)
conn.execute("UPDATE outbox SET published_at = NULL WHERE id IN (6, 7)")  # marks never committed
clock.t += 45
obs.log("relay", "process.started", reason="restart")
drain(conn, broker)
api.create_order(conn, "idem-5", "c_103", 700)  # an ordinary client retry, replayed
'''),
    # 2026-10-14 09:00 UTC. Broker rejects some publishes for ~20 minutes.
    "inc-lost-cancellations": (1791968400, '''
flaky = {"idem-1", "idem-4", "idem-6"}
orders = {}
for i in range(8):
    o = api.create_order(conn, f"idem-{i}", f"c_{200 + i % 3}", 1000 + 100 * i)
    orders[f"idem-{i}"] = o["order_id"]
    clock.t += 15
for key in ("idem-1", "idem-2", "idem-4", "idem-6"):
    api.cancel_order(conn, f"cancel-{key}", orders[key])
    clock.t += 10
bad = {orders[k] for k in flaky}
broker.fail_when(lambda key, value: key in bad and value["type"] == "OrderCancelled")
for _ in range(3):
    relay_once(conn, broker)
    clock.t += 300
broker.fail_when(None)
for _ in range(2):
    drain(conn, broker)
    clock.t += 60
'''),
    # 2026-10-14 14:00 UTC. Mobile clients retry after 60s with the same key and body.
    "inc-409-spike": (1791986400, '''
for i in range(12):
    try:
        api.create_order(conn, f"mob-{i}", f"c_{300 + i}", 2000 + i)
    except api.OrderError:
        pass
    clock.t += 5
for attempt in range(3):
    clock.t += 61
    for i in (1, 4, 7, 9):
        try:
            api.create_order(conn, f"mob-{i}", f"c_{300 + i}", 2000 + i)
        except api.IdempotencyConflict:
            pass
try:
    api.create_order(conn, "mob-2", "c_302", 9999)  # a genuine client bug: same key, new body
except api.IdempotencyConflict:
    pass
drain(conn, broker)
'''),
}


def generate(task_id: str) -> Path:
    [task] = load_tasks(only=[task_id])
    start, body = SCENARIOS[task_id]
    out = task.dir / "incident.jsonl"
    with tempfile.TemporaryDirectory() as tmp:
        saved = out.read_bytes() if out.exists() else None
        if out.exists():
            out.unlink()  # build_workspace copies it; we are regenerating it
        try:
            repo = build_workspace(task, Path(tmp))
        finally:
            if saved is not None:
                out.write_bytes(saved)
        log = Path(tmp) / "orders.jsonl"
        env = {**os.environ, "ORDERS_LOG_PATH": str(log)}
        subprocess.run([sys.executable, "-c", PRELUDE.format(start=start) + body], cwd=repo, env=env, check=True)
        out.write_text(log.read_text())
    return out


if __name__ == "__main__":
    for tid in sys.argv[1:] or list(SCENARIOS):
        p = generate(tid)
        print(f"wrote {p} ({len(p.read_text().splitlines())} records)")
