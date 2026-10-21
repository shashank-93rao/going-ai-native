"""Run an agent test N times, compute pass@k / pass^k, and write a flakiness report.

The key move is a THREE-way outcome per trial: pass, fail (the agent got it wrong),
infra_error (the environment broke). Infra errors are retried on a fresh
environment and reported separately; they never count as model failures, and
model failures are never retried away.

    python flaky.py            # 40 seeds of the noisy policy against a faulty world
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from ainative_kit import FakeClient, get_client

from ops_agent import TASK, run_agent
from policies import noisy_policy
from trajectory_checks import evaluate, failed, first_failure, format_matrix, transition_matrix
from world import FaultPlan, OpsWorld


@dataclass
class Trial:
    seed: int
    status: str  # "pass" | "fail" | "infra_error"
    failed_checks: list[str] = field(default_factory=list)
    infra_retries: int = 0
    transition: tuple[str, str] | None = None


TrialFn = Callable[[int], Trial]


def pass_at_k(n: int, c: int, k: int) -> float:
    """P(at least one of k samples passes), unbiased estimator from n trials with c passes."""
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k: P(all k samples pass), estimated as C(c,k)/C(n,k) (the tau-bench estimator)."""
    if k > n:
        raise ValueError("k cannot exceed n")
    return math.comb(c, k) / math.comb(n, k)


def wilson(c: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a pass rate. Behaves at 0/n and n/n, unlike mean +/- 1.96*SE."""
    if n == 0:
        return (0.0, 1.0)
    p = c / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def run_with_infra_retry(trial_fn: TrialFn, seed: int, max_infra_retries: int = 2) -> Trial:
    """Retry ONLY infra errors, each time on a fresh environment (a new seed offset)."""
    for attempt in range(max_infra_retries + 1):
        t = trial_fn(seed + 1_000_000 * attempt)
        t.seed, t.infra_retries = seed, attempt
        if t.status != "infra_error":
            return t
    return t


@dataclass
class FlakinessReport:
    n: int
    passes: int
    fails: int
    infra: int
    pass_at: dict[int, float]
    pass_hat: dict[int, float]
    ci: tuple[float, float]
    failing_checks: Counter[str]
    verdict: str
    matrix: str

    def render(self) -> str:
        scored = self.passes + self.fails
        lines = [
            f"trials: {self.n}  pass: {self.passes}  fail: {self.fails}  infra_error (excluded): {self.infra}",
            f"pass rate: {self.passes}/{scored}  95% CI [{self.ci[0]:.2f}, {self.ci[1]:.2f}]",
            "pass@k: " + "  ".join(f"k={k}: {v:.2f}" for k, v in self.pass_at.items()),
            "pass^k: " + "  ".join(f"k={k}: {v:.2f}" for k, v in self.pass_hat.items()),
            "failing checks: " + (", ".join(f"{c} x{n}" for c, n in self.failing_checks.most_common()) or "none"),
            f"verdict: {self.verdict}",
            "transition failure matrix:",
            self.matrix,
        ]
        return "\n".join(lines)


def verdict(passes: int, scored: int, infra: int, n: int, gate_k: int, gate: float, infra_budget: float) -> str:
    """Decision rule for CI. Course synthesis, tune the thresholds to your suite."""
    if n and infra / n > infra_budget:
        return f"ENVIRONMENT: infra error rate {infra / n:.0%} > budget {infra_budget:.0%}; fix the harness, not the prompt"
    if scored == 0:
        return "NO SIGNAL: every trial was an infra error"
    if passes == scored:
        return "STABLE"
    if passes == 0:
        return "BROKEN: deterministic failure, treat as a regression"
    if pass_hat_k(scored, passes, min(gate_k, scored)) < gate:
        return f"FLAKY: pass^{gate_k} below {gate:.2f}; quarantine from the blocking gate and file a model-behavior bug"
    return f"FLAKY BUT WITHIN BUDGET: pass^{gate_k} >= {gate:.2f}"


def flakiness_report(trials: list[Trial], ks: tuple[int, ...] = (1, 3, 5), gate_k: int = 3,
                     gate: float = 0.8, infra_budget: float = 0.05) -> FlakinessReport:
    passes = sum(t.status == "pass" for t in trials)
    fails = sum(t.status == "fail" for t in trials)
    infra = sum(t.status == "infra_error" for t in trials)
    scored = passes + fails
    ks = tuple(k for k in ks if k <= scored)
    checks: Counter[str] = Counter(c for t in trials for c in t.failed_checks)
    return FlakinessReport(
        n=len(trials), passes=passes, fails=fails, infra=infra,
        pass_at={k: pass_at_k(scored, passes, k) for k in ks},
        pass_hat={k: pass_hat_k(scored, passes, k) for k in ks},
        ci=wilson(passes, scored),
        failing_checks=checks,
        verdict=verdict(passes, scored, infra, len(trials), gate_k, gate, infra_budget),
        matrix=format_matrix(transition_matrix([t.transition for t in trials])),
    )


def deploy_trial(faults: FaultPlan, bug_rates: dict[str, float] | None = None, *, real: bool = False) -> TrialFn:
    """One trial of the deploy task: a fresh world and a fresh 'model sample' per seed.

    real=True uses get_client() (the API when a key is set); the default is always offline.
    """

    def trial(seed: int) -> Trial:
        world = OpsWorld(seed=seed, faults=faults)
        fake = FakeClient(noisy_policy(seed % 1_000_000, bug_rates))
        client = get_client(fake=fake) if real else fake
        run = run_agent(client, world, TASK)
        if run.stop_reason == "infra_error":
            return Trial(seed, "infra_error")
        bad = failed(evaluate(run, world, "payments", "v2.4.0"))
        return Trial(seed, "fail" if bad else "pass", bad, transition=first_failure(run, world, "payments", "v2.4.0"))

    return trial


def run_suite(trial_fn: TrialFn, seeds: range, retry_infra: bool = True) -> list[Trial]:
    if retry_infra:
        return [run_with_infra_retry(trial_fn, s) for s in seeds]
    return [trial_fn(s) for s in seeds]


if __name__ == "__main__":
    faults = FaultPlan(transient_rate=0.15, ack_loss_rate=0.15, infra_crash_rate=0.02)
    trial = deploy_trial(faults, real=True)
    print("== without infra retry ==")
    print(flakiness_report(run_suite(trial, range(40), retry_infra=False)).render())
    print("\n== with infra retry on a fresh environment ==")
    print(flakiness_report(run_suite(trial, range(40))).render())
