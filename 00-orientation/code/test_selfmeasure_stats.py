import math

import pytest

from selfmeasure_log import fold, read_events
import random

from selfmeasure_stats import (
    bootstrap_ratio_ci, mde_ratio, n_needed, permutation_p, render, summarize, t_quantile_975, welch_ratio_ci,
)
from simulate_ab import simulate


def summary_for(tmp_path, **kw):
    log = simulate(tmp_path / "sim.jsonl", **kw)
    return summarize(fold(read_events(log)), outcome="active")


def test_recovers_planted_slowdown(tmp_path):
    s = summary_for(tmp_path, n_tasks=80, true_ratio=1.19, noise_sd=0.3)
    assert s.time_adjusted.ci[0] < 1.19 < s.time_adjusted.ci[1]
    assert s.time_adjusted.ratio > 1.0


def test_null_effect_ci_covers_one(tmp_path):
    s = summary_for(tmp_path, n_tasks=60, true_ratio=1.0)
    assert s.time_adjusted.ci[0] < 1.0 < s.time_adjusted.ci[1]


def test_adjustment_tightens_ci(tmp_path):
    # Size buckets vary 10x; the pre-assignment estimate absorbs that variance.
    s = summary_for(tmp_path, n_tasks=60, true_ratio=0.7, noise_sd=0.3)
    width = lambda e: math.log(e.ci[1]) - math.log(e.ci[0])
    assert width(s.time_adjusted) < width(s.time)


def test_perception_gap_is_visible(tmp_path):
    s = summary_for(tmp_path, n_tasks=40, true_ratio=1.19, perceived_ratio=0.80)
    assert s.perceived_ratio == pytest.approx(0.80, rel=0.1)
    assert s.time_adjusted.ratio > s.perceived_ratio


def test_rework_counts_against_ai_arm(tmp_path):
    s = summary_for(tmp_path, n_tasks=80, true_ratio=1.0, rework_p={"ai": 0.9, "no_ai": 0.0})
    assert s.arms["ai"]["rework_rate"] > 0.6 and s.arms["no_ai"]["rework_rate"] == 0
    assert s.time_with_rework.ratio > s.time_adjusted.ratio


def test_differential_abandonment_warns(tmp_path):
    s = summary_for(tmp_path, n_tasks=60, abandon_p={"ai": 0.0, "no_ai": 0.3})
    assert any("abandon rates differ" in w for w in s.warnings)
    assert s.arms["no_ai"]["completion_rate"] < 1.0


def test_small_n_warns_and_tiny_n_refuses(tmp_path):
    s = summary_for(tmp_path, n_tasks=10)
    assert any("treat the estimate as a direction" in w for w in s.warnings)
    s2 = summary_for(tmp_path, n_tasks=2)
    assert s2.time is None and s2.warnings


def test_permutation_p_extremes():
    a, b = [10.0] * 8, [100.0] * 8
    assert permutation_p(a, b, n_perm=999) < 0.01
    assert permutation_p([10.0, 20, 30, 40], [10.0, 20, 30, 40], n_perm=999) > 0.9


def test_bootstrap_ci_contains_point_estimate():
    a, b = [12.0, 15, 9, 20, 11], [20.0, 25, 18, 30, 22]
    lo, hi = bootstrap_ratio_ci(a, b, n_boot=1000)
    point = math.exp(sum(map(math.log, a)) / 5 - sum(map(math.log, b)) / 5)
    assert lo <= point <= hi


def test_power_helpers_are_consistent():
    sd = 0.5
    n = n_needed(sd, 0.8)
    assert mde_ratio(sd, n) >= 0.8 - 1e-9  # at n_needed, a 20% effect is detectable
    assert mde_ratio(sd, n - 5) < 0.8
    assert n_needed(1.0, 0.8) > n_needed(0.5, 0.8)


def test_render_mentions_key_lines(tmp_path):
    s = summary_for(tmp_path, n_tasks=30, true_ratio=1.19)
    out = render(s)
    for needle in ("Unadjusted", "Estimate-adjusted", "incl. rework", "Perceived ratio", "Detectable"):
        assert needle in out


def test_t_quantile_matches_tables():
    assert t_quantile_975(5) == pytest.approx(2.571, abs=0.01)
    assert t_quantile_975(20) == pytest.approx(2.086, abs=0.005)
    assert t_quantile_975(1e6) == pytest.approx(1.96, abs=0.001)


def test_welch_ci_has_nominal_coverage():
    rng = random.Random(1)
    true = 1.19
    hits = 0
    for _ in range(400):
        a = [math.exp(rng.gauss(math.log(true), 0.5)) for _ in range(20)]
        b = [math.exp(rng.gauss(0, 0.5)) for _ in range(20)]
        lo, hi = welch_ratio_ci(a, b)
        hits += lo <= true <= hi
    assert 0.92 <= hits / 400 <= 0.98
