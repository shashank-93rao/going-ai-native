"""Visible tests for relay + consumer, using the hermetic FakeBroker."""

from orders import api
from orders.broker import FakeBroker
from orders.consumer import StatsConsumer, drain, get_stats
from orders.db import connect
from orders.outbox import TOPIC, lag, relay_once


def test_relay_publishes_in_order_and_marks_rows():
    conn, broker = connect(), FakeBroker()
    a = api.create_order(conn, "k1", "cust_1", 100)
    api.cancel_order(conn, "k2", a["order_id"])
    assert relay_once(conn, broker) == 2
    assert lag(conn) == 0
    assert [m.value["type"] for m in broker.messages(TOPIC)] == ["OrderPlaced", "OrderCancelled"]


def test_relay_leaves_rows_unpublished_when_broker_is_down():
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "cust_1", 100)
    broker.fail_next(1)
    assert relay_once(conn, broker) == 0
    assert lag(conn) == 1
    assert relay_once(conn, broker) == 1


def test_consumer_builds_stats():
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "cust_1", 100)
    api.create_order(conn, "k2", "cust_1", 250)
    drain(conn, broker)
    assert get_stats(conn, "cust_1") == (2, 350)


def test_consumer_skips_redelivered_message():
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "cust_1", 100)
    relay_once(conn, broker)
    msg = broker.poll(TOPIC, "g")[0]
    c = StatsConsumer()
    assert c.handle(conn, msg) is True
    assert c.handle(conn, msg) is False  # same offset redelivered after a rebalance
    assert get_stats(conn, "cust_1") == (1, 100)
