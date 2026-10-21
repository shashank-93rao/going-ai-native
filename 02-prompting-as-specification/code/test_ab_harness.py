from ainative_kit import FakeClient, Tracer

from ab_harness import VersionRun, RowResult, ab, compare, load_rows, mcnemar_exact, report
from sim_model import simulated_model


def run(ref, flags, valid=None):
    valid = valid or [True] * len(flags)
    return VersionRun(ref, [RowResult(f"r{i}", v, c, None, []) for i, (c, v) in enumerate(zip(flags, valid))])


def test_mcnemar_exact_known_values():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(2, 1) == 1.0
    assert abs(mcnemar_exact(6, 0) - 2 / 64) < 1e-12
    assert abs(mcnemar_exact(8, 1) - 2 * 10 / 512) < 1e-12
    assert mcnemar_exact(5, 5) == 1.0


def test_v1_to_v2_spec_rewrite_promotes():
    tracer = Tracer()
    c = ab(FakeClient(simulated_model), "log_triage", 1, 2, tracer=tracer)
    assert c.baseline.valid_rate == 0.0  # prose answers with an invented severity scale
    assert c.candidate.valid_rate == 1.0
    assert c.decision == "promote" and not c.losses
    refs = {s.attrs["prompt_ref"] for s in tracer.spans}
    assert any(r.startswith("log_triage@v1#") for r in refs) and any(r.startswith("log_triage@v2#") for r in refs)


def test_v3_wins_more_rows_but_is_rejected_for_must_pass_regression():
    c = ab(FakeClient(simulated_model), "log_triage", 2, 3)
    assert c.candidate.accuracy > c.baseline.accuracy
    assert set(c.wins) == {"kafka-lag", "upstream-timeout"}
    assert c.losses == ["idempotency"]
    assert c.decision == "reject" and "must_pass" in c.reasons[0]
    assert "REJECT" in report(c)


def test_small_positive_difference_is_inconclusive():
    rows = [{"id": f"r{i}"} for i in range(10)]
    base = run("a@v1", [True] * 7 + [False] * 3)
    cand = run("a@v2", [True] * 9 + [False] * 1)
    c = compare(base, cand, rows)
    assert c.decision == "inconclusive" and len(c.wins) == 2


def test_validity_drop_rejects_even_when_accuracy_rises():
    rows = [{"id": f"r{i}"} for i in range(4)]
    base = run("a@v1", [False, False, True, True], valid=[True, True, True, True])
    cand = run("a@v2", [True, True, True, True], valid=[True, True, True, False])
    assert compare(base, cand, rows).decision == "reject"


def test_eval_set_shape():
    rows = load_rows()
    assert len(rows) >= 15 and len({r["id"] for r in rows}) == len(rows)
    assert all({"category", "severity"} == set(r["expected"]) for r in rows)
    assert any(r["must_pass"] for r in rows)
