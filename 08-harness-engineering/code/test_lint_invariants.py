"""Tests for the invariant lint and the docs-freshness check."""

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SERVICE = HERE / "sample_service"
sys.path.insert(0, str(SERVICE / "tools"))

import check_docs  # noqa: E402
from lint_invariants import RULES, lint_paths, lint_source  # noqa: E402
from task_suite import apply_edits, load_tasks  # noqa: E402


def rules(src: str, path: str = "orders/api.py") -> list[str]:
    return [f.rule for f in lint_source(textwrap.dedent(src), path)]


def test_base_service_is_clean():
    assert lint_paths([SERVICE / "orders"], SERVICE) == []


def test_inv001_state_write_without_outbox():
    src = '''
    def ship(conn, order_id):
        with tx(conn):
            conn.execute("UPDATE orders SET status = 'SHIPPED' WHERE id = ?", (order_id,))
    '''
    assert rules(src) == ["INV001"]
    ok = src.replace("(order_id,))", "(order_id,))\n            _enqueue(conn, order_id, 'OrderShipped', {})")
    assert rules(ok) == []


def test_inv002_publish_outside_relay():
    src = '''
    def create(conn, broker):
        broker.publish("orders", key="k", value={})
    '''
    assert "INV002" in rules(src)
    assert "INV002" not in rules(src, "orders/outbox.py")


def test_inv003_swallowed_failure_in_relay():
    src = '''
    def relay_once(conn, broker):
        for row in rows:
            try:
                broker.publish("t", key="k", value={})
            except BrokerError:
                continue
    '''
    assert rules(src, "orders/outbox.py") == ["INV003"]
    assert rules(src.replace("continue", "break"), "orders/outbox.py") == []


def test_inv004_read_model_without_dedupe():
    src = '''
    def handle(conn, ev):
        conn.execute("UPDATE customer_stats SET order_count = order_count + 1 WHERE customer_id = ?", (ev,))
    '''
    assert rules(src, "orders/consumer.py") == ["INV004"]


def test_inv005_clock_in_request_hash():
    assert rules('rh = request_hash("op", {**body, "t": time.time()})\n') == ["INV005"]
    assert rules('rh = request_hash("op", body)\n') == []


def test_inv006_manual_commit_but_not_broker_commit():
    assert rules("def f(conn):\n    conn.commit()\n") == ["INV006"]
    assert rules("def f(broker, m):\n    broker.commit('g', m)\n") == []


def test_messages_carry_remediation():
    f = lint_source('rh = request_hash("op", {"t": _now()})\n', "orders/api.py")[0]
    out = f.render()
    assert out.startswith("orders/api.py:1:")
    for part in ("why:", "fix:", "see: INVARIANTS.md#i2"):
        assert part in out
    assert all(r["fix"] and r["see"] for r in RULES.values())


def test_suppression_requires_a_reason():
    base = 'rh = request_hash("op", {"t": _now()})'
    assert rules(base + "  # noqa: INV005 replay window is intentional here\n") == []
    assert rules(base + "  # noqa: INV005\n") == ["INV005"]


@pytest.mark.parametrize("task_id,expected", [
    ("bug-relay-skips-failure", "INV003"),
    ("inc-409-spike", "INV005"),
    ("inc-stats-drift", None),         # blind spot: dedupe on offset still inserts processed_events
    ("inc-lost-cancellations", None),  # blind spot: mis-scoped UPDATE is semantically wrong, not structurally
])
def test_lint_against_injected_bugs(tmp_path, task_id, expected):
    shutil.copytree(SERVICE / "orders", tmp_path / "orders")
    [task] = load_tasks(only=[task_id])
    apply_edits(tmp_path, task.inject)
    found = {f.rule for f in lint_paths([tmp_path / "orders"], tmp_path)}
    assert found == ({expected} if expected else set())


def test_cli_exit_codes(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def f(conn):\n    conn.commit()\n")
    lint = str(SERVICE / "tools/lint_invariants.py")
    clean = subprocess.run([sys.executable, lint], capture_output=True, text=True)
    dirty = subprocess.run([sys.executable, lint, "--json", str(bad)], capture_output=True, text=True)
    assert clean.returncode == 0 and "invariants hold" in clean.stdout
    assert dirty.returncode == 1 and '"rule": "INV006"' in dirty.stdout


def test_check_docs_clean_and_detects_stale_anchor(tmp_path):
    assert check_docs.check(SERVICE) == []
    repo = tmp_path / "repo"
    shutil.copytree(SERVICE, repo, ignore=shutil.ignore_patterns("__pycache__"))
    inv = repo / "INVARIANTS.md"
    inv.write_text(inv.read_text().replace("## I3. Per-key ordering", "## I3. Ordering"))
    (repo / "orders/refunds.py").write_text("")
    problems = check_docs.check(repo)
    assert any("D2" in p and "i3-per-key-ordering" in p for p in problems)
    assert any("D3" in p and "refunds.py" in p for p in problems)
