"""Order API: idempotent commands that write state and outbox rows atomically.

Invariants enforced here (see INVARIANTS.md):
  I1 every state change writes its event to the outbox in the same transaction
  I2 same Idempotency-Key + same request => same response, no new side effects
     same Idempotency-Key + different request => IdempotencyConflict (409)
  I5 status transitions follow PLACED -> CANCELLED only
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any

from orders.db import tx
from orders.obs import log


class OrderError(Exception):
    status = 400


class IdempotencyConflict(OrderError):
    status = 409


class InvalidTransition(OrderError):
    status = 409


class NotFound(OrderError):
    status = 404


def request_hash(op: str, body: dict[str, Any]) -> str:
    """Hash of the canonical request body. Only client-supplied fields belong here."""
    blob = json.dumps({"op": op, "body": body}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _replay(conn: sqlite3.Connection, key: str, rh: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT request_hash, response FROM idempotency_keys WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    if row[0] != rh:
        log("api", "idempotency.conflict", level="warn", idem_key=key, stored_hash=row[0], request_hash=rh)
        raise IdempotencyConflict(f"Idempotency-Key {key!r} was used with a different request")
    log("api", "idempotency.replay", idem_key=key)
    return json.loads(row[1])


def _remember(conn: sqlite3.Connection, key: str, rh: str, response: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO idempotency_keys (key, request_hash, response) VALUES (?, ?, ?)",
        (key, rh, json.dumps(response, sort_keys=True)),
    )


def _enqueue(conn: sqlite3.Connection, aggregate_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Write an event to the outbox. Must be called inside the caller's tx (I1)."""
    conn.execute(
        "INSERT INTO outbox (aggregate_id, event_type, payload) VALUES (?, ?, ?)",
        (aggregate_id, event_type, json.dumps(payload, sort_keys=True)),
    )


def create_order(conn: sqlite3.Connection, idem_key: str, customer_id: str, amount_cents: int) -> dict[str, Any]:
    if not customer_id:
        raise OrderError("customer_id is required")
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise OrderError("amount_cents must be a positive integer")
    body = {"customer_id": customer_id, "amount_cents": amount_cents}
    rh = request_hash("create_order", body)
    with tx(conn):
        cached = _replay(conn, idem_key, rh)
        if cached is not None:
            return cached
        order_id = "ord_" + hashlib.sha256(idem_key.encode()).hexdigest()[:10]
        conn.execute(
            "INSERT INTO orders (id, customer_id, amount_cents, status) VALUES (?, ?, ?, 'PLACED')",
            (order_id, customer_id, amount_cents),
        )
        _enqueue(conn, order_id, "OrderPlaced", {"order_id": order_id, "customer_id": customer_id, "amount_cents": amount_cents})
        response = {"order_id": order_id, "customer_id": customer_id, "amount_cents": amount_cents, "status": "PLACED"}
        _remember(conn, idem_key, rh, response)
    log("api", "order.placed", order_id=order_id, idem_key=idem_key, customer_id=customer_id)
    return response


def cancel_order(conn: sqlite3.Connection, idem_key: str, order_id: str) -> dict[str, Any]:
    body = {"order_id": order_id}
    rh = request_hash("cancel_order", body)
    with tx(conn):
        cached = _replay(conn, idem_key, rh)
        if cached is not None:
            return cached
        row = conn.execute("SELECT customer_id, amount_cents, status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise NotFound(order_id)
        customer_id, amount_cents, status = row
        if status != "PLACED":
            raise InvalidTransition(f"cannot cancel order in status {status}")
        conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
        _enqueue(conn, order_id, "OrderCancelled", {"order_id": order_id, "customer_id": customer_id, "amount_cents": amount_cents})
        response = {"order_id": order_id, "status": "CANCELLED"}
        _remember(conn, idem_key, rh, response)
    log("api", "order.cancelled", order_id=order_id, idem_key=idem_key)
    return response


def get_order(conn: sqlite3.Connection, order_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT id, customer_id, amount_cents, status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise NotFound(order_id)
    return dict(zip(("order_id", "customer_id", "amount_cents", "status"), row))


def _now() -> float:
    """Wall clock; never part of a request hash (see INVARIANTS.md I2)."""
    return time.time()
