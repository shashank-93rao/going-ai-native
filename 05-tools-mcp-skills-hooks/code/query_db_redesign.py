"""Before/after: a `query_db(q)` tool redesigned into tools an agent can use well.

Run `python query_db_redesign.py` to print the two transcripts' tool results side by side.
The database is an in-memory SQLite `payments` table seeded deterministically.

BEFORE: one generic tool. The model must guess the schema, writes raw SQL, gets back
`str(list_of_tuples)` with no column names and no limit, and sees raw driver errors.

AFTER: three tools shaped around the questions on-call actually asks:
  - payments_failure_summary: "why are payments failing for merchant X?" (aggregated, tiny)
  - payments_search: filtered, paginated rows, concise by default
  - payments_sql_readonly: an escape hatch that is read-only, row-capped, and whose
    errors list the real columns
"""

from __future__ import annotations

import random
import sqlite3
from typing import Any

from tool_formatter import ToolError, check_response_format, estimate_tokens, format_records

NOW = 1_760_000_000
MERCHANTS = {"m_5f1e0c9a-77b1-4c43-9d2e-1a6b3f0e8c21": "Acme Coffee",
             "m_0b7d2f44-1c8e-4a90-b3f6-9e2d5c7a1b08": "Northwind Books",
             "m_c3a9e1d7-5b2f-4e86-8a14-7f0c2b9d6e35": "Globex Rail"}
STATUSES = ["succeeded", "failed", "pending"]
FAILURE_CODES = ["card_declined", "issuer_timeout", "insufficient_funds", "do_not_honor"]
COLUMNS = ["id", "merchant_id", "amount_cents", "currency", "status", "failure_code", "created_at", "idempotency_key"]


def make_db(n: int = 600, seed: int = 7) -> sqlite3.Connection:
    rnd = random.Random(seed)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE merchants (id TEXT PRIMARY KEY, name TEXT)")
    db.execute("CREATE TABLE payments (id TEXT, merchant_id TEXT, amount_cents INT, currency TEXT, status TEXT,"
               " failure_code TEXT, created_at INT, idempotency_key TEXT)")
    db.executemany("INSERT INTO merchants VALUES (?, ?)", MERCHANTS.items())
    mids = list(MERCHANTS)
    for i in range(n):
        mid = mids[i % 3]
        # Globex has an issuer outage in the last 30 minutes: many issuer_timeouts.
        recent = rnd.random() < 0.3
        ts = NOW - (rnd.randint(0, 1800) if recent else rnd.randint(1801, 86400))
        if mid == mids[2] and recent:
            status = "failed" if rnd.random() < 0.6 else "succeeded"
            code = "issuer_timeout" if status == "failed" and rnd.random() < 0.85 else (rnd.choice(FAILURE_CODES) if status == "failed" else None)
        else:
            status = rnd.choices(STATUSES, weights=[90, 7, 3])[0]
            code = rnd.choice(FAILURE_CODES) if status == "failed" else None
        db.execute("INSERT INTO payments VALUES (?,?,?,?,?,?,?,?)",
                   (f"pay_{i:05d}_{rnd.getrandbits(48):012x}", mid, rnd.randint(100, 50000), "USD", status, code, ts,
                    f"idem_{rnd.getrandbits(64):016x}"))
    return db


# ---------------------------------------------------------------- BEFORE

BAD_QUERY_DB_SCHEMA = {
    "name": "query_db",
    "description": "Query the database.",
    "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
}


def bad_query_db(db: sqlite3.Connection, q: str) -> str:
    """What many first tools look like. Errors propagate as raw driver exceptions."""
    return str(db.execute(q).fetchall())


# ---------------------------------------------------------------- AFTER

def _resolve_merchant(db: sqlite3.Connection, merchant: str) -> tuple[str, str]:
    """Accept a human name (or an ID). Agents reason better over names than UUIDs."""
    rows = db.execute("SELECT id, name FROM merchants").fetchall()
    for mid, name in rows:
        if merchant in (mid, name) or merchant.lower() == name.lower():
            return mid, name
    partial = [name for _, name in rows if merchant.lower() in name.lower()]
    if len(partial) == 1:
        return next((mid, n) for mid, n in rows if n == partial[0])
    names = sorted(n for _, n in rows)
    raise ToolError(f"No merchant matches {merchant!r}. Known merchants: {names}. Pass the name exactly.")


def payments_failure_summary(db: sqlite3.Connection, merchant: str, since_minutes: int = 60) -> str:
    """Failure rate and failure codes for one merchant over a window, vs the prior 24h baseline."""
    if not 5 <= since_minutes <= 1440:
        raise ToolError(f"since_minutes must be 5..1440, got {since_minutes}.")
    mid, name = _resolve_merchant(db, merchant)
    since = NOW - since_minutes * 60

    def rate(lo: int, hi: int) -> tuple[int, int]:
        tot, fail = db.execute("SELECT COUNT(*), SUM(status='failed') FROM payments WHERE merchant_id=? "
                               "AND created_at>=? AND created_at<?", (mid, lo, hi)).fetchone()
        return tot, fail or 0

    tot, fail = rate(since, NOW + 1)
    btot, bfail = rate(NOW - 86400, since)
    codes = db.execute("SELECT failure_code, COUNT(*) FROM payments WHERE merchant_id=? AND created_at>=? "
                       "AND status='failed' GROUP BY failure_code ORDER BY 2 DESC", (mid, since)).fetchall()
    pct = lambda f, t: f"{100 * f / t:.1f}%" if t else "n/a"
    code_s = ", ".join(f"{c}={n}" for c, n in codes) or "none"
    return (f"merchant={name} window={since_minutes}m payments={tot} failed={fail} failure_rate={pct(fail, tot)} "
            f"(baseline prior 24h: {pct(bfail, btot)} of {btot}).\nfailure codes in window: {code_s}.")


