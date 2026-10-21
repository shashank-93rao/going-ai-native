from orders import api
from orders.broker import FakeBroker
from orders.consumer import StatsConsumer, drain, get_stats
from orders.db import connect
from orders.outbox import TOPIC, relay_once


def test_relay_republish_does_not_double_count():
    """Crash between publish and mark: the same event_id is republished at a new offset."""
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "c1", 100)
    api.create_order(conn, "k2", "c1", 250)
    relay_once(conn, broker)
    conn.execute("UPDATE outbox SET published_at = NULL")
    drain(conn, broker)
    assert get_stats(conn, "c1") == (2, 350)


def test_same_offset_redelivery_still_skipped():
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "c1", 100)
    relay_once(conn, broker)
    msg = broker.poll(TOPIC, "g")[0]
    c = StatsConsumer()
    c.handle(conn, msg)
    c.handle(conn, msg)
    assert get_stats(conn, "c1") == (1, 100)


def test_dedupe_key_is_event_id():
    conn, broker = connect(), FakeBroker()
    api.create_order(conn, "k1", "c1", 100)
    drain(conn, broker)
    row = conn.execute("SELECT event_id FROM processed_events").fetchone()
    outbox_id = conn.execute("SELECT id FROM outbox").fetchone()[0]
    assert row[0] == str(outbox_id)
