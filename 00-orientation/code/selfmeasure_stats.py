"""Statistics for the personal A/B: is the AI arm actually faster, and does it cost rework later?

Design choices, briefly:
- Durations are right-skewed (one task eats a week), so effects are computed on
  log(minutes). The headline is a *time ratio*: geometric-mean(ai) / geometric-mean(no_ai).
  0.80 means AI tasks took 20% less time; 1.19 means 19% more (METR 2025's number).
- An estimate-adjusted ratio uses log(actual / your pre-assignment estimate). Your
  estimate soaks up task difficulty, which cuts variance a lot at small n.
- The CI is a Welch t interval on log time, and the p-value is a permutation test.
  A percentile bootstrap is kept for comparison, but it under-covers at small n
  (about 92% actual coverage for a nominal 95% at 20 tasks per arm over 200 simulate_ab.py
  runs, vs about 95% for Welch).
- Abandoned and still-open tasks are *reported*, not silently dropped. Dropping the
  hard tasks from one arm is the selection effect that broke METR's 2026 follow-up.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from selfmeasure_log import ARMS, TaskState, parse_ts

Z_975, Z_80 = 1.96, 0.84  # two-sided alpha 0.05, power 0.80


def outcome_minutes(t: TaskState, outcome: str) -> float | None:
    """'wall' = start->merge wall clock; 'active' = self-reported active_minutes on merge."""
    if t.merged is None:
        return None
    if outcome == "active":
        return t.active_minutes
    hours = t.hours_to_merge
    return None if hours is None else hours * 60


def rework_in_window(t: TaskState, days: float) -> list[dict[str, Any]]:
    if t.merged is None:
        return []
    end = t.merged + timedelta(days=days)
    return [r for r in t.rework if t.merged <= parse_ts(r["ts"]) <= end]


def _mean_log_diff(a: list[float], b: list[float]) -> float:
    return statistics.fmean(math.log(x) for x in a) - statistics.fmean(math.log(x) for x in b)


def t_quantile_975(df: float) -> float:
    """97.5th percentile of Student's t via the Cornish-Fisher expansion (stdlib has no t.ppf).

    Within 0.1% of table values for df >= 3.
    """
    z = Z_975
    g1 = (z**3 + z) / 4
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384
    g4 = (79 * z**9 + 776 * z**7 + 1482 * z**5 - 1920 * z**3 - 945 * z) / 92160
    return z + g1 / df + g2 / df**2 + g3 / df**3 + g4 / df**4


def welch_ratio_ci(a: list[float], b: list[float]) -> tuple[float, float]:
    """95% CI for geomean(a)/geomean(b): Welch t interval on the difference of mean logs."""
    la, lb = [math.log(x) for x in a], [math.log(x) for x in b]
    va, vb = statistics.variance(la) / len(la), statistics.variance(lb) / len(lb)
    se = math.sqrt(va + vb)
    if se == 0:
        d = statistics.fmean(la) - statistics.fmean(lb)
        return math.exp(d), math.exp(d)
    df = (va + vb) ** 2 / (va**2 / (len(la) - 1) + vb**2 / (len(lb) - 1))
    d = statistics.fmean(la) - statistics.fmean(lb)
    half = t_quantile_975(df) * se
    return math.exp(d - half), math.exp(d + half)


def bootstrap_ratio_ci(a: list[float], b: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% percentile-bootstrap CI for geomean(a)/geomean(b), resampling within each arm."""
    rng = random.Random(seed)
    stats = sorted(
        math.exp(_mean_log_diff(rng.choices(a, k=len(a)), rng.choices(b, k=len(b)))) for _ in range(n_boot)
    )
    return stats[int(0.025 * n_boot)], stats[int(0.975 * n_boot) - 1]


def permutation_p(a: list[float], b: list[float], n_perm: int = 5000, seed: int = 0) -> float:
    """Two-sided permutation p-value for a difference in mean log time."""
    rng = random.Random(seed)
    observed = abs(_mean_log_diff(a, b))
    pooled = a + b
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        if abs(_mean_log_diff(pooled[: len(a)], pooled[len(a):])) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def mde_ratio(sd_log: float, n_per_arm: int) -> float:
    """Smallest time ratio below 1 you could detect at 80% power with this n and spread."""
    return math.exp(-(Z_975 + Z_80) * sd_log * math.sqrt(2 / n_per_arm))


def n_needed(sd_log: float, target_ratio: float) -> int:
    """Tasks per arm needed to detect `target_ratio` (e.g. 0.8) at 80% power."""
    return math.ceil(2 * ((Z_975 + Z_80) * sd_log / abs(math.log(target_ratio))) ** 2)


@dataclass
class Effect:
    ratio: float
    ci: tuple[float, float]
    p: float

    def describe(self) -> str:
        pct = (self.ratio - 1) * 100
        word = "longer" if pct > 0 else "shorter"
        return f"{abs(pct):.0f}% {word} with AI (ratio {self.ratio:.2f}, 95% CI {self.ci[0]:.2f}-{self.ci[1]:.2f}, p={self.p:.3f})"


@dataclass
class Summary:
    arms: dict[str, dict[str, Any]]
    time: Effect | None = None
    time_adjusted: Effect | None = None
    time_with_rework: Effect | None = None
    perceived_ratio: float | None = None
    mde: float | None = None
    n_for_20pct: int | None = None
    warnings: list[str] = field(default_factory=list)


