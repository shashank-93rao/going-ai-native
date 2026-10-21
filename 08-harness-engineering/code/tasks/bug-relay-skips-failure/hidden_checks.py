from orders import api
from orders.broker import FakeBroker
from orders.db import connect
from orders.outbox import TOPIC, lag, relay_once


def per_key_types(broker, key):
    return [m.value["type"] for m in broker.messages(TOPIC) if m.key == key]


def test_failed_placed_is_not_overtaken_by_cancel():
    conn, broker = connect(), FakeBroker()
    o = api.create_order(conn, "k1", "c1", 100)
    api.cancel_order(conn, "k2", o["order_id"])
    broker.fail_when(lambda key, value: value["type"] == "OrderPlaced")
    relay_once(conn, broker)
    assert per_key_types(broker, o["order_id"]) == []
    broker.fail_when(None)
    while lag(conn):
        relay_once(conn, broker)
    assert per_key_types(broker, o["order_id"]) == ["OrderPlaced", "OrderCancelled"]


def test_persistent_outage_keeps_everything_in_order():
    conn, broker = connect(), FakeBroker()
    ids = [api.create_order(conn, f"k{i}", "c1", 100 + i)["order_id"] for i in range(3)]
    for i, oid in enumerate(ids):
        api.cancel_order(conn, f"c{i}", oid)
    broker.fail_next(3)  # several consecutive failures, not just one
    for _ in range(10):
        relay_once(conn, broker)
    for oid in ids:
        assert per_key_types(broker, oid) == ["OrderPlaced", "OrderCancelled"]
    assert lag(conn) == 0
