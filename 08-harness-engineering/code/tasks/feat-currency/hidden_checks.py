import json

import pytest

from orders import api
from orders.db import connect


@pytest.fixture
def conn():
    return connect()


def payload(conn):
    return json.loads(conn.execute("SELECT payload FROM outbox ORDER BY id DESC LIMIT 1").fetchone()[0])


def test_default_usd_everywhere(conn):
    r = api.create_order(conn, "k1", "c1", 100)
    assert r["currency"] == "USD"
    assert api.get_order(conn, r["order_id"])["currency"] == "USD"
    assert payload(conn)["currency"] == "USD"


def test_explicit_currency_stored_and_emitted(conn):
    r = api.create_order(conn, "k1", "c1", 100, currency="EUR")
    assert api.get_order(conn, r["order_id"])["currency"] == "EUR"
    assert payload(conn)["currency"] == "EUR"


@pytest.mark.parametrize("bad", ["usd", "US", "EURO", "U$D", "", 978])
def test_invalid_currency_rejected_without_side_effects(conn, bad):
    with pytest.raises(api.OrderError):
        api.create_order(conn, "k1", "c1", 100, currency=bad)
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_identical_retry_with_currency_replays(conn):
    first = api.create_order(conn, "k1", "c1", 100, currency="GBP")
    assert api.create_order(conn, "k1", "c1", 100, currency="GBP") == first
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_same_key_different_currency_conflicts(conn):
    """I2: currency is part of the request, so it must be part of the request hash."""
    api.create_order(conn, "k1", "c1", 100, currency="USD")
    with pytest.raises(api.IdempotencyConflict):
        api.create_order(conn, "k1", "c1", 100, currency="JPY")
