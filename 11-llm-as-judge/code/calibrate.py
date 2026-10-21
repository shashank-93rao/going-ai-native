"""Calibrate a binary judge against human labels, then correct its observed pass rate.

Convention: positive = PASS.
  TPR = P(judge says pass | human says pass)    (sensitivity to good outputs)
  TNR = P(judge says fail | human says fail)    (sensitivity to bad outputs: the one that usually matters)

Rogan-Gladen: if the judge reports an observed pass rate p_obs on unlabeled traffic,
the estimated true pass rate is

    theta = (p_obs + TNR - 1) / (TPR + TNR - 1)

valid only when TPR + TNR > 1 (the judge beats a coin). The bootstrap resamples
both the labeled test set (uncertainty in TPR/TNR) and the production verdicts
(uncertainty in p_obs), so the CI reflects both.

    python calibrate.py                                 # uses data/incident_judge_labels.jsonl
    python calibrate.py --labels my_labels.jsonl --prod my_prod_verdicts.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

DATA = Path(__file__).parent / "data"


@dataclass(frozen=True)
class Confusion:
    tp: int  # human pass, judge pass
    fn: int  # human pass, judge fail
    fp: int  # human fail, judge pass   <- the dangerous cell: bad output waved through
    tn: int  # human fail, judge fail

    @property
    def n(self) -> int:
        return self.tp + self.fn + self.fp + self.tn

    @property
    def tpr(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def tnr(self) -> float:
        return self.tn / (self.tn + self.fp) if self.tn + self.fp else float("nan")

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else float("nan")

    @property
    def kappa(self) -> float:
        """Cohen's kappa: agreement corrected for chance."""
        n = self.n
        if not n:
            return float("nan")
        po = self.accuracy
        pe = ((self.tp + self.fn) * (self.tp + self.fp) + (self.fp + self.tn) * (self.fn + self.tn)) / (n * n)
        return (po - pe) / (1 - pe) if pe != 1 else float("nan")

    def table(self) -> str:
        return (
            "                judge=pass  judge=fail\n"
            f"  human=pass    {self.tp:>9}  {self.fn:>10}\n"
            f"  human=fail    {self.fp:>9}  {self.tn:>10}"
        )


def confusion(human: Sequence[bool], judge: Sequence[bool]) -> Confusion:
    """Build a confusion matrix; True means PASS."""
    if len(human) != len(judge):
        raise ValueError("human and judge label lists differ in length")
    tp = sum(h and j for h, j in zip(human, judge))
    fn = sum(h and not j for h, j in zip(human, judge))
    fp = sum((not h) and j for h, j in zip(human, judge))
    tn = sum((not h) and (not j) for h, j in zip(human, judge))
    return Confusion(tp, fn, fp, tn)


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Behaves sanely at k=0, k=n and small n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rogan_gladen(p_obs: float, tpr: float, tnr: float, clip: bool = True) -> float:
    """Correct an observed pass rate for judge error. Raises if the judge is no better than chance."""
    youden = tpr + tnr - 1
    if youden <= 0:
        raise ValueError(f"TPR + TNR must exceed 1 (got {tpr:.3f} + {tnr:.3f}); the judge is not informative")
    theta = (p_obs + tnr - 1) / youden
    return min(1.0, max(0.0, theta)) if clip else theta


@dataclass(frozen=True)
class Estimate:
    point: float
    lo: float
    hi: float
    skipped: int = 0  # bootstrap resamples discarded as degenerate (no passes, no fails, or TPR+TNR<=1)


