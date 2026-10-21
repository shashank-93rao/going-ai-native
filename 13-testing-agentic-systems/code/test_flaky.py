"""pass@k / pass^k math, and the flakiness report's separation of infra noise from agent failures."""

import pytest

from flaky import Trial, deploy_trial, flakiness_report, pass_at_k, pass_hat_k, run_suite, wilson
from world import FaultPlan


def test_pass_hat_k_matches_independent_trials_at_scale():
    # 75% per-trial success -> pass^3 ~ 0.42 (the Anthropic evals post's example)
    assert pass_hat_k(1000, 750, 3) == pytest.approx(0.75**3, abs=0.005)
    assert round(0.75**3, 2) == 0.42


def test_pass_at_k_and_pass_hat_k_bracket_pass_rate():
    n, c = 20, 15
    for k in (1, 3, 5):
        assert pass_hat_k(n, c, k) <= c / n <= pass_at_k(n, c, k) or k == 1
    assert pass_at_k(n, c, 1) == pass_hat_k(n, c, 1) == 0.75
    assert pass_hat_k(n, n, 5) == 1.0 and pass_at_k(n, 0, 5) == 0.0


def test_wilson_interval_is_sane_at_extremes():
    lo, hi = wilson(20, 20)
    assert hi == 1.0 and 0.8 < lo < 0.9  # 20/20 does NOT prove 100%
    lo, hi = wilson(0, 20)
    assert lo == 0.0 and hi < 0.2


def test_infra_errors_are_excluded_and_trigger_environment_verdict():
    trials = [Trial(i, "pass") for i in range(18)] + [Trial(18, "infra_error"), Trial(19, "infra_error")]
    r = flakiness_report(trials)
    assert (r.passes, r.fails, r.infra) == (18, 0, 2)
    assert r.verdict.startswith("ENVIRONMENT")


def test_verdicts():
    assert flakiness_report([Trial(i, "pass") for i in range(10)]).verdict == "STABLE"
    assert flakiness_report([Trial(i, "fail", ["x"]) for i in range(10)]).verdict.startswith("BROKEN")
    mixed = [Trial(i, "pass") for i in range(7)] + [Trial(i, "fail", ["x"]) for i in range(3)]
    assert flakiness_report(mixed).verdict.startswith("FLAKY: pass^3")


def test_end_to_end_report_on_noisy_agent():
    trial = deploy_trial(FaultPlan(0.15, 0.15, infra_crash_rate=0.02))
    no_retry = flakiness_report(run_suite(trial, range(40), retry_infra=False))
    with_retry = flakiness_report(run_suite(trial, range(40)))
    assert no_retry.infra > 0 and with_retry.infra == 0
    assert with_retry.fails == no_retry.fails  # retrying infra never hides a model failure
    assert 0 < with_retry.passes < 40
    assert with_retry.pass_hat[3] < with_retry.pass_hat[1]
    assert "transition failure matrix" in with_retry.render()
