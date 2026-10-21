"""Customer-stats consumer: an idempotent read model fed from the orders topic (I4)."""

from __future__ import annotations

import sqlite3

from orders.broker import FakeBroker, Message
from orders.db import tx
from orders.obs import log
from orders.outbox import TOPIC, relay_once


class StatsConsumer:
    name = "customer-stats"

    def handle(self, conn: sqlite3.Connection, msg: Message) -> bool:
        """Apply one event. Returns False if it was a duplicate and was skipped."""
        ev = msg.value
        with tx(conn):
            try:
                conn.execute(
                    "INSERT INTO processed_events (consumer, event_id) VALUES (?, ?)",
                    (self.name, ev["event_id"]),
                )
            except sqlite3.IntegrityError:
                log("consumer", "event.duplicate_skipped", event_id=ev["event_id"], order_id=ev.get("order_id"),
                    partition=msg.partition, offset=msg.offset)
                return False
            if ev["type"] == "OrderPlaced":
                conn.execute(
                    "INSERT INTO customer_stats (customer_id, order_count, total_cents) VALUES (?, 1, ?) "
                    "ON CONFLICT(customer_id) DO UPDATE SET order_count = order_count + 1, "
                    "total_cents = total_cents + excluded.total_cents",
                    (ev["customer_id"], ev["amount_cents"]),
                )
        log("consumer", "event.applied", event_id=ev["event_id"], order_id=ev.get("order_id"), type=ev["type"],
            partition=msg.partition, offset=msg.offset)
        return True


def get_stats(conn: sqlite3.Connection, customer_id: str) -> tuple[int, int]:
    row = conn.execute("SELECT order_count, total_cents FROM customer_stats WHERE customer_id = ?", (customer_id,)).fetchone()
    return (row[0], row[1]) if row else (0, 0)


def drain(conn: sqlite3.Connection, broker: FakeBroker, consumer: StatsConsumer | None = None,
          group: str = "customer-stats") -> int:
    """Relay the outbox, then consume and commit everything available. Test/demo helper."""
    consumer = consumer or StatsConsumer()
    relay_once(conn, broker)
    applied = 0
    for msg in broker.poll(TOPIC, group, max_messages=10_000):
        applied += consumer.handle(conn, msg)
        broker.commit(group, msg)
    return applied
