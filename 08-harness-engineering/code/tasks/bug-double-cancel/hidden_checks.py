import pytest

from orders import api
from orders.db import connect


def cancelled_events(conn):
    return conn.execute("SELECT COUNT(*) FROM outbox WHERE event_type = 'OrderCancelled'").fetchone()[0]


def test_second_cancel_with_new_key_is_rejected():
    conn = connect()
    r = api.create_order(conn, "k1", "c1", 100)
    api.cancel_order(conn, "k2", r["order_id"])
    with pytest.raises(api.InvalidTransition):
        api.cancel_order(conn, "k3", r["order_id"])
    assert cancelled_events(conn) == 1


def test_rejected_cancel_does_not_burn_the_key():
    conn = connect()
    r = api.create_order(conn, "k1", "c1", 100)
    api.cancel_order(conn, "k2", r["order_id"])
    with pytest.raises(api.InvalidTransition):
        api.cancel_order(conn, "k3", r["order_id"])
    assert conn.execute("SELECT COUNT(*) FROM idempotency_keys WHERE key = 'k3'").fetchone()[0] == 0


def test_same_key_cancel_retry_still_replays():
    conn = connect()
    r = api.create_order(conn, "k1", "c1", 100)
    first = api.cancel_order(conn, "k2", r["order_id"])
    assert api.cancel_order(conn, "k2", r["order_id"]) == first
    assert cancelled_events(conn) == 1
