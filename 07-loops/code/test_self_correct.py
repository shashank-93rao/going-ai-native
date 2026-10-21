"""Generate-verify-fix tests: the verifier, the loop, and the measurement harness."""

import json

from ainative_kit import FakeClient, text
from self_correct import generate_verify_fix, measure, scripted_model, verify_policy

GOOD = json.dumps({"name": "t", "capacity": 20, "refill_per_sec": 5, "burst": 20})


def test_verifier_gives_specific_errors():
    assert verify_policy(GOOD, {"rps": 5}) == []
    assert verify_policy("sure! here you go", {}) == ["no JSON object found in reply"]
    bad = json.dumps({"name": "t", "capacity": 20, "refill_per_sec": 4, "burst": 40})
    assert verify_policy(bad, {"rps": 5}) == ["burst 40 > capacity 20", "refill_per_sec is 4, requirement says 5"]


def test_passes_first_try_uses_zero_fix_rounds():
    a = generate_verify_fix(FakeClient([text(GOOD)]), "t", {"rps": 5})
    assert a.passed_at_round == 0 and a.rounds_used == 0


def test_external_feedback_names_the_error():
    fake = FakeClient(scripted_model)
    a = generate_verify_fix(fake, "t", {"rps": 5}, mode="external")
    assert a.passed_at_round == 1
    assert "burst 40 > capacity 20" in fake.calls[1]["messages"][-1]["content"]


def test_round_cap_is_respected():
    fake = FakeClient(scripted_model)
    a = generate_verify_fix(fake, "t", {"rps": 5}, mode="intrinsic", max_rounds=3)
    assert a.passed_at_round is None and len(fake.calls) == 4


def test_measure_reports_curves_and_cost():
    cases = [(f"t{i}", {"rps": 5 + i}) for i in range(4)]
    rep = measure(lambda: FakeClient(scripted_model), cases, max_rounds=2)
    assert rep["external"]["pass_rate_by_round"] == [0.0, 1.0, 1.0]
    assert rep["intrinsic"]["pass_rate_by_round"] == [0.0, 0.0, 0.0]
    assert rep["intrinsic"]["mean_tokens"] > rep["external"]["mean_tokens"]  # paid more, got nothing