def payments_search(db: sqlite3.Connection, merchant: str, status: str = "", failure_code: str = "",
                    since_minutes: int = 60, limit: int = 10, cursor: str = "", response_format: str = "concise") -> str:
    check_response_format(response_format)
    if status and status not in STATUSES:
        raise ToolError(f"status must be one of {STATUSES} or empty, got {status!r}.")
    if failure_code and failure_code not in FAILURE_CODES:
        raise ToolError(f"failure_code must be one of {FAILURE_CODES}, got {failure_code!r}.")
    if not 1 <= limit <= 50:
        raise ToolError(f"limit must be 1..50, got {limit}. Use payments_failure_summary for aggregates.")
    mid, name = _resolve_merchant(db, merchant)
    where, params = ["merchant_id=?", "created_at>=?"], [mid, NOW - since_minutes * 60]
    if status:
        where.append("status=?"), params.append(status)
    if failure_code:
        where.append("failure_code=?"), params.append(failure_code)
    w = " AND ".join(where)
    total = db.execute(f"SELECT COUNT(*) FROM payments WHERE {w}", params).fetchone()[0]
    offset = int(cursor or 0)
    rows = db.execute(f"SELECT {', '.join(COLUMNS)} FROM payments WHERE {w} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                      [*params, limit, offset]).fetchall()
    recs = [dict(zip(COLUMNS, r), merchant=name, age_min=(NOW - r[6]) // 60) for r in rows]
    nxt = str(offset + limit) if offset + limit < total else None
    return format_records(recs, response_format=response_format, total=total, next_cursor=nxt, noun="payments",
                          concise_fields=["age_min", "amount_cents", "status", "failure_code"],
                          refine_hint="Filter by status/failure_code, or use payments_failure_summary")


def payments_sql_readonly(db: sqlite3.Connection, sql: str, max_rows: int = 20) -> str:
    """Escape hatch: one read-only SELECT, row-capped, with column names and fixable errors."""
    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ToolError("Only a single SELECT (or WITH ... SELECT) is allowed. For writes, ask a human.")
    db.execute("PRAGMA query_only = ON")  # enforced by SQLite, not by string checks
    try:
        cur = db.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
    except sqlite3.OperationalError as e:
        if "readonly" in str(e):
            raise ToolError("This tool is read-only; the statement tried to write. Ask a human for writes.") from None
        raise ToolError(f"SQL error: {e}. Tables: payments({', '.join(COLUMNS)}), merchants(id, name). "
                        "Join merchants to filter by merchant name. Timestamps are epoch seconds.") from None
    finally:
        db.execute("PRAGMA query_only = OFF")
    more = len(rows) > max_rows
    out = [" | ".join(cols)] + [" | ".join(map(str, r)) for r in rows[:max_rows]]
    if more:
        out.append(f"[stopped at {max_rows} rows; add WHERE/LIMIT or aggregate with GROUP BY.]")
    return "\n".join(out)


GOOD_SCHEMAS: list[dict[str, Any]] = [
    {"name": "payments_failure_summary",
     "description": ("Failure rate and failure-code breakdown for ONE merchant over the last N minutes, compared with "
                     "the prior 24h. Start here for 'are payments failing for X' questions."),
     "input_schema": {"type": "object", "properties": {
         "merchant": {"type": "string", "description": "Merchant name, e.g. 'Globex Rail'."},
         "since_minutes": {"type": "integer", "minimum": 5, "maximum": 1440, "default": 60}},
         "required": ["merchant"]}},
    {"name": "payments_search",
     "description": "List individual payments for ONE merchant, newest first, filtered and paginated.",
     "input_schema": {"type": "object", "properties": {
         "merchant": {"type": "string"},
         "status": {"type": "string", "enum": STATUSES},
         "failure_code": {"type": "string", "enum": FAILURE_CODES},
         "since_minutes": {"type": "integer", "default": 60},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
         "cursor": {"type": "string"},
         "response_format": {"type": "string", "enum": ["concise", "detailed"], "default": "concise"}},
         "required": ["merchant"]}},
    {"name": "payments_sql_readonly",
     "description": ("Run ONE read-only SELECT against payments(" + ", ".join(COLUMNS) + ") and merchants(id, name). "
                     "Use only when the other payments_* tools cannot answer. Returns at most max_rows rows."),
     "input_schema": {"type": "object", "properties": {
         "sql": {"type": "string"}, "max_rows": {"type": "integer", "default": 20, "maximum": 100}},
         "required": ["sql"]}},
]


def demo() -> dict[str, str]:
    db = make_db()
    out: dict[str, str] = {}
    # BEFORE: the model guesses a column name, then dumps every row.
    try:
        bad_query_db(db, "SELECT * FROM payments WHERE merchant = 'Globex Rail' AND status_code = 'failed'")
    except Exception as e:  # what the agent loop would pass back verbatim
        out["before_1"] = f"{type(e).__name__}: {e}"
    out["before_2"] = bad_query_db(db, "SELECT * FROM payments WHERE status = 'failed'")
    # AFTER
    out["after_1"] = payments_failure_summary(db, "globex", since_minutes=30)
    out["after_2"] = payments_search(db, "Globex Rail", status="failed", since_minutes=30, limit=3)
    try:
        payments_sql_readonly(db, "SELECT merchant, COUNT(*) FROM payments GROUP BY merchant")
    except ToolError as e:
        out["after_3"] = str(e)
    return out


if __name__ == "__main__":
    for k, v in demo().items():
        print(f"--- {k} ({estimate_tokens(v)} tokens est.)\n{v[:600]}{' ...' if len(v) > 600 else ''}\n")
