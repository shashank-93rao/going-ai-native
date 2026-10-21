"""Tests for the worked examples: incident summary, dependency audit, SQL optimizer."""

import json
from pathlib import Path

import pytest

from ainative_kit import FakeClient, Response, text
from dependency_audit import audit, fake_audit_model, version_tuple
from incident_summary import (duration_minutes, fake_incident_model, summarize_incident, summary_gate,
                              timeline_gate)
from patterns import GateFailed
from sql_optimizer import (ATTEMPT_BOUNDARY, ATTEMPT_FANOUT, ATTEMPT_FIXED, REFERENCE_SQL, SqlChecker, make_db,
                           optimize_sql, run_limited)

DATA = Path(__file__).parent / "data"
INCIDENTS = [json.loads(l) for l in (DATA / "incidents.jsonl").read_text().splitlines()]


# --------------------------------------------------------------------------- incident summary

@pytest.mark.parametrize("inc,label,minutes", [(INCIDENTS[0], "database", 12), (INCIDENTS[1], "deploy", 5),
                                               (INCIDENTS[2], "capacity", 41)])
def test_incident_routes_and_summarizes(inc, label, minutes):
    fake = FakeClient(fake_incident_model)
    out = summarize_incident(fake, inc["log"])
    assert out["route"] == label and not out["fell_back"]
    assert f"Duration: {minutes} minutes" in out["summary"]
    assert fake.calls[0]["model"] == "claude-haiku-5-5"          # the router uses the cheap model


def test_route_specific_prompt_is_used():
    fake = FakeClient(fake_incident_model)
    summarize_incident(fake, INCIDENTS[0]["log"])
    assert "replication lag" in fake.calls[1]["system"]


def test_timeline_gate_catches_invented_timestamp():
    ctx = {"log": INCIDENTS[1]["log"]}
    bad = json.dumps({"services": ["checkout-svc"], "timeline": [{"ts": "2026-10-16T15:05:00Z", "event": "x"}]})
    assert "not present in the log" in timeline_gate(bad, ctx)
    unsorted = json.dumps({"services": ["checkout-svc"], "timeline": [
        {"ts": "2026-10-16T15:12:00Z", "event": "b"}, {"ts": "2026-10-16T15:02:11Z", "event": "a"}]})
    assert "chronological" in timeline_gate(unsorted, ctx)
    assert "not valid JSON" in timeline_gate("Sure! Here is the timeline", ctx)


def test_summary_gate_catches_missing_service_and_invented_time():
    ctx = {"timeline": json.dumps({"services": ["notify-svc"], "timeline": [{"ts": "2026-10-18T09:40:00Z"}]})}
    assert "notify-svc" in summary_gate("Impact: lag. Duration: 41 minutes", ctx)
    assert "not in the timeline" in summary_gate("notify-svc Duration: x at 2026-10-18T09:45:00Z", ctx)
    assert summary_gate("notify-svc lag. Duration: 41 minutes", ctx) is None


def test_gate_failure_is_retried_with_reason_then_raises():
    hallucinating = json.dumps({"services": ["checkout-svc"], "timeline": [{"ts": "2026-01-01T00:00:00Z", "event": "x"}]})
    fake = FakeClient([text("deploy"), text(hallucinating), text(hallucinating)])
    with pytest.raises(GateFailed) as e:
        summarize_incident(fake, INCIDENTS[1]["log"])
    assert e.value.step == "timeline"
    assert "not present in the log" in fake.calls[2]["messages"][0]["content"]


def test_duration_is_code_not_model():
    assert duration_minutes(INCIDENTS[2]["log"]) == 41
    assert duration_minutes("no paging data") is None


# --------------------------------------------------------------------------- dependency audit