def bootstrap_true_pass_rate(
    human_test: Sequence[bool],
    judge_test: Sequence[bool],
    judge_prod: Sequence[bool],
    *,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Estimate:
    """Point estimate and percentile CI for the corrected true pass rate."""
    cm = confusion(human_test, judge_test)
    point = rogan_gladen(sum(judge_prod) / len(judge_prod), cm.tpr, cm.tnr)
    rng = random.Random(seed)
    pairs = list(zip(human_test, judge_test))
    prod = list(judge_prod)
    samples, skipped = [], 0
    for _ in range(n_boot):
        bt = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        bc = confusion([h for h, _ in bt], [j for _, j in bt])
        p_obs = sum(prod[rng.randrange(len(prod))] for _ in prod) / len(prod)
        if bc.tp + bc.fn == 0 or bc.tn + bc.fp == 0 or bc.tpr + bc.tnr <= 1:
            skipped += 1
            continue
        samples.append(rogan_gladen(p_obs, bc.tpr, bc.tnr))
    if not samples:
        raise ValueError("every bootstrap resample was degenerate; you need more labels")
    samples.sort()
    lo = samples[int((alpha / 2) * (len(samples) - 1))]
    hi = samples[int((1 - alpha / 2) * (len(samples) - 1))]
    return Estimate(point, lo, hi, skipped)


def assign_split(row_id: str, fractions: tuple[float, float, float] = (0.15, 0.40, 0.45)) -> str:
    """Stable train/dev/test assignment by hashing the id: adding rows never moves old ones."""
    h = int(hashlib.sha256(row_id.encode()).hexdigest(), 16) % 10_000 / 10_000
    return "train" if h < fractions[0] else ("dev" if h < fractions[0] + fractions[1] else "test")


def simulate_judge_verdicts(true_pass_rate: float, tpr: float, tnr: float, n: int, seed: int = 0) -> list[bool]:
    """Synthetic production verdicts from a judge with known error rates. For demos and tests only."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        good = rng.random() < true_pass_rate
        out.append(rng.random() < tpr if good else rng.random() >= tnr)
    return out


def drift_alarms(baseline: Confusion, recent: Confusion, min_per_class: int = 10) -> list[str]:
    """Compare TPR/TNR on a fresh human-labeled sample against the frozen calibration.

    Alarm when a recent rate falls below the baseline's Wilson lower bound. Deliberately
    simple: it is a tripwire that says "re-calibrate now", not a hypothesis test.
    """
    alarms = []
    for name, k_b, n_b, k_r, n_r in (
        ("TPR", baseline.tp, baseline.tp + baseline.fn, recent.tp, recent.tp + recent.fn),
        ("TNR", baseline.tn, baseline.tn + baseline.fp, recent.tn, recent.tn + recent.fp),
    ):
        if n_r < min_per_class:
            alarms.append(f"{name}: only {n_r} recent labels in this class (need {min_per_class}); label more")
            continue
        lo, _ = wilson_interval(k_b, n_b)
        if k_r / n_r < lo:
            alarms.append(f"{name} drifted: recent {k_r / n_r:.2f} < baseline lower bound {lo:.2f}")
    return alarms


def _as_bool(label: str) -> bool:
    if label not in ("pass", "fail"):
        raise ValueError(f"label must be 'pass' or 'fail', got {label!r} (exclude judge errors explicitly)")
    return label == "pass"


def report(rows: list[dict[str, Any]], prod: list[bool], split: str = "test") -> str:
    """Human-readable calibration report for one split, plus the corrected production estimate."""
    use = [r for r in rows if r["split"] == split and r["judge_label"] in ("pass", "fail")]
    errors = sum(1 for r in rows if r["split"] == split and r["judge_label"] not in ("pass", "fail"))
    h = [_as_bool(r["human_label"]) for r in use]
    j = [_as_bool(r["judge_label"]) for r in use]
    cm = confusion(h, j)
    tpr_ci = wilson_interval(cm.tp, cm.tp + cm.fn)
    tnr_ci = wilson_interval(cm.tn, cm.tn + cm.fp)
    p_obs = sum(prod) / len(prod)
    est = bootstrap_true_pass_rate(h, j, prod)
    return "\n".join([
        f"split={split}  n={cm.n}  judge errors excluded={errors}",
        cm.table(),
        f"TPR {cm.tpr:.2f}  95% CI [{tpr_ci[0]:.2f}, {tpr_ci[1]:.2f}]",
        f"TNR {cm.tnr:.2f}  95% CI [{tnr_ci[0]:.2f}, {tnr_ci[1]:.2f}]",
        f"accuracy {cm.accuracy:.2f}  kappa {cm.kappa:.2f}",
        f"production: n={len(prod)}  observed pass rate {p_obs:.3f}",
        f"corrected true pass rate {est.point:.3f}  95% CI [{est.lo:.3f}, {est.hi:.3f}]  (skipped {est.skipped} degenerate resamples)",
    ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(DATA / "incident_judge_labels.jsonl"))
    ap.add_argument("--prod", default=None, help="JSONL with a judge_label per row; default: simulated stream")
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    rows = [json.loads(line) for line in Path(args.labels).read_text().splitlines() if line.strip()]
    if args.prod:
        prod = [_as_bool(json.loads(line)["judge_label"]) for line in Path(args.prod).read_text().splitlines() if line.strip()]
    else:
        # Simulated: 500 production items, 70% truly good, judged by a judge with the TPR/TNR we just measured.
        use = [r for r in rows if r["split"] == args.split and r["judge_label"] in ("pass", "fail")]
        cm = confusion([_as_bool(r["human_label"]) for r in use], [_as_bool(r["judge_label"]) for r in use])
        prod = simulate_judge_verdicts(0.70, cm.tpr, cm.tnr, 500, seed=7)
        print("(production verdicts are SIMULATED: true pass rate 0.70, n=500)")
    print(report(rows, prod, args.split))


if __name__ == "__main__":
    main()
