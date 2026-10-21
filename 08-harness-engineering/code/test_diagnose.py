"""Tests for the diagnose CLI, run against the real incident logs produced by the buggy code."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DIAG = HERE / "sample_service/tools/diagnose.py"
sys.path.insert(0, str(DIAG.parent))

import diagnose  # noqa: E402


def run(log: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(DIAG), "--log", str(log), *args], capture_output=True, text=True)
    return p.returncode, p.stdout


def task_log(task_id: str) -> Path:
    return HERE / "tasks" / task_id / "incident.jsonl"


def test_dupes_finds_republished_events_and_points_at_i4():
    rc, out = run(task_log("inc-stats-drift"), "dupes")
    assert rc == 0
    assert out.count("ERROR event_id=") == 2
    assert "2 event(s) published more than once" in out
    assert "dedupe on event_id" in out and "I4" in out


def test_gaps_finds_cancellations_that_were_never_published():
    rc, out = run(task_log("inc-lost-cancellations"), "gaps")
    assert out.count("OrderCancelled committed at the API but never published") == 4
    assert "hint:" in out


def test_conflicts_detects_hash_per_attempt_pattern():
    rc, out = run(task_log("inc-409-spike"), "conflicts")
    assert "WARN idem_key=mob-1 conflicts=3 distinct_request_hashes=3" in out
    assert "non-deterministic field" in out


def test_trace_follows_one_order_across_components():
    rows = diagnose.load(task_log("inc-stats-drift"))
    order_id = next(r["order_id"] for r in rows if r["event"] == "event.applied" and r["event_id"] == "6")
    rc, out = run(task_log("inc-stats-drift"), "trace", order_id)
    components = [line.split()[1].split(".")[0] for line in out.splitlines()]
    assert components[0] == "api" and "relay" in components and "consumer" in components
    assert all(order_id in line for line in out.splitlines())


def test_grep_filters_and_limit_truncates():
    rc, out = run(task_log("inc-409-spike"), "--limit", "3", "grep", "--event", "idempotency.conflict")
    lines = out.strip().splitlines()
    assert len(lines) == 4 and lines[-1].startswith("... 10 more")
    assert all(line.startswith("WARN ") for line in lines[:3])


def test_summary_puts_problems_first(tmp_path):
    log = tmp_path / "x.jsonl"
    rows = [{"ts": 1.0, "component": "api", "event": "order.placed", "level": "info", "order_id": "o1"},
            {"ts": 2.0, "component": "relay", "event": "publish.failed", "level": "error", "event_id": "1"}]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    rc, out = run(log, "summary")
    assert out.splitlines()[1].startswith("ERROR")


def test_missing_log_is_a_clear_error(tmp_path):
    rc, out = run(tmp_path / "nope.jsonl", "summary")
    assert rc == 2 and out.startswith("ERROR log file not found")


def test_service_writes_logs_diagnose_can_read(tmp_path, monkeypatch):
    log = tmp_path / "live.jsonl"
    monkeypatch.setenv("ORDERS_LOG_PATH", str(log))
    sys.path.insert(0, str(HERE / "sample_service"))
    from orders import api
    from orders.broker import FakeBroker
    from orders.consumer import drain
    from orders.db import connect
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "c1", 100)
    drain(conn, broker)
    rc, out = run(log, "dupes")
    assert "0 event(s) applied more than once" in out
