import random

from canary import Arm, decide, decide_paired, diff_ci, mcnemar_exact, required_n_per_arm, two_proportion_z


def test_two_proportion_direction():
    z, p = two_proportion_z(Arm(950, 1000), Arm(900, 1000))
    assert z < 0 and p < 0.001
    z, p = two_proportion_z(Arm(900, 1000), Arm(950, 1000))
    assert z > 0 and p > 0.99


def test_mcnemar_exact_known_values():
    assert mcnemar_exact(0, 0) == 1.0
    assert abs(mcnemar_exact(5, 0) - 1 / 32) < 1e-12
    assert mcnemar_exact(3, 3) > 0.5


def test_required_n_grows_as_margin_shrinks():
    assert required_n_per_arm(0.95, 0.01) > 3.9 * required_n_per_arm(0.95, 0.02)


def test_decisions():
    assert decide(Arm(950, 1000), Arm(880, 1000)).action == "ROLLBACK"
    assert decide(Arm(95, 100), Arm(95, 100)).action == "CONTINUE"  # too few samples
    assert decide(Arm(2850, 3000), Arm(2853, 3000), margin=0.02).action == "PROMOTE"
    assert decide(Arm(2850, 3000), Arm(2853, 3000), guardrails={"secret_leak": True}).action == "ROLLBACK"


def test_more_looks_is_more_conservative():
    c, k = Arm(1900, 2000), Arm(1872, 2000)
    assert decide(c, k, looks=1).action == "ROLLBACK"
    assert decide(c, k, looks=5).action != "ROLLBACK"


def test_ci_contains_true_difference_most_of_the_time():
    rng, hits = random.Random(3), 0
    for _ in range(300):
        c = Arm(sum(rng.random() < 0.9 for _ in range(800)), 800)
        k = Arm(sum(rng.random() < 0.88 for _ in range(800)), 800)
        lo, _ = diff_ci(c, k, alpha=0.05)
        hits += lo <= -0.02
    assert hits / 300 > 0.9  # one-sided 95% bound


def test_paired_detects_what_unpaired_misses():
    # 500 identical inputs replayed through both configs: 14 regressions, 3 fixes.
    pairs = [(True, True)] * 380 + [(True, False)] * 14 + [(False, True)] * 3 + [(False, False)] * 103
    assert decide_paired(pairs).action == "ROLLBACK"
    control, canary = Arm(394, 500), Arm(383, 500)  # same marginals, analysed as independent samples
    assert decide(control, canary, min_n=400).action != "ROLLBACK"
