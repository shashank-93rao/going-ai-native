"""Eval statistics that keep a hill-climb honest. Standard library only.

Everything here works on per-item scores: one float per eval item (0/1 for a
binary grader, or the mean over k repeats of that item). Formulas follow
Evan Miller, "Adding Error Bars to Evals" (arXiv 2411.00640), which Anthropic
published as "A statistical approach to model evaluations".

    mean_se(xs)                  -> Estimate(mean, se)
    clustered_se(xs, clusters)   -> Estimate with cluster-robust SE
    paired_diff(a, b, clusters)  -> Estimate of mean(b - a)
    paired_bootstrap(a, b, ...)  -> (lo, hi, p_le_zero)
    mcnemar(a, b)                -> (b01, b10, p_value)
    ci_halfwidth / required_n_*  -> sample-size and power math
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist
from typing import Hashable, Sequence

_N = NormalDist()


def z_for(alpha: float = 0.05) -> float:
    """Two-sided critical value: z_for(0.05) == 1.96."""
    return _N.inv_cdf(1 - alpha / 2)


@dataclass(frozen=True)
class Estimate:
    mean: float
    se: float
    n: int

    def ci(self, alpha: float = 0.05) -> tuple[float, float]:
        h = z_for(alpha) * self.se
        return (self.mean - h, self.mean + h)

    @property
    def lo(self) -> float:
        return self.ci()[0]

    @property
    def hi(self) -> float:
        return self.ci()[1]

    def p_value(self) -> float:
        """Two-sided p-value for H0: true mean == 0 (normal approximation)."""
        if self.se == 0:
            return 0.0 if self.mean != 0 else 1.0
        return 2 * (1 - _N.cdf(abs(self.mean) / self.se))

    def fmt(self, pct: bool = True) -> str:
        k = 100 if pct else 1
        lo, hi = self.ci()
        return f"{self.mean * k:.1f} [{lo * k:.1f}, {hi * k:.1f}]"


def mean_se(xs: Sequence[float]) -> Estimate:
    """Mean and naive standard error, SE = s / sqrt(n) with the n-1 sample SD."""
    n = len(xs)
    if n == 0:
        raise ValueError("empty sample")
    m = sum(xs) / n
    if n == 1:
        return Estimate(m, 0.0, 1)
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return Estimate(m, math.sqrt(var / n), n)


def binomial_se(p: float, n: int) -> float:
    """SE of a proportion: sqrt(p(1-p)/n)."""
    return math.sqrt(p * (1 - p) / n)


def clustered_se(xs: Sequence[float], clusters: Sequence[Hashable], small_sample: bool = True) -> Estimate:
    """Cluster-robust SE of the mean (Miller 2024, eq. for clustered SEs).

    SE^2 = sum_c (sum_{i in c} (x_i - mean))^2 / n^2, times G/(G-1) when
    small_sample is set. Use it when items share context: several alerts from
    one incident, several questions about one passage, several tasks in one repo.
    """
    if len(xs) != len(clusters):
        raise ValueError("xs and clusters must be the same length")
    n = len(xs)
    m = sum(xs) / n
    sums: dict[Hashable, float] = {}
    for x, c in zip(xs, clusters):
        sums[c] = sums.get(c, 0.0) + (x - m)
    g = len(sums)
    var = sum(s * s for s in sums.values()) / (n * n)
    if small_sample and g > 1:
        var *= g / (g - 1)
    return Estimate(m, math.sqrt(var), n)


def paired_diff(a: Sequence[float], b: Sequence[float], clusters: Sequence[Hashable] | None = None) -> Estimate:
    """Estimate mean(b - a) on the same items. Clustered when clusters are given.

    Pairing removes the between-item variance that both variants share, which
    is why it detects smaller effects than comparing two independent means.
    """
    if len(a) != len(b):
        raise ValueError("paired samples must align item-for-item")
    d = [y - x for x, y in zip(a, b)]
    return clustered_se(d, clusters) if clusters is not None else mean_se(d)


def unpaired_diff(a: Sequence[float], b: Sequence[float]) -> Estimate:
    """mean(b) - mean(a) treating the samples as independent (for contrast only)."""
    ea, eb = mean_se(a), mean_se(b)
    return Estimate(eb.mean - ea.mean, math.sqrt(ea.se**2 + eb.se**2), min(ea.n, eb.n))


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    clusters: Sequence[Hashable] | None = None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for mean(b - a). Resamples clusters if given.

    Returns (lo, hi, p_le_zero) where p_le_zero is the bootstrap share of
    resamples with a difference <= 0: a one-sided "is it really better" check.
    """
    rng = random.Random(seed)
    d = [y - x for x, y in zip(a, b)]
    keys = list(clusters) if clusters is not None else list(range(len(d)))
    groups: dict[Hashable, list[float]] = {}
    for k, v in zip(keys, d):
        groups.setdefault(k, []).append(v)
    units = list(groups.values())
    stats: list[float] = []
    for _ in range(n_boot):
        tot, cnt = 0.0, 0
        for _ in range(len(units)):
            u = units[rng.randrange(len(units))]
            tot += sum(u)
            cnt += len(u)
        stats.append(tot / cnt)
    stats.sort()
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    p_le_zero = sum(1 for s in stats if s <= 0) / n_boot
    return lo, hi, p_le_zero


