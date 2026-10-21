"""Canary analysis for prompt and model changes: is the canary's quality worse than control?

Two designs:
  * Live split (unpaired): different requests hit control and canary. Use a
    two-proportion test on the pass rate of an online check or judge.
  * Shadow replay (paired): the SAME inputs go to both configs. Use exact McNemar
    on the discordant pairs. Pairing removes input-mix variance, so it needs far
    fewer samples to detect the same regression.

Decision rule is non-inferiority, not "no significant difference":
  ROLLBACK  if the canary is significantly worse (one-sided p < alpha), or a guardrail breaches
  PROMOTE   if n >= min_n per arm AND the lower confidence bound on (canary - control) > -margin
  CONTINUE  otherwise (keep soaking, collect more data)

"No significant difference" at small n is absence of evidence; non-inferiority makes
you show the regression is smaller than a margin you chose in advance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

_N = NormalDist()


@dataclass
class Arm:
    passes: int
    n: int

    @property
    def rate(self) -> float:
        return self.passes / self.n if self.n else float("nan")


def two_proportion_z(control: Arm, canary: Arm) -> tuple[float, float]:
    """Pooled z-test. Returns (z, one-sided p-value for H1: canary rate < control rate)."""
    p = (control.passes + canary.passes) / (control.n + canary.n)
    se = math.sqrt(p * (1 - p) * (1 / control.n + 1 / canary.n))
    if se == 0:
        return 0.0, 0.5
    z = (canary.rate - control.rate) / se
    return z, _N.cdf(z)


def diff_ci(control: Arm, canary: Arm, alpha: float = 0.05) -> tuple[float, float]:
    """Two-sided (1 - 2*alpha) Wald CI on canary - control, so the lower bound is a one-sided
    alpha bound. Fine for n in the hundreds; use Newcombe's method for small n or rates near 0/1."""
    d = canary.rate - control.rate
    se = math.sqrt(control.rate * (1 - control.rate) / control.n + canary.rate * (1 - canary.rate) / canary.n)
    z = _N.inv_cdf(1 - alpha)
    return d - z * se, d + z * se


def mcnemar_exact(b: int, c: int) -> float:
    """Exact McNemar on discordant pairs. b = control pass & canary fail, c = control fail & canary pass.
    Returns the one-sided p-value for H1: canary worse (b > c)."""
    n = b + c
    if n == 0:
        return 1.0
    # P(X >= b) for X ~ Binomial(n, 0.5)
    return sum(math.comb(n, k) for k in range(b, n + 1)) / 2 ** n


def required_n_per_arm(p: float, margin: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Per-arm sample size to show non-inferiority within `margin` when both arms truly equal p."""
    za, zb = _N.inv_cdf(1 - alpha), _N.inv_cdf(power)
    return math.ceil((za + zb) ** 2 * 2 * p * (1 - p) / margin ** 2)


@dataclass
class Decision:
    action: str  # PROMOTE | ROLLBACK | CONTINUE
    reason: str
    stats: dict[str, float] = field(default_factory=dict)


def decide(control: Arm, canary: Arm, *, margin: float = 0.02, alpha: float = 0.05, min_n: int = 400,
           looks: int = 1, guardrails: dict[str, bool] | None = None) -> Decision:
    """Non-inferiority canary decision.

    `looks` is how many times you will check during the soak. Peeking repeatedly inflates the
    false-alarm rate, so alpha is split across looks (Bonferroni: conservative but honest).
    `guardrails` maps names to "breached?" for hard limits (secret leak, cost per request).
    """
    a = alpha / looks
    breached = [k for k, v in (guardrails or {}).items() if v]
    z, p_worse = two_proportion_z(control, canary)
    lo, hi = diff_ci(control, canary, a)
    stats = {"control": control.rate, "canary": canary.rate, "diff": canary.rate - control.rate,
             "ci_lo": lo, "ci_hi": hi, "z": z, "p_worse": p_worse, "alpha_per_look": a}
    if breached:
        return Decision("ROLLBACK", f"guardrail breached: {', '.join(breached)}", stats)
    if p_worse < a:
        return Decision("ROLLBACK", f"canary significantly worse (p={p_worse:.4f} < {a:.4f})", stats)
    if min(control.n, canary.n) < min_n:
        return Decision("CONTINUE", f"need {min_n} per arm, have {min(control.n, canary.n)}", stats)
    if lo > -margin:
        return Decision("PROMOTE", f"non-inferior: lower bound {lo:+.4f} > -{margin}", stats)
    return Decision("CONTINUE", f"inconclusive: lower bound {lo:+.4f} <= -{margin}", stats)


def decide_paired(pairs: list[tuple[bool, bool]], *, alpha: float = 0.05, margin: float = 0.02,
                  min_n: int = 200) -> Decision:
    """Shadow-replay decision. pairs = [(control_pass, canary_pass), ...] on identical inputs."""
    b = sum(1 for c0, c1 in pairs if c0 and not c1)
    c = sum(1 for c0, c1 in pairs if c1 and not c0)
    n = len(pairs)
    p = mcnemar_exact(b, c)
    d = (c - b) / n if n else 0.0
    # Wald CI for a paired difference of proportions.
    se = math.sqrt(max((b + c) / n - d * d, 0.0) / n) if n else float("inf")
    lo = d - _N.inv_cdf(1 - alpha) * se
    stats = {"n": n, "b_regressions": b, "c_fixes": c, "diff": d, "ci_lo": lo, "p_worse": p}
    if n and p < alpha:
        return Decision("ROLLBACK", f"{b} regressions vs {c} fixes on the same inputs (p={p:.4f})", stats)
    if n < min_n:
        return Decision("CONTINUE", f"need {min_n} paired cases, have {n}", stats)
    if lo > -margin:
        return Decision("PROMOTE", f"non-inferior on paired replay: lower bound {lo:+.4f}", stats)
    return Decision("CONTINUE", f"inconclusive: lower bound {lo:+.4f}", stats)


if __name__ == "__main__":
    print("n per arm to rule out a 2-pt drop at 95% pass:", required_n_per_arm(0.95, 0.02))
    print(decide(Arm(1172, 1240), Arm(1150, 1236), margin=0.02, looks=3))
    print(decide(Arm(1172, 1240), Arm(1102, 1236), margin=0.02, looks=3))
    pairs = [(True, True)] * 470 + [(True, False)] * 19 + [(False, True)] * 6 + [(False, False)] * 5
    print(decide_paired(pairs))