def test_audit_finds_exactly_the_vulnerable_pins():
    out = audit(FakeClient(fake_audit_model))
    got = {(f.repo, f.package) for f in out["findings"]}
    assert got == {("payments-svc", "requests"), ("payments-svc", "cryptography"), ("ledger-svc", "golang.org/x/net"),
                   ("notify-svc", "express"), ("web-portal", "jinja2")}
    assert out["manifests_audited"] == 5
    assert ("notify-svc", "axios") not in got          # 1.6.0 is the fixed version: boundary is exclusive


def test_audit_drops_bad_and_excess_subtasks():
    plan = {"subtasks": [{"repo": "payments-svc", "manifest": "requirements.txt", "ecosystem": "pypi"},
                         {"repo": "../../etc", "manifest": "passwd", "ecosystem": "pypi"},
                         {"repo": "ledger-svc", "manifest": "go.mod", "ecosystem": "npm"},
                         {"repo": "ghost-svc", "manifest": "go.mod", "ecosystem": "go"}]}

    def responder(m, kw):
        return Response(text=json.dumps(plan)) if kw["system"].startswith("You plan") else fake_audit_model(m, kw)
    out = audit(FakeClient(responder))
    assert out["manifests_audited"] == 1 and len(out["dropped_subtasks"]) == 3


def test_audit_drops_ungrounded_worker_output():
    def responder(m, kw):
        if kw["system"].startswith("You read") and "fastapi" in m[-1]["content"]:
            return Response(text=json.dumps([{"name": "requests", "version": "2.31.0"},
                                             {"name": "urllib3", "version": "1.26.0"}]))
        return fake_audit_model(m, kw)
    out = audit(FakeClient(responder))
    assert any("urllib3" in w for w in out["warnings"])


def test_version_tuple():
    assert version_tuple("v0.19.0") < version_tuple("0.23.0")
    assert version_tuple("^1.6.0") == (1, 6, 0)


# --------------------------------------------------------------------------- SQL evaluator-optimizer

@pytest.fixture
def checker():
    return SqlChecker(make_db(7), make_db(1009))


def test_reference_is_correct_and_checker_passes_it(checker):
    assert checker(REFERENCE_SQL).ok


def test_checker_rejects_writes_and_multiple_statements(checker):
    assert not checker("DELETE FROM orders").ok
    assert not checker("SELECT 1; DROP TABLE orders").ok


def test_checker_returns_sqlite_error_as_feedback(checker):
    v = checker("SELECT region FROM customerz")
    assert not v.ok and "no such table: customerz" in v.feedback


def test_checker_flags_fanout_and_boundary_bugs(checker):
    assert "too high" in checker(ATTEMPT_FANOUT).feedback
    assert "too low" in checker(ATTEMPT_BOUNDARY).feedback
    assert checker(ATTEMPT_FIXED).ok


def test_hardcoded_answer_fails_on_hidden_fixture(checker):
    _, rows = run_limited(make_db(7), REFERENCE_SQL)
    hardcoded = " UNION ALL ".join(
        f"SELECT '{r}' AS region, {n} AS order_count, {v} AS revenue_cents" for r, n, v in rows)
    v = checker(f"SELECT * FROM ({hardcoded}) ORDER BY revenue_cents DESC")
    assert not v.ok and "hidden" in v.feedback


def test_checker_enforces_cost_budget(checker):
    explode = ("SELECT 'x' AS region, COUNT(*) AS order_count, 0 AS revenue_cents FROM order_items a, "
               "order_items b, order_items c, order_items d")
    v = checker(explode)
    assert not v.ok and "budget" in v.feedback


def test_optimizer_loop_feeds_feedback_and_converges():
    fake = FakeClient([Response(text=s) for s in (ATTEMPT_FANOUT, ATTEMPT_BOUNDARY, "```sql\n" + ATTEMPT_FIXED + "\n```")])
    res = optimize_sql(fake)
    assert res.stopped_by == "passed" and len(res.attempts) == 3
    assert "too high" in fake.calls[1]["messages"][0]["content"]
    assert "too low" in fake.calls[2]["messages"][0]["content"]
