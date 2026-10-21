import math

import pytest
from ainative_kit import FakeClient, text
from online_eval import (CODE_CHECKS, LLMJudge, Threshold, burn_rate, burn_rate_alerts, compute_slis,
                         corrected_pass_rate, evaluate_thresholds, in_sample, review_queue, run_checks,
                         select_for_judge, summarize, wilson)
from prod_fixtures import generate, group


def rows(**kw):
    return [summarize(s) for s in group(generate(**kw)).values()]


def test_summarize_reads_usage_and_feedback():
    r = rows(n=5)[0]
    assert r.model == "claude-sonnet-5-5" and r.prompt_version == "v14"
    assert r.cache_read_tokens + r.cache_write_tokens == 6000
    assert r.cost_usd > 0 and r.latency_s > 0


def test_consistent_sampling_is_stable_and_close_to_rate():
    ids = [f"t{i}" for i in range(5000)]
    a = [i for i in ids if in_sample(i, 0.1)]
    assert a == [i for i in ids if in_sample(i, 0.1)]  # deterministic
    assert 400 < len(a) < 600
    assert set(a) != {i for i in ids if in_sample(i, 0.1, salt="other")}


def test_code_checks_catch_each_bad_output():
    rs = rows(n=400, bad_rate=0.5)
    res = run_checks(rs, CODE_CHECKS)
    for r in rs:
        out = res[r.trace_id]
        if r.output.startswith("Sure!"):
            assert out["schema_valid"] is False and out["grounded_service"] is None
        if "billing-legacy" in r.output:
            assert out["grounded_service"] is False
        if "sk-ant-" in r.output:
            assert out["no_secret_in_output"] is False


def test_wilson_and_correction():
    lo, hi = wilson(0, 10)
    assert lo == 0 and 0.25 < hi < 0.32
    assert corrected_pass_rate(0.9 * 0.9 + 0.2 * 0.1, tpr=0.9, tnr=0.8) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        corrected_pass_rate(0.5, 0.5, 0.5)


def test_judge_parses_and_unknown_is_none():
    r = rows(n=1)[0]
    assert LLMJudge(FakeClient([text("PASS\nfaithful")]), "rubric")(r) is True
    assert LLMJudge(FakeClient([text("fail")]), "rubric")(r) is False
    assert LLMJudge(FakeClient([text("I think it is fine")]), "rubric")(r) is None


def test_slis_and_threshold_alerts_fire_on_cache_regression():
    healthy, broken = rows(n=300), rows(n=300, cache_hit=0.1, seed=8)
    s_ok = compute_slis(healthy, run_checks(healthy, CODE_CHECKS))
    s_bad = compute_slis(broken, run_checks(broken, CODE_CHECKS))
    assert s_ok["cache_hit_rate"].value > 0.85 > s_bad["cache_hit_rate"].value
    assert s_bad["cost_per_request_usd"].value > 1.5 * s_ok["cost_per_request_usd"].value
    rule = [Threshold("cache_hit_rate", ">=", 0.85, use_bound=False)]
    assert evaluate_thresholds(s_ok, rule) == []
    assert [a.sli for a in evaluate_thresholds(s_bad, rule)] == ["cache_hit_rate"]


def test_threshold_respects_min_n_and_ci():
    few = rows(n=10, bad_rate=0.5)
    slis = compute_slis(few, run_checks(few, CODE_CHECKS))
    assert evaluate_thresholds(slis, [Threshold("schema_valid", ">=", 0.99, min_n=30)]) == []


def test_judge_sli_is_corrected():
    rs = rows(n=200)
    judged = {r.trace_id: True for r in select_for_judge(rs, 0.5)}
    judge = LLMJudge(FakeClient([]), "r", tpr=0.9, tnr=0.9)
    s = compute_slis(rs, run_checks(rs, CODE_CHECKS), judged, judge)["judge_faithful"]
    assert s.raw == 1.0 and s.value == 1.0  # clipped
    assert not math.isnan(s.lo)


def test_review_queue_contains_negative_feedback():
    rs = rows(n=300)
    q = set(review_queue(rs, run_checks(rs, CODE_CHECKS)))
    assert all(r.trace_id in q for r in rs if r.feedback == -1)


def test_burn_rate_multiwindow():
    now = 100_000.0
    good = [(now - 7200 + i * 10, True) for i in range(720)]
    assert burn_rate(good, now - 3600, now, 0.99)[0] == 0
    # last 20 minutes: 60% bad against a 99% objective
    bad = [(now - 1200 + i * 10, i % 10 >= 6) for i in range(120)]
    events = [e for e in good if e[0] < now - 1200] + bad
    alerts = burn_rate_alerts("schema_valid", events, 0.99, now)
    assert any(a.severity == "page" for a in alerts)
    # after a rollback, the short window recovers and the page clears even though the hour is still bad
    recovered = events + [(now + i * 10, True) for i in range(40)]
    assert not any(a.severity == "page" and "1h" in a.message
                   for a in burn_rate_alerts("schema_valid", recovered, 0.99, now + 400))
