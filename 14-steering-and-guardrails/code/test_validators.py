import json

from validators import (
    TRIAGE_CHECKS,
    TRIAGE_SCHEMA,
    ValidationError,
    extract_json,
    format_errors_for_model,
    make_evidence_grounding_check,
    run_semantic_checks,
    validate,
)

GOOD = {
    "service": "orders-consumer",
    "severity": "sev2",
    "category": "consumer_lag",
    "affected_partitions": [1, 2],
    "summary": "Lag on orders.v2 grew past 500k after a slow downstream write.",
    "confidence": 0.7,
}


def test_valid_object_has_no_errors():
    assert validate(GOOD, TRIAGE_SCHEMA) == []
    assert run_semantic_checks(GOOD, TRIAGE_CHECKS) == []


def test_reports_all_errors_not_just_first():
    bad = dict(GOOD, severity="SEV1", confidence=85, summary="short")
    errs = validate(bad, TRIAGE_SCHEMA)
    paths = {e.path for e in errs}
    assert paths == {"$.severity", "$.confidence", "$.summary"}


def test_missing_and_extra_properties():
    bad = {k: v for k, v in GOOD.items() if k != "service"}
    bad["owner"] = "team-a"
    msgs = [str(e) for e in validate(bad, TRIAGE_SCHEMA)]
    assert "$.service: is required but missing" in msgs
    assert "$.owner: is not an allowed property" in msgs


def test_bool_is_not_an_integer_and_item_paths_are_precise():
    errs = validate(dict(GOOD, affected_partitions=[1, True, -3]), TRIAGE_SCHEMA)
    assert {e.path for e in errs} == {"$.affected_partitions[1]", "$.affected_partitions[2]"}


def test_type_mismatch_short_circuits_children():
    errs = validate(dict(GOOD, affected_partitions="4,5"), TRIAGE_SCHEMA)
    assert len(errs) == 1 and "expected type array" in errs[0].message


def test_pattern():
    errs = validate(dict(GOOD, runbook_url="http://wiki/x"), TRIAGE_SCHEMA)
    assert errs and "does not match pattern" in errs[0].message


def test_semantic_cross_field_rules():
    sev1 = dict(GOOD, severity="sev1")
    assert any("runbook_url" in e.message for e in run_semantic_checks(sev1, TRIAGE_CHECKS))
    unknown = dict(GOOD, category="unknown", confidence=0.9)
    assert any("contradictory" in e.message for e in run_semantic_checks(unknown, TRIAGE_CHECKS))
    dup = dict(GOOD, affected_partitions=[3, 3])
    assert [e.kind for e in run_semantic_checks(dup, TRIAGE_CHECKS)] == ["semantic"]


def test_evidence_grounding():
    check = make_evidence_grounding_check("line A\nline B happened")
    assert check({"evidence": ["line B happened"]}) == []
    assert check({"evidence": ["line C"]})


def test_extract_json_handles_fence_and_reports_position():
    obj, errs = extract_json('```json\n{"a": 1}\n```')
    assert obj == {"a": 1} and errs == []
    obj, errs = extract_json('Here you go: {"a": 1,}')
    assert obj is None and errs[0].kind == "parse" and "invalid JSON" in errs[0].message


def test_feedback_is_capped():
    errs = [ValidationError(f"$.f{i}", "bad") for i in range(15)]
    text = format_errors_for_model(errs, limit=10)
    assert text.count("\n") == 10 and "5 more" in text


def test_schema_is_plain_json():
    json.dumps(TRIAGE_SCHEMA)  # usable as a prompt or as output_config.format schema
