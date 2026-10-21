"""Outbox relay: the only code allowed to publish to the broker (INVARIANTS.md I1, I3).

Delivery is at-least-once: we publish, then mark the row. A crash between the
two republishes the row on restart, so consumers must deduplicate (I4).
"""

from __future__ import annotations

import json
import sqlite3
import time

from orders.broker import BrokerError, FakeBroker
from orders.obs import log

TOPIC = "orders"


def relay_once(conn: sqlite3.Connection, broker: FakeBroker, batch: int = 100) -> int:
    """Publish up to `batch` unpublished events in outbox-id order. Returns count published."""
    rows = conn.execute(
        "SELECT id, aggregate_id, event_type, payload FROM outbox WHERE published_at IS NULL ORDER BY id LIMIT ?",
        (batch,),
    ).fetchall()
    published = 0
    for event_id, aggregate_id, event_type, payload in rows:
        value = {"event_id": str(event_id), "type": event_type, **json.loads(payload)}
        try:
            msg = broker.publish(TOPIC, key=aggregate_id, value=value)
        except BrokerError as e:
            log("relay", "publish.failed", level="error", event_id=str(event_id), order_id=aggregate_id, error=str(e))
            break  # I3: stop at the first failure; skipping ahead reorders events for this key
        conn.execute("UPDATE outbox SET published_at = ? WHERE id = ?", (time.time(), event_id))
        log("relay", "event.published", event_id=str(event_id), order_id=aggregate_id, type=event_type,
            partition=msg.partition, offset=msg.offset)
        published += 1
    return published


def lag(conn: sqlite3.Connection) -> int:
    """Number of outbox rows not yet published (an SLI worth alerting on)."""
    return conn.execute("SELECT COUNT(*) FROM outbox WHERE published_at IS NULL").fetchone()[0]
