import pytest

from orders import api
from orders.db import connect


@pytest.fixture
def conn():
    c = connect()
    # Insert in an order that differs from id order, so sorting by id would be wrong.
    for key, cust, amt in [("zz", "c1", 100), ("aa", "c1", 200), ("mm", "c2", 300), ("bb", "c1", 400)]:
        api.create_order(c, key, cust, amt)
    return c


def test_creation_order_and_shape(conn):
    rows = api.list_orders(conn, "c1")
    assert [r["amount_cents"] for r in rows] == [100, 200, 400]
    assert rows[0] == api.get_order(conn, rows[0]["order_id"])


def test_status_filter(conn):
    first = api.list_orders(conn, "c1")[0]
    api.cancel_order(conn, "cancel-1", first["order_id"])
    assert [r["order_id"] for r in api.list_orders(conn, "c1", status="CANCELLED")] == [first["order_id"]]
    assert len(api.list_orders(conn, "c1", status="PLACED")) == 2


def test_unknown_status_rejected(conn):
    with pytest.raises(api.OrderError):
        api.list_orders(conn, "c1", status="SHIPPED")


def test_other_customers_and_empty(conn):
    assert [r["customer_id"] for r in api.list_orders(conn, "c2")] == ["c2"]
    assert api.list_orders(conn, "nobody") == []


def test_is_read_only(conn):
    before = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    api.list_orders(conn, "c1")
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == before
