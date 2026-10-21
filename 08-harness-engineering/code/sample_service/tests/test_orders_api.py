"""Visible tests for the order API. Hidden task tests live outside this repo copy."""

import json

import pytest

from orders import api
from orders.db import connect


@pytest.fixture
def conn():
    return connect()


def outbox(conn):
    return [(t, json.loads(p)) for t, p in conn.execute("SELECT event_type, payload FROM outbox ORDER BY id")]


def test_create_writes_order_and_event_atomically(conn):
    r = api.create_order(conn, "k1", "cust_1", 1500)
    assert api.get_order(conn, r["order_id"])["status"] == "PLACED"
    [(event_type, payload)] = outbox(conn)
    assert event_type == "OrderPlaced"
    # Subset check: new payload fields are additive and must not break this contract test.
    assert {k: payload[k] for k in ("order_id", "customer_id", "amount_cents")} == {
        "order_id": r["order_id"], "customer_id": "cust_1", "amount_cents": 1500}


def test_identical_retry_replays_without_side_effects(conn):
    first = api.create_order(conn, "k1", "cust_1", 1500)
    assert api.create_order(conn, "k1", "cust_1", 1500) == first
    assert len(outbox(conn)) == 1


def test_same_key_different_body_conflicts(conn):
    api.create_order(conn, "k1", "cust_1", 1500)
    with pytest.raises(api.IdempotencyConflict):
        api.create_order(conn, "k1", "cust_1", 9999)


def test_failed_validation_writes_nothing(conn):
    with pytest.raises(api.OrderError):
        api.create_order(conn, "k1", "cust_1", 0)
    assert outbox(conn) == []


def test_cancel_emits_event_with_amount(conn):
    r = api.create_order(conn, "k1", "cust_1", 1500)
    api.cancel_order(conn, "k2", r["order_id"])
    assert [t for t, _ in outbox(conn)] == ["OrderPlaced", "OrderCancelled"]
    assert outbox(conn)[1][1]["amount_cents"] == 1500


def test_cancel_twice_with_new_key_is_invalid_transition(conn):
    r = api.create_order(conn, "k1", "cust_1", 1500)
    api.cancel_order(conn, "k2", r["order_id"])
    with pytest.raises(api.InvalidTransition):
        api.cancel_order(conn, "k3", r["order_id"])
    assert [t for t, _ in outbox(conn)].count("OrderCancelled") == 1


def test_cancel_unknown_order(conn):
    with pytest.raises(api.NotFound):
        api.cancel_order(conn, "k1", "ord_missing")