def _effect(a: list[float], b: list[float], seed: int) -> Effect:
    return Effect(math.exp(_mean_log_diff(a, b)), welch_ratio_ci(a, b), permutation_p(a, b, seed=seed))


def summarize(
    tasks: dict[str, TaskState], outcome: str = "wall", rework_days: float = 14, seed: int = 0
) -> Summary:
    by_arm: dict[str, list[TaskState]] = {arm: [t for t in tasks.values() if t.arm == arm] for arm in ARMS}
    arms: dict[str, dict[str, Any]] = {}
    times: dict[str, list[float]] = {}
    adjusted: dict[str, list[float]] = {}
    effective: dict[str, list[float]] = {}
    perceived_logs: list[float] = []
    warnings: list[str] = []

    for arm, ts in by_arm.items():
        merged = [t for t in ts if t.merged is not None]
        abandoned = [t for t in ts if t.abandoned]
        open_ = [t for t in ts if t.merged is None and not t.abandoned]
        mins, adj, eff = [], [], []
        reworked = 0
        for t in merged:
            m = outcome_minutes(t, outcome)
            if m is None or m <= 0:
                continue
            rw = rework_in_window(t, rework_days)
            reworked += bool(rw)
            mins.append(m)
            adj.append(m / t.est_minutes if t.est_minutes else m)
            eff.append((m + sum(r["minutes"] for r in rw)) / (t.est_minutes or 1))
            if t.perceived_other_arm_minutes:
                # log(ai_time / no_ai_time), one side observed, the other guessed. Guesses are
                # about effort, so compare against active minutes when you logged them.
                guess, actual = t.perceived_other_arm_minutes, t.active_minutes or m
                perceived_logs.append(math.log(actual / guess) if arm == "ai" else math.log(guess / actual))
        times[arm], adjusted[arm], effective[arm] = mins, adj, eff
        arms[arm] = {
            "assigned": len(ts),
            "merged": len(merged),
            "abandoned": len(abandoned),
            "open": len(open_),
            "completion_rate": len(merged) / len(ts) if ts else None,
            "median_minutes": statistics.median(mins) if mins else None,
            "geomean_minutes": math.exp(statistics.fmean(math.log(x) for x in mins)) if mins else None,
            "rework_rate": reworked / len(mins) if mins else None,
        }

    s = Summary(arms=arms, warnings=warnings)
    a, b = times["ai"], times["no_ai"]
    if len(a) < 2 or len(b) < 2:
        warnings.append("need at least 2 merged tasks per arm for any estimate")
        return s

    s.time = _effect(a, b, seed)
    s.time_adjusted = _effect(adjusted["ai"], adjusted["no_ai"], seed)
    s.time_with_rework = _effect(effective["ai"], effective["no_ai"], seed)
    if perceived_logs:
        s.perceived_ratio = math.exp(statistics.fmean(perceived_logs))

    resid = [math.log(x) - statistics.fmean(map(math.log, adjusted[k])) for k in ARMS for x in adjusted[k]]
    sd = statistics.stdev(resid)
    n = min(len(a), len(b))
    s.mde, s.n_for_20pct = mde_ratio(sd, n), n_needed(sd, 0.8)

    if n < 10:
        warnings.append(f"only {n} merged tasks in the smaller arm; treat the estimate as a direction, not a size")
    ab = {arm: arms[arm]["abandoned"] / arms[arm]["assigned"] for arm in ARMS}
    if abs(ab["ai"] - ab["no_ai"]) >= 0.10:
        warnings.append(
            f"abandon rates differ (ai {ab['ai']:.0%} vs no_ai {ab['no_ai']:.0%}): the merged sets are no longer comparable"
        )
    for arm in ARMS:
        if arms[arm]["open"]:
            warnings.append(f"{arms[arm]['open']} {arm} task(s) still open: excluding them favours whichever arm finishes fast work first")
    return s


def render(s: Summary, outcome: str = "wall") -> str:
    """Plain-text report suitable for a terminal or a weekly note."""
    lines = [f"Outcome: {'wall-clock start->merge' if outcome == 'wall' else 'active minutes'}", ""]
    lines.append(f"{'arm':<7}{'assigned':>9}{'merged':>8}{'abandon':>9}{'open':>6}{'median_min':>12}{'geomean_min':>13}{'rework':>8}")
    for arm, r in s.arms.items():
        med = f"{r['median_minutes']:.0f}" if r["median_minutes"] else "-"
        geo = f"{r['geomean_minutes']:.0f}" if r["geomean_minutes"] else "-"
        rw = f"{r['rework_rate']:.0%}" if r["rework_rate"] is not None else "-"
        lines.append(f"{arm:<7}{r['assigned']:>9}{r['merged']:>8}{r['abandoned']:>9}{r['open']:>6}{med:>12}{geo:>13}{rw:>8}")
    lines.append("")
    if s.time:
        lines.append(f"Unadjusted:              {s.time.describe()}")
        lines.append(f"Estimate-adjusted:       {s.time_adjusted.describe()}")
        lines.append(f"Adjusted, incl. rework:  {s.time_with_rework.describe()}")
    if s.perceived_ratio:
        lines.append(f"Perceived ratio:         {s.perceived_ratio:.2f} (your guesses about the other arm, vs active minutes)")
    if s.mde:
        lines.append(f"Detectable at this n:    ratio <= {s.mde:.2f} (80% power); ~{s.n_for_20pct} tasks/arm needed for a 20% effect")
    for w in s.warnings:
        lines.append(f"WARNING: {w}")
    return "\n".join(lines)
