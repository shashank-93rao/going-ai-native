from orders import api
from orders.broker import FakeBroker
from orders.db import connect
from orders.outbox import TOPIC, lag, relay_once


def types_for(broker, key):
    return [m.value["type"] for m in broker.messages(TOPIC) if m.key == key]


def test_failed_cancel_is_retried_not_lost():
    conn, broker = connect(), FakeBroker()
    o = api.create_order(conn, "k1", "c1", 100)
    api.cancel_order(conn, "k2", o["order_id"])
    broker.fail_when(lambda key, value: value["type"] == "OrderCancelled")
    relay_once(conn, broker)
    assert lag(conn) == 1, "the unpublished cancel must still count as lag"
    broker.fail_when(None)
    relay_once(conn, broker)
    assert types_for(broker, o["order_id"]) == ["OrderPlaced", "OrderCancelled"]


def test_small_batches_publish_every_event():
    conn, broker = connect(), FakeBroker()
    o = api.create_order(conn, "k1", "c1", 100)
    api.cancel_order(conn, "k2", o["order_id"])
    relay_once(conn, broker, batch=1)
    relay_once(conn, broker, batch=1)
    assert types_for(broker, o["order_id"]) == ["OrderPlaced", "OrderCancelled"]
    assert lag(conn) == 0
