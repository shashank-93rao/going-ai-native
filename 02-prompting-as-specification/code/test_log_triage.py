import json

from ainative_kit import FakeClient, Tracer, text

from log_triage import TRIAGE_SCHEMA, check, classify
from mini_schema import validate

EXCERPT = "2026-10-03T02:14:07Z orders-api pod orders-api-6c4d OOMKilled (limit 512Mi)"
GOOD = {
    "category": "infra", "severity": "page", "service": "orders-api",
    "summary": "orders-api was OOMKilled.", "evidence": [EXCERPT], "needs_human": False,
}


def test_schema_accepts_good_output():
    assert validate(GOOD, TRIAGE_SCHEMA) == []


def test_schema_rejects_bad_enum_extra_field_missing_field_and_bool_as_int():
    bad = dict(GOOD, severity="high", confidence=0.9)
    del bad["service"]
    errs = validate(bad, TRIAGE_SCHEMA)
    assert any("'high' is not one of" in e for e in errs)
    assert any("unexpected field 'confidence'" in e for e in errs)
    assert any("missing required field 'service'" in e for e in errs)
    assert validate(1, {"type": "boolean"}) and validate(True, {"type": "integer"})


def test_empty_evidence_violates_min_items():
    assert any("at least 1" in e for e in validate(dict(GOOD, evidence=[]), TRIAGE_SCHEMA))


def test_prose_around_json_is_a_contract_violation():
    obj, errs = check("Here is the triage:\n" + json.dumps(GOOD), EXCERPT)
    assert obj is None and "not a bare JSON object" in errs[0]


def test_semantic_checks_catch_what_schema_cannot():
    _, errs = check(json.dumps(dict(GOOD, evidence=["pod crashed because of a bad deploy"])), EXCERPT)
    assert any("not found verbatim" in e for e in errs)
    _, errs = check(json.dumps(dict(GOOD, category="unknown", needs_human=False)), EXCERPT)
    assert any("requires needs_human" in e for e in errs)
    _, errs = check(json.dumps(dict(GOOD, summary="x" * 201)), EXCERPT)
    assert any("limit is 200" in e for e in errs)


def test_truncated_or_refused_output_is_never_parsed():
    for reason in ("max_tokens", "refusal"):
        obj, errs = check(json.dumps(GOOD), EXCERPT, stop_reason=reason)
        assert obj is None and reason in errs[0]


def test_retry_feeds_errors_back_as_a_user_turn_not_a_prefill():
    client = FakeClient([text(json.dumps(dict(GOOD, severity="critical"))), text(json.dumps(GOOD))])
    tracer = Tracer()
    res = classify(client, "SYSTEM", EXCERPT, tracer=tracer, prompt_ref="log_triage@v2#abc")
    assert res.ok and res.attempts == 2 and res.output == GOOD
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]  # ends on user: no prefill
    assert "'critical' is not one of" in second[-1]["content"]
    assert tracer.spans[-1].attrs["prompt_ref"] == "log_triage@v2#abc"


def test_retry_budget_is_bounded():
    client = FakeClient([text("nope"), text("still nope")])
    res = classify(client, "SYSTEM", EXCERPT, retries=1)
    assert not res.ok and res.attempts == 2 and len(client.calls) == 2
    assert "not a bare JSON object" in res.errors[0]