def mcnemar(a: Sequence[int], b: Sequence[int], exact_below: int = 25) -> tuple[int, int, float]:
    """McNemar's test for paired binary outcomes (1 = pass).

    b01 = items a failed and b passed, b10 = items a passed and b failed. Only
    the discordant items carry information. Exact binomial when b01+b10 is
    small, otherwise chi-square with continuity correction.
    """
    b01 = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)
    b10 = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    n = b01 + b10
    if n == 0:
        return b01, b10, 1.0
    if n < exact_below:
        k = min(b01, b10)
        tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
        return b01, b10, min(1.0, 2 * tail)
    chi2 = (abs(b01 - b10) - 1) ** 2 / n
    p = 2 * (1 - _N.cdf(math.sqrt(chi2)))  # chi-square(1) survival via the normal
    return b01, b10, p


def ci_halfwidth(p: float, n: int, alpha: float = 0.05) -> float:
    """Half-width of the normal CI for a proportion. ci_halfwidth(0.03, 200) ~= 0.024."""
    return z_for(alpha) * binomial_se(p, n)


def required_n_for_margin(p: float, margin: float, alpha: float = 0.05) -> int:
    """Items needed so the CI on a proportion p is +/- margin."""
    return math.ceil(z_for(alpha) ** 2 * p * (1 - p) / margin**2)


def required_n_two_proportions(p1: float, p2: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Items per arm to detect p1 vs p2 with INDEPENDENT samples (classic formula)."""
    za, zb = z_for(alpha), _N.inv_cdf(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p1 - p2) ** 2)


def required_n_paired(delta: float, sd_diff: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Items to detect a mean paired difference `delta` given the SD of per-item diffs."""
    za, zb = z_for(alpha), _N.inv_cdf(power)
    return math.ceil(((za + zb) * sd_diff / delta) ** 2)


def sd_diff_from_correlation(sd_a: float, sd_b: float, rho: float) -> float:
    """SD of (b - a) when per-item scores correlate with coefficient rho."""
    return math.sqrt(sd_a**2 + sd_b**2 - 2 * rho * sd_a * sd_b)


def min_detectable_effect(se_diff: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest true effect you detect with the given power: (z_a/2 + z_b) * SE."""
    return (z_for(alpha) + _N.inv_cdf(power)) * se_diff


def design_effect(naive: Estimate, clustered: Estimate) -> float:
    """Variance inflation from clustering: (SE_clustered / SE_naive)^2."""
    return (clustered.se / naive.se) ** 2 if naive.se else float("nan")


if __name__ == "__main__":
    print("Eugene Yan's numbers: 3% defects")
    for n in (200, 400):
        print(f"  n={n}: 95% CI = 3.0% +/- {ci_halfwidth(0.03, n) * 100:.1f}%")
    print(f"  n for +/-1.0%: {required_n_for_margin(0.03, 0.01)}")
    print(f"Detect 70% -> 75% unpaired, 80% power: {required_n_two_proportions(0.70, 0.75)} per arm")
    sd = sd_diff_from_correlation(0.46, 0.43, 0.5)
    print(f"Same effect, paired (rho=0.5, sd_diff={sd:.2f}): {required_n_paired(0.05, sd)} items")
    _, _, p = mcnemar([0] * 10 + [1] * 2 + [1] * 50, [1] * 10 + [0] * 2 + [1] * 50)
    print(f"McNemar b01=10, b10=2: exact p = {p:.4f}")
