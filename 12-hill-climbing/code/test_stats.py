"""Stats checked against hand-computed and published values."""

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from stats import (
    Estimate, binomial_se, ci_halfwidth, clustered_se, design_effect, mcnemar, mean_se,
    min_detectable_effect, paired_bootstrap, paired_diff, required_n_for_margin,
    required_n_paired, required_n_two_proportions, sd_diff_from_correlation, unpaired_diff, z_for,
)


def test_z_for_95():
    assert z_for(0.05) == pytest.approx(1.959964, abs=1e-5)


def test_mean_se_hand_computed():
    e = mean_se([0, 1, 1, 1])  # mean .75, sample SD .5, SE .25
    assert e.mean == 0.75 and e.se == pytest.approx(0.25)
    lo, hi = e.ci()
    assert lo == pytest.approx(0.75 - 1.959964 * 0.25, abs=1e-5) and hi > e.mean


def test_eugene_yan_error_bars():
    # "200 samples and observe 3% defects ... roughly 3% +/- 2.4%"; 400 samples "+/- 1.7%"
    assert ci_halfwidth(0.03, 200) == pytest.approx(0.0236, abs=5e-4)
    assert ci_halfwidth(0.03, 400) == pytest.approx(0.0167, abs=5e-4)
    # halving the margin needs 4x the samples
    assert ci_halfwidth(0.03, 800) == pytest.approx(ci_halfwidth(0.03, 200) / 2)
    assert required_n_for_margin(0.03, 0.024) <= 200


def test_binomial_se():
    assert binomial_se(0.5, 100) == pytest.approx(0.05)


def test_clustered_se_hand_computed():
    # mean .5; cluster residual sums +1 and -1 -> var = 2/16, x G/(G-1) = 2 -> 0.25
    e = clustered_se([1, 1, 0, 0], ["a", "a", "b", "b"])
    assert e.se == pytest.approx(0.5)
    e0 = clustered_se([1, 1, 0, 0], ["a", "a", "b", "b"], small_sample=False)
    assert e0.se == pytest.approx(math.sqrt(2 / 16))


@given(st.lists(st.floats(0, 1, allow_nan=False), min_size=3, max_size=60))
@settings(max_examples=60, deadline=None)
def test_singleton_clusters_equal_naive(xs):
    """With one item per cluster and the G/(G-1) correction, clustered SE == naive SE exactly."""
    c = clustered_se(xs, list(range(len(xs))))
    assert c.se == pytest.approx(mean_se(xs).se, rel=1e-9, abs=1e-12)


def test_perfectly_correlated_clusters_inflate_by_sqrt_k():
    # 30 clusters of 9 identical scores: design effect ~ k = 9, SE ratio ~ 3 (the "over 3x" regime)
    rng = random.Random(0)
    xs, cl = [], []
    for c in range(30):
        v = float(rng.random() < 0.6)
        xs += [v] * 9
        cl += [c] * 9
    naive, clus = mean_se(xs), clustered_se(xs, cl, small_sample=False)
    assert clus.se / naive.se == pytest.approx(3.0, rel=0.05)
    assert design_effect(naive, clus) == pytest.approx(9.0, rel=0.1)


def test_paired_beats_unpaired_when_items_correlate():
    rng = random.Random(1)
    base = [rng.random() for _ in range(300)]  # item difficulty shared by both variants
    a = [float(rng.random() < b) for b in base]
    b = [float(rng.random() < min(1, x + 0.05)) for x in base]
    assert paired_diff(a, b).se < unpaired_diff(a, b).se
    assert paired_diff(a, b).mean == pytest.approx(unpaired_diff(a, b).mean)


def test_paired_diff_requires_alignment():
    with pytest.raises(ValueError):
        paired_diff([1, 0], [1])


def test_paired_bootstrap_agrees_with_normal_ci():
    rng = random.Random(2)
    a = [float(rng.random() < 0.7) for _ in range(400)]
    b = [x if rng.random() < 0.9 else 1.0 for x in a]
    lo, hi, p0 = paired_bootstrap(a, b, n_boot=2000, seed=3)
    e = paired_diff(a, b)
    assert lo == pytest.approx(e.lo, abs=0.01) and hi == pytest.approx(e.hi, abs=0.01)
    assert p0 < 0.01


def test_paired_bootstrap_resamples_clusters():
    a = [0.0] * 40
    b = [1.0] * 20 + [0.0] * 20
    cl = [i // 10 for i in range(40)]  # 4 clusters: two all-improved, two unchanged
    lo, hi, _ = paired_bootstrap(a, b, cl, n_boot=1000, seed=0)
    lo_i, hi_i, _ = paired_bootstrap(a, b, None, n_boot=1000, seed=0)
    assert (hi - lo) > 2 * (hi_i - lo_i)  # clustering widens the interval a lot


def test_mcnemar_exact_known_value():
    # b01=10, b10=2: p = 2 * P(X<=2 | n=12, .5) = 2 * 79 / 4096
    a = [0] * 10 + [1] * 2 + [1] * 50
    b = [1] * 10 + [0] * 2 + [1] * 50
    b01, b10, p = mcnemar(a, b)
    assert (b01, b10) == (10, 2)
    assert p == pytest.approx(158 / 4096)


def test_mcnemar_chi_square_known_value():
    a = [0] * 30 + [1] * 10
    b = [1] * 30 + [0] * 10
    _, _, p = mcnemar(a, b)  # chi2 = (|30-10|-1)^2 / 40 = 9.025 -> p = 0.00266
    assert p == pytest.approx(0.002663, abs=2e-5)


def test_mcnemar_no_discordant_pairs():
    assert mcnemar([1, 0, 1], [1, 0, 1])[2] == 1.0


def test_required_n_two_proportions_textbook():
    # 50% vs 60%, alpha .05 two-sided, power .8: 387.4 -> 388 per arm (no continuity correction)
    assert required_n_two_proportions(0.5, 0.6) == 388


def test_required_n_paired_hand_computed():
    # ((1.96 + 0.8416) * 0.3 / 0.05)^2 = 282.6 -> 283
    assert required_n_paired(0.05, 0.3) == 283


def test_pairing_cuts_required_n():
    sd = sd_diff_from_correlation(0.46, 0.43, 0.5)
    assert required_n_paired(0.05, sd) < required_n_two_proportions(0.70, 0.75)


def test_min_detectable_effect():
    assert min_detectable_effect(0.01) == pytest.approx(0.028, abs=1e-3)


def test_estimate_p_value_and_fmt():
    e = Estimate(0.05, 0.025, 100)
    assert e.p_value() == pytest.approx(0.0455, abs=1e-3)
    assert e.fmt() == "5.0 [0.1, 9.9]"
