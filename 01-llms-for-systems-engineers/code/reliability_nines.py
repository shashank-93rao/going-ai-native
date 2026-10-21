"""Reliability-nines calculator for multi-step agents.

If each step of an agent succeeds independently with probability p, a run of n
steps succeeds with p**n. This is the same arithmetic as serial availability
(a request that crosses five 99.9% services is ~99.5% available), and the same
caveat applies: independence is an assumption, and correlated failures break it.

Run:  python reliability_nines.py
"""

from __future__ import annotations

import math
import random


def chain_success(p: float, steps: int) -> float:
    """P(all `steps` succeed), independent steps each succeeding with p."""
    _check_p(p)
    if steps < 0:
        raise ValueError("steps must be >= 0")
    return p**steps


def nines(p: float) -> float:
    """Number of nines: 0.9 -> 1, 0.99 -> 2, 0.999 -> 3."""
    _check_p(p)
    return math.inf if p == 1.0 else -math.log10(1.0 - p)


def required_step_reliability(target: float, steps: int) -> float:
    """Per-step success needed so an n-step chain hits `target`: target**(1/n)."""
    _check_p(target)
    if steps <= 0:
        raise ValueError("steps must be > 0")
    return target ** (1.0 / steps)


def max_steps(p: float, target: float) -> int:
    """Largest n with p**n >= target."""
    _check_p(p)
    _check_p(target)
    if p == 1.0:
        return math.inf  # type: ignore[return-value]
    if p == 0.0:
        return 0
    # floor(log(target)/log(p)), with a small epsilon against float edge cases
    return int(math.floor(math.log(target) / math.log(p) + 1e-12))


def with_verified_retries(p: float, detect: float, attempts: int) -> float:
    """Per-step success when a verifier catches a fraction `detect` of failures
    and the step is retried, up to `attempts` total tries.

    An undetected failure ends the step as a (silent) failure. Assumes attempts
    are independent, which is optimistic: a model that is wrong for a systematic
    reason tends to be wrong again on retry.
    """
    _check_p(p)
    _check_p(detect)
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    success, reach = 0.0, 1.0  # reach = P(we get to make this attempt)
    for _ in range(attempts):
        success += reach * p
        reach *= (1 - p) * detect  # failed AND caught -> try again
    return success


def pass_at_k(p: float, k: int) -> float:
    """P(at least one of k independent tries succeeds). Good when a checker picks the winner."""
    _check_p(p)
    return 1 - (1 - p) ** k


def pass_hat_k(p: float, k: int) -> float:
    """P(all k tries succeed): consistency, what a user sees across k runs."""
    _check_p(p)
    return p**k


def expected_failures(success: float, runs: int) -> float:
    """Error-budget view: expected failed runs out of `runs`."""
    _check_p(success)
    return (1 - success) * runs


def simulate_chain(p: float, steps: int, trials: int = 100_000, seed: int = 0) -> float:
    """Monte Carlo check of chain_success."""
    rng = random.Random(seed)
    ok = sum(all(rng.random() < p for _ in range(steps)) for _ in range(trials))
    return ok / trials


def _check_p(p: float) -> None:
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {p}")


def main() -> None:
    print("Chain success p**n (rows: per-step success, cols: steps)")
    steps = [1, 5, 10, 20, 50, 100]
    print("p\\n     " + "".join(f"{n:>9}" for n in steps))
    for p in (0.9, 0.95, 0.99, 0.995, 0.999):
        print(f"{p:<9}" + "".join(f"{chain_success(p, n):>9.3f}" for n in steps))

    print("\nPer-step reliability needed for a 20-step agent to hit a run-level target")
    for target in (0.9, 0.99, 0.999):
        r = required_step_reliability(target, 20)
        print(f"  run {target:.1%} ({nines(target):.0f} nines) -> step {r:.5f} ({nines(r):.2f} nines)")

    p, detect = 0.95, 0.8
    print(f"\nVerifier + retry, base step p={p}, verifier catches {detect:.0%} of failures")
    for a in (1, 2, 3):
        s = with_verified_retries(p, detect, a)
        print(f"  attempts={a}: step={s:.4f}  20-step run={chain_success(s, 20):.3f}")

    print("\npass@k vs pass^k at p=0.7")
    for k in (1, 3, 5, 10):
        print(f"  k={k:<3} pass@k={pass_at_k(0.7, k):.3f}  pass^k={pass_hat_k(0.7, k):.3f}")


if __name__ == "__main__":
    main()
