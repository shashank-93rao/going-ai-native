import pytest

from orders import api
from orders.db import connect


class Clock:
    def __init__(self, t: float = 1_760_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(api, "_now", c)
    monkeypatch.setattr(api.time, "time", c)
    return c


def test_retry_after_a_minute_replays(clock):
    conn = connect()
    first = api.create_order(conn, "k1", "c1", 100)
    clock.t += 61
    assert api.create_order(conn, "k1", "c1", 100) == first
    clock.t += 3600
    assert api.create_order(conn, "k1", "c1", 100) == first
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_different_body_still_conflicts(clock):
    """The fix must not paper over real conflicts."""
    conn = connect()
    api.create_order(conn, "k1", "c1", 100)
    clock.t += 61
    with pytest.raises(api.IdempotencyConflict):
        api.create_order(conn, "k1", "c1", 999)


def test_request_hash_is_a_pure_function_of_the_body(clock):
    h1 = api.request_hash("create_order", {"customer_id": "c1", "amount_cents": 100})
    clock.t += 10_000
    assert api.request_hash("create_order", {"customer_id": "c1", "amount_cents": 100}) == h1
