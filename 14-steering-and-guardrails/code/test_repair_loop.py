from ainative_kit import FakeClient, Response, Tracer, text

from repair_loop import ALERT, PROMPT, demo_fake, repair_loop
from validators import TRIAGE_CHECKS, TRIAGE_SCHEMA, make_evidence_grounding_check

CHECKS = TRIAGE_CHECKS + [("evidence_grounded", make_evidence_grounding_check(ALERT))]


def test_feedback_loop_converges_and_feeds_errors_back():
    client = demo_fake()
    tracer = Tracer()
    r = repair_loop(client, PROMPT, TRIAGE_SCHEMA, CHECKS, max_attempts=3, tracer=tracer)
    assert r.ok and r.stop_reason == "valid" and len(r.attempts) == 3
    second_call = client.calls[1]["messages"]
    assert second_call[-2]["role"] == "assistant"
    feedback = second_call[-1]["content"]
    assert "$.severity: 'SEV1' is not one of" in feedback and "$.confidence: 85 is above maximum 1" in feedback
    third_call = client.calls[2]["messages"][-1]["content"]
    assert "evidence not found verbatim" in third_call
    root = [s for s in tracer.spans if s.name == "repair_loop"][0]
    assert root.attrs["stop_reason"] == "valid"


def test_blind_retry_resends_identical_prompt_and_stops_on_no_progress():
    bad = text('{"service": "x"}')
    client = FakeClient([bad, bad, bad])
    r = repair_loop(client, PROMPT, TRIAGE_SCHEMA, CHECKS, max_attempts=3, feedback=False)
    assert not r.ok and r.stop_reason == "no_progress" and len(r.attempts) == 2
    assert client.calls[0]["messages"] == client.calls[1]["messages"]


def test_max_attempts_bound():
    outputs = [text("not json"), text('{"service": 1}'), text("[]")]
    r = repair_loop(FakeClient(outputs), PROMPT, TRIAGE_SCHEMA, CHECKS, max_attempts=3)
    assert not r.ok and r.stop_reason == "max_attempts" and len(r.attempts) == 3


def test_truncation_is_reported_specifically():
    client = FakeClient([Response(text='{"service": "orders', stop_reason="max_tokens"), demo_fake()._script[2]])
    r = repair_loop(client, PROMPT, TRIAGE_SCHEMA, CHECKS, max_attempts=2, max_tokens=50)
    assert r.ok
    assert "truncated at max_tokens=50" in client.calls[1]["messages"][-1]["content"]


def test_semantic_checks_only_after_schema_passes():
    r = repair_loop(demo_fake(), PROMPT, TRIAGE_SCHEMA, CHECKS, max_attempts=1)
    kinds = {e.kind for e in r.attempts[0].errors}
    assert kinds == {"schema"}
