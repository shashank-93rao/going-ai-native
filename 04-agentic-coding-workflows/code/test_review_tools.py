"""Tests for the tautological-test linter, the call-site verifier, the reviewer, and the demo."""

from __future__ import annotations

import json

import pytest

from ainative_kit import FakeClient, text
from check_callsite import problems
from diff_reviewer import DEMO_DIFF, DEMO_REPLY, DEMO_SPEC, parse_findings, review
from tautology_lint import lint_diff, lint_source

BAD_TESTS = '''
from unittest.mock import MagicMock
from payments.idempotency import fingerprint, handle

def test_nothing():
    handle({"amount": 100})

def test_trivial():
    assert True

def test_same_sides():
    x = fingerprint({"a": 1})
    assert x == x

def test_mock_return():
    store = MagicMock()
    store.get.return_value = {"status": 201}
    assert store.get("k") == store.get.return_value

def test_oracle_from_impl():
    assert fingerprint({"a": 1}) == fingerprint({"a": 1})

def test_swallowed():
    try:
        assert handle({}) == 422
    except AssertionError:
        pass
'''

GOOD_TESTS = '''
from decimal import Decimal
import pytest
from payments.idempotency import fingerprint, handle

def test_replay_returns_same_response(store):
    first = handle(store, key="k1", body={"amount": 100})
    second = handle(store, key="k1", body={"amount": 100})
    assert second.status == 201
    assert second.body == first.body
    assert store.charge_count("k1") == 1

def test_decimal_literal():
    assert Decimal("1.0") == Decimal("1.00")

def test_mismatched_body_rejected(store):
    handle(store, key="k1", body={"amount": 100})
    with pytest.raises(ValueError):
        handle(store, key="k1", body={"amount": 999})

def test_fingerprint_is_order_independent():
    assert fingerprint({"a": 1, "b": 2}) == "3f1c"
'''


def rules(findings):
    return {(f.where.split("::")[1].split(":")[0], f.rule) for f in findings}


def test_lint_flags_each_bad_pattern():
    got = rules(lint_source(BAD_TESTS, "t.py"))
    assert ("test_nothing", "no-assertion") in got
    assert ("test_trivial", "trivial-assert") in got
    assert ("test_same_sides", "trivial-assert") in got
    assert ("test_mock_return", "asserts-mock-return") in got
    assert ("test_oracle_from_impl", "oracle-from-impl") in got
    assert ("test_swallowed", "swallowed") in got


def test_lint_is_quiet_on_good_tests():
    assert lint_source(GOOD_TESTS, "t.py") == []


DIFF = """diff --git a/tests/test_consumer.py b/tests/test_consumer.py
--- a/tests/test_consumer.py
+++ b/tests/test_consumer.py
@@ -10,6 +10,5 @@
+@pytest.mark.skip(reason="flaky")
 def test_rebalance_commits_offsets():
-    assert committed == {0: 42}
-    assert dlq.empty()
+    assert committed
--- a/src/consumer.py
+++ b/src/consumer.py
@@ -1,2 +1,2 @@
-    assert x
+    pass
"""


def test_lint_diff_finds_disarmed_tests_only_in_test_files():
    found = {(f.rule, f.where) for f in lint_diff(DIFF)}
    assert ("added-skip", "tests/test_consumer.py") in found
    assert ("removed-assertions", "tests/test_consumer.py") in found
    assert not any(w == "src/consumer.py" for _, w in found)


def test_callsite_checker():
    assert problems('publisher.publish(T, o, key=o["id"])\n') == []
    assert any("legacy" in p for p in problems("emit_event(T, o)\n"))
    assert any("without key" in p for p in problems("publisher.publish(T, o)\n"))
    assert any("syntax" in p for p in problems("publisher.publish(T, o, key=(o)\n"))


def test_reviewer_keeps_evidenced_findings_and_drops_style():
    client = FakeClient([text(DEMO_REPLY)])
    findings = review(DEMO_SPEC, DEMO_DIFF, client)
    assert [f.category for f in findings] == ["requirement"]
    sent = client.calls[0]
    assert "<spec>" in sent["messages"][0]["content"] and "Do not report style" in sent["system"]


def test_reviewer_drops_findings_whose_evidence_is_not_in_the_diff():
    reply = json.dumps({"findings": [{"category": "correctness", "severity": "high", "file": "x.py",
                                      "line": 1, "claim": "race", "evidence": "lock.acquire()"}]})
    assert parse_findings(reply, DEMO_DIFF) == []


def test_reviewer_retries_once_on_non_json_then_fails():
    ok = FakeClient([text("Here are my thoughts..."), text('{"findings": []}')])
    assert review(DEMO_SPEC, DEMO_DIFF, ok) == []
    assert len(ok.calls) == 2
    bad = FakeClient([text("nope"), text("still nope")])
    with pytest.raises(ValueError):
        review(DEMO_SPEC, DEMO_DIFF, bad)


def test_migrate_demo_runs_offline(tmp_path, capsys):
    from migrate_demo import main as demo
    assert demo(["--keep", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    summary = json.loads(out[out.index("{"): out.rindex("}") + 1])
    assert summary["targets"] == 40
    assert summary["by_status"] == {"ok": 37, "agent_failed": 1, "verify_failed": 2}
    assert summary["claimed_ok_but_not_ok"] == 2
    assert summary["needed_retry"] == 1
