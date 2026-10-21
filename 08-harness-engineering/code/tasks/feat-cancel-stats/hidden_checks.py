from orders import api
from orders.broker import FakeBroker
from orders.consumer import StatsConsumer, drain, get_stats
from orders.db import connect
from orders.outbox import TOPIC


def setup():
    conn, broker = connect(), FakeBroker()
    a = api.create_order(conn, "k1", "c1", 100)
    api.create_order(conn, "k2", "c1", 250)
    api.create_order(conn, "k3", "c2", 999)
    api.cancel_order(conn, "k4", a["order_id"])
    return conn, broker


def test_cancel_decrements_count_and_total():
    conn, broker = setup()
    drain(conn, broker)
    assert get_stats(conn, "c1") == (1, 250)
    assert get_stats(conn, "c2") == (1, 999)


def test_cancel_survives_relay_republish():
    """I4: a republished OrderCancelled arrives at a new offset and must not decrement twice."""
    conn, broker = setup()
    drain(conn, broker)
    conn.execute("UPDATE outbox SET published_at = NULL")
    drain(conn, broker)
    assert get_stats(conn, "c1") == (1, 250)


def test_cancel_survives_same_offset_redelivery():
    conn, broker = setup()
    drain(conn, broker, group="g")
    c = StatsConsumer()
    for m in broker.messages(TOPIC):
        c.handle(conn, m)
    assert get_stats(conn, "c1") == (1, 250)
