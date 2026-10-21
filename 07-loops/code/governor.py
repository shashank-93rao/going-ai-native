"""Loop governor: the part of a loop that decides when to stop, independent of the model.

The model decides *what* to do next. The governor decides *whether there is a next*.
It is consulted at fixed points (before each model call, after each tool batch) and
trips with a typed exit code. Think of it as the circuit breaker plus rate limiter
around an unreliable, expensive dependency that can also loop forever.

    gov = Governor(Limits(max_iterations=20, max_cost_usd=2.0))
    while True:
        gov.tick()                      # raises GovernorTripped when a limit is hit
        resp = client.complete(...)
        gov.record_usage(resp.usage.input_tokens, resp.usage.output_tokens)
        for call in resp.tool_calls:
            gov.record_tool_call(call.name, call.input)
            ...
            gov.record_outcome(ok)
        gov.record_metric(oracle_score)  # optional: enables no-progress detection
        gov.check()
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable


class ExitCode(IntEnum):
    """Typed exit codes. Each way a loop can end gets its own code, so callers can branch."""

    SUCCESS = 0  # the oracle (not the model) says done
    FAIL = 1  # loop ended normally but the oracle says not done (e.g. iteration cap)
    BLOCKED = 2  # the agent reported it cannot proceed and needs a human
    BROKEN = 3  # loop machinery or the oracle itself errored: fail closed
    BUDGET = 4  # token, dollar or wall-clock budget exhausted
    STALLED = 5  # no progress, repetition, or consecutive-error breaker
    STOPPED = 6  # an operator asked it to stop (stop file)


@dataclass
class Limits:
    """Every limit gets a real number. None disables that check (do this deliberately)."""

    max_iterations: int = 30
    max_input_tokens: int | None = 2_000_000
    max_output_tokens: int | None = 200_000
    max_cost_usd: float | None = 5.0
    max_wall_seconds: float | None = 30 * 60
    max_consecutive_errors: int = 3  # 12-factor agents, factor 9
    max_repeats: int = 3  # identical (tool, args) calls allowed inside the window
    repeat_window: int = 6  # how many recent calls to look at (catches A-B-A-B too)
    stall_patience: int | None = 5  # metric observations without improvement
    stop_file: str | Path | None = None


@dataclass
class Prices:
    """USD per million tokens. Placeholder defaults: set these from the current pricing page."""

    input_per_mtok: float = 3.0
    output_per_mtok: float = 15.0
    cached_read_per_mtok: float = 0.30


class GovernorTripped(Exception):
    def __init__(self, code: ExitCode, reason: str):
        super().__init__(f"{code.name}: {reason}")
        self.code = code
        self.reason = reason


def call_signature(name: str, args: dict[str, Any]) -> str:
    """Stable hash of a tool call. Same tool + same args => same signature."""
    blob = json.dumps({"n": name, "a": args}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


class Governor:
    def __init__(
        self,
        limits: Limits | None = None,
        prices: Prices | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limits = limits or Limits()
        self.prices = prices or Prices()
        self._clock = clock
        self.started_at = clock()
        self.iterations = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.consecutive_errors = 0
        self.best_metric: Any = None
        self.since_improvement = 0
        self.metric_history: list[Any] = []
        self._recent_calls: deque[tuple[str, str]] = deque(maxlen=self.limits.repeat_window)
        self._pending: GovernorTripped | None = None

    # ---- recording ----------------------------------------------------------
    def tick(self) -> None:
        """Start a new iteration. Checks limits first, so a tripped loop never spends again."""
        self.check()
        if self.iterations >= self.limits.max_iterations:
            raise GovernorTripped(ExitCode.FAIL, f"max_iterations={self.limits.max_iterations} reached")
        self.iterations += 1

    def record_usage(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached_tokens

    def record_tool_call(self, name: str, args: dict[str, Any]) -> None:
        """Repetition detection: the same call N times inside a sliding window."""
        sig = call_signature(name, args)
        self._recent_calls.append((sig, name))
        repeats = sum(1 for s, _ in self._recent_calls if s == sig)
        if repeats >= self.limits.max_repeats and self._pending is None:
            self._pending = GovernorTripped(
                ExitCode.STALLED,
                f"repetition: {name}({_short(args)}) called {repeats}x in last {len(self._recent_calls)} calls",
            )

    def record_outcome(self, ok: bool) -> None:
        """Consecutive-error breaker. Any success resets the counter."""
        self.consecutive_errors = 0 if ok else self.consecutive_errors + 1
        if self.consecutive_errors >= self.limits.max_consecutive_errors and self._pending is None:
            self._pending = GovernorTripped(
                ExitCode.STALLED, f"{self.consecutive_errors} consecutive errors; escalate instead of retrying"
            )

    def record_metric(self, value: Any) -> None:
        """No-progress detection on the oracle metric (higher is better; tuples compare lexically).

        Progress means a strict improvement over the best value seen so far. Moving
        sideways or oscillating counts as no progress.
        """
        if value is None:
            return
        self.metric_history.append(value)
        if self.best_metric is None or value > self.best_metric:
            self.best_metric = value
            self.since_improvement = 0
            return
        self.since_improvement += 1
        patience = self.limits.stall_patience
        if patience is not None and self.since_improvement >= patience and self._pending is None:
            self._pending = GovernorTripped(
                ExitCode.STALLED,
                f"no progress: metric stuck at best={self.best_metric!r} for {self.since_improvement} observations",
            )

    # ---- checking -----------------------------------------------------------
    @property
    def cost_usd(self) -> float:
        p = self.prices
        return (
            self.input_tokens * p.input_per_mtok
            + self.output_tokens * p.output_per_mtok
            + self.cached_tokens * p.cached_read_per_mtok
        ) / 1_000_000

    @property
    def elapsed(self) -> float:
        return self._clock() - self.started_at

    def check(self) -> None:
        """Raise GovernorTripped if any limit is exceeded. Order: operator, behaviour, budget."""
        lim = self.limits
        if lim.stop_file and Path(lim.stop_file).exists():
            raise GovernorTripped(ExitCode.STOPPED, f"stop file {lim.stop_file} present")
        if self._pending is not None:
            raise self._pending
        if lim.max_wall_seconds is not None and self.elapsed > lim.max_wall_seconds:
            raise GovernorTripped(ExitCode.BUDGET, f"wall clock {self.elapsed:.0f}s > {lim.max_wall_seconds:.0f}s")
        if lim.max_input_tokens is not None and self.input_tokens > lim.max_input_tokens:
            raise GovernorTripped(ExitCode.BUDGET, f"input tokens {self.input_tokens} > {lim.max_input_tokens}")
        if lim.max_output_tokens is not None and self.output_tokens > lim.max_output_tokens:
            raise GovernorTripped(ExitCode.BUDGET, f"output tokens {self.output_tokens} > {lim.max_output_tokens}")
        if lim.max_cost_usd is not None and self.cost_usd > lim.max_cost_usd:
            raise GovernorTripped(ExitCode.BUDGET, f"cost ${self.cost_usd:.2f} > ${lim.max_cost_usd:.2f}")

    def snapshot(self) -> dict[str, Any]:
        """Small dict for traces and logs."""
        return {
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "elapsed_s": round(self.elapsed, 2),
            "consecutive_errors": self.consecutive_errors,
            "best_metric": self.best_metric,
            "since_improvement": self.since_improvement,
        }


def _short(args: dict[str, Any], n: int = 60) -> str:
    s = json.dumps(args, sort_keys=True, default=str)
    return s if len(s) <= n else s[: n - 3] + "..."
