"""SQLite schema and the one transaction helper every write must use.

See INVARIANTS.md: I1 (atomic state + outbox) relies on every write going
through `tx(conn)`, so that a state row and its outbox row commit together.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id           TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key          TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    response     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    aggregate_id TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    published_at REAL
);
CREATE TABLE IF NOT EXISTS processed_events (
    consumer TEXT NOT NULL,
    event_id TEXT NOT NULL,
    PRIMARY KEY (consumer, event_id)
);
CREATE TABLE IF NOT EXISTS customer_stats (
    customer_id TEXT PRIMARY KEY,
    order_count INTEGER NOT NULL,
    total_cents INTEGER NOT NULL
);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Open a connection in autocommit mode; transactions are explicit via tx()."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
