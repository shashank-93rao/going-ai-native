"""Generate a synthetic experiment log with a KNOWN true effect.

Use it to check the analysis before you trust it on your own data: if the
estimator cannot recover a ratio you planted, it will not find one you did not.

    python simulate_ab.py --out data/sample_log.jsonl --tasks 40 --true-ratio 1.19 --perceived-ratio 0.80

Everything this writes is synthetic. Do not quote it as a measurement.
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from selfmeasure_log import append_event, assign_arm

KINDS = ["bugfix", "feature", "refactor", "migration", "test-flake"]
SIZE_EST = {"S": 45, "M": 150, "L": 480}  # your pre-assignment estimate, minutes


def simulate(
    out: str | Path,
    n_tasks: int = 40,
    true_ratio: float = 1.0,
    perceived_ratio: float = 0.8,
    rework_p: dict[str, float] | None = None,
    abandon_p: dict[str, float] | None = None,
    noise_sd: float = 0.5,
    seed: int = 7,
    experiment_seed: str = "sim-secret",
) -> Path:
    """Write a full event log. Returns the path."""
    rng = random.Random(seed)
    rework_p = rework_p or {"ai": 0.2, "no_ai": 0.2}
    abandon_p = abandon_p or {"ai": 0.0, "no_ai": 0.0}
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    clock = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)

    def at(dt: datetime) -> str:
        return dt.replace(microsecond=0).isoformat()

    for i in range(n_tasks):
        tid = f"T-{i + 1:03d}"
        size = rng.choice(list(SIZE_EST))
        est = SIZE_EST[size] * math.exp(rng.gauss(0, 0.2))
        append_event(path, {"event": "register", "task_id": tid, "ts": at(clock), "title": f"synthetic {size} task {i + 1}",
                            "kind": rng.choice(KINDS), "size": size, "est_minutes": round(est)})
        arm = assign_arm(path, tid, experiment_seed, ts=at(clock))
        start = clock + timedelta(minutes=5)
        append_event(path, {"event": "start", "task_id": tid, "ts": at(start)})
        if rng.random() < abandon_p[arm]:
            append_event(path, {"event": "abandon", "task_id": tid, "ts": at(start + timedelta(hours=2)), "reason": "synthetic"})
            clock += timedelta(hours=6)
            continue
        no_ai_minutes = est * math.exp(rng.gauss(0, noise_sd))
        minutes = no_ai_minutes * (true_ratio if arm == "ai" else 1.0)
        # Wall clock = active work + review/CI wait, which is noisy and arm-independent.
        wait = math.exp(rng.gauss(math.log(90), 0.8))
        merged = start + timedelta(minutes=minutes + wait)
        append_event(path, {"event": "merge", "task_id": tid, "ts": at(merged), "pr": f"#{1000 + i}", "active_minutes": round(minutes)})
        # Your guess about the other arm, biased so that perceived ai/no_ai = perceived_ratio.
        jitter = math.exp(rng.gauss(0, 0.15))
        if arm == "ai":
            guess = minutes / perceived_ratio * jitter
        else:
            guess = minutes * perceived_ratio * jitter
        append_event(path, {"event": "perceive", "task_id": tid, "ts": at(merged), "perceived_other_arm_minutes": round(guess, 1)})
        if rng.random() < rework_p[arm]:
            append_event(path, {"event": "rework", "task_id": tid, "ts": at(merged + timedelta(days=rng.uniform(0.5, 10))),
                                "rework_kind": rng.choice(["fix", "followup", "revert"]), "minutes": round(est * rng.uniform(0.2, 0.6))})
        clock = merged + timedelta(minutes=30)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/sample_log.jsonl")
    ap.add_argument("--tasks", type=int, default=40)
    ap.add_argument("--true-ratio", type=float, default=1.0)
    ap.add_argument("--perceived-ratio", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    p = simulate(args.out, args.tasks, args.true_ratio, args.perceived_ratio, seed=args.seed)
    print(f"wrote synthetic log to {p}")


if __name__ == "__main__":
    main()
