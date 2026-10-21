import json
import random
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from calibrate import (Confusion, assign_split, drift_alarms, bootstrap_true_pass_rate, confusion, report, rogan_gladen,
                       simulate_judge_verdicts, wilson_interval, _as_bool)

DATA = Path(__file__).parent / "data"


def test_confusion_cells_and_rates():
    human = [True, True, True, True, False, False, False, False]
    judge = [True, True, True, False, True, False, False, False]
    cm = confusion(human, judge)
    assert (cm.tp, cm.fn, cm.fp, cm.tn) == (3, 1, 1, 3)
    assert cm.tpr == 0.75 and cm.tnr == 0.75 and cm.accuracy == 0.75
    assert cm.kappa == pytest.approx(0.5)


def test_accuracy_hides_a_useless_judge_on_imbalanced_data():
    # 95% of outputs are good; a judge that always says PASS is 95% "accurate" and catches nothing.
    human = [True] * 95 + [False] * 5
    cm = confusion(human, [True] * 100)
    assert cm.accuracy == 0.95
    assert cm.tnr == 0.0
    assert cm.kappa == pytest.approx(0.0)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        confusion([True], [True, False])


def test_wilson_interval_edges():
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and 0.2 < hi < 0.35
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0 and 0.65 < lo < 0.8
    lo, hi = wilson_interval(45, 50)
    assert lo < 0.9 < hi
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_rogan_gladen_worked_example():
    # TPR 0.92, TNR 0.88, observed 80% passes -> about 85% truly passing.
    assert rogan_gladen(0.80, 0.92, 0.88) == pytest.approx(0.85)


def test_rogan_gladen_rejects_uninformative_judge_and_clips():
    with pytest.raises(ValueError):
        rogan_gladen(0.5, 0.6, 0.4)
    assert rogan_gladen(0.05, 0.9, 0.9) == 0.0
    assert rogan_gladen(0.05, 0.9, 0.9, clip=False) < 0


@settings(max_examples=200, deadline=None)
@given(theta=st.floats(0, 1), tpr=st.floats(0.55, 1), tnr=st.floats(0.55, 1))
def test_rogan_gladen_inverts_the_measurement_model(theta, tpr, tnr):
    p_obs = tpr * theta + (1 - tnr) * (1 - theta)
    assert rogan_gladen(p_obs, tpr, tnr) == pytest.approx(theta, abs=1e-9)


def _labeled(n, tpr, tnr, seed):
    rng = random.Random(seed)
    human = [rng.random() < 0.5 for _ in range(n)]
    judge = [(rng.random() < tpr) if h else (rng.random() >= tnr) for h in human]
    return human, judge


def test_bootstrap_ci_covers_truth_and_raw_rate_is_biased():
    human, judge = _labeled(200, 0.85, 0.75, seed=1)
    prod = simulate_judge_verdicts(0.60, 0.85, 0.75, 2000, seed=2)
    raw = sum(prod) / len(prod)
    est = bootstrap_true_pass_rate(human, judge, prod, n_boot=500, seed=3)
    assert est.lo <= 0.60 <= est.hi
    assert abs(raw - 0.60) > abs(est.point - 0.60)  # correction moves us toward the truth


def test_more_labels_narrow_the_interval():
    prod = simulate_judge_verdicts(0.70, 0.85, 0.75, 1000, seed=5)
    small = bootstrap_true_pass_rate(*_labeled(30, 0.85, 0.75, seed=6), prod, n_boot=400, seed=0)
    big = bootstrap_true_pass_rate(*_labeled(300, 0.85, 0.75, seed=6), prod, n_boot=400, seed=0)
    assert (big.hi - big.lo) < (small.hi - small.lo)


def test_bootstrap_is_deterministic_given_seed():
    human, judge = _labeled(60, 0.9, 0.8, seed=9)
    prod = simulate_judge_verdicts(0.5, 0.9, 0.8, 300, seed=9)
    assert bootstrap_true_pass_rate(human, judge, prod, n_boot=200, seed=4) == \
        bootstrap_true_pass_rate(human, judge, prod, n_boot=200, seed=4)


def test_assign_split_is_stable_and_roughly_proportional():
    ids = [f"row-{i}" for i in range(4000)]
    splits = [assign_split(i) for i in ids]
    assert splits == [assign_split(i) for i in ids]
    frac = {s: splits.count(s) / len(ids) for s in ("train", "dev", "test")}
    assert frac["train"] == pytest.approx(0.15, abs=0.03)
    assert frac["dev"] == pytest.approx(0.40, abs=0.03)
    assert frac["test"] == pytest.approx(0.45, abs=0.03)


def test_judge_errors_are_not_silently_counted():
    with pytest.raises(ValueError):
        _as_bool("error")


def test_report_on_committed_labels():
    rows = [json.loads(line) for line in (DATA / "incident_judge_labels.jsonl").read_text().splitlines()]
    prod = simulate_judge_verdicts(0.7, 0.85, 0.75, 300, seed=1)
    out = report(rows, prod, "test")
    assert "TPR" in out and "TNR" in out and "corrected true pass rate" in out
    assert "n=25" in out


def test_drift_alarms():
    baseline = Confusion(tp=85, fn=15, fp=25, tn=75)          # TPR 0.85, TNR 0.75
    assert drift_alarms(baseline, Confusion(tp=17, fn=3, fp=5, tn=15)) == []
    alarms = drift_alarms(baseline, Confusion(tp=17, fn=3, fp=10, tn=10))  # TNR fell to 0.50
    assert len(alarms) == 1 and alarms[0].startswith("TNR drifted")
    assert "label more" in drift_alarms(baseline, Confusion(tp=17, fn=3, fp=1, tn=2))[0]
