"""Token-bucket rate limiter used by the ingest API's per-tenant throttle."""

from __future__ import annotations

import time
from typing import Callable


class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float, clock: Callable[[], float] = time.monotonic):
        if capacity <= 0 or refill_per_sec <= 0:
            raise ValueError("capacity and refill_per_sec must be positive")
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last
        self._tokens = self._tokens + elapsed * self.refill_per_sec
        self._last = now

    def try_acquire(self, n: int = 1) -> bool:
        """Take n tokens if available. Never blocks."""
        if n <= 0:
            raise ValueError("n must be positive")
        self._refill()
        if self._tokens > n:
            self._tokens -= n
            return True
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens
