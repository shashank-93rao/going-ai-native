"""Executable spec for TokenBucket. This file is the oracle: do not edit it."""

import pytest

from tokenbucket import TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def make(capacity=3, rate=1.0):
    clock = FakeClock()
    return TokenBucket(capacity, rate, clock=clock), clock


def test_starts_full_and_allows_exactly_capacity():
    b, _ = make(capacity=3)
    assert [b.try_acquire() for _ in range(4)] == [True, True, True, False]


def test_refill_never_exceeds_capacity():
    b, clock = make(capacity=2, rate=1.0)
    clock.advance(100)
    assert [b.try_acquire() for _ in range(3)] == [True, True, False]


def test_refills_at_rate():
    b, clock = make(capacity=1, rate=2.0)
    assert b.try_acquire()
    assert not b.try_acquire()
    clock.advance(0.5)
    assert b.try_acquire()


def test_failed_acquire_consumes_nothing():
    b, _ = make(capacity=2)
    assert not b.try_acquire(3)
    assert b.available == 2


def test_rejects_non_positive_n():
    b, _ = make()
    with pytest.raises(ValueError):
        b.try_acquire(0)
