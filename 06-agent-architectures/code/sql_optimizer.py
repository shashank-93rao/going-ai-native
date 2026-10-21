"""Worked example: evaluator-optimizer for SQL generation, with a REAL checker.

The evaluator is code, not a second model:
  1. guard: a single read-only SELECT/WITH statement (and the connection is query_only anyway)
  2. compile: EXPLAIN the query; SQLite's error message is the feedback
  3. execute under a VM-step budget (a cost cap, like statement_timeout)
  4. columns match the contract
  5. results match a reference query on a VISIBLE fixture and on a HIDDEN fixture.
     Feedback only describes the visible one, so the generator cannot overfit by hard-coding.

Run:  python sql_optimizer.py
"""

from __future__ import annotations

import random
import re
import sqlite3
from dataclasses import dataclass

from ainative_kit import FakeClient, LLMClient, Response, get_client
from patterns import Attempt, OptimizeResult, Verdict, ask, evaluator_optimizer

SCHEMA = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
                     status TEXT NOT NULL CHECK (status IN ('completed','cancelled','pending')),
                     created_at TEXT NOT NULL);  -- ISO-8601 UTC, e.g. 2026-09-30T14:05:00Z
CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
                          sku TEXT NOT NULL, qty INTEGER NOT NULL, unit_price_cents INTEGER NOT NULL);
"""

QUESTION = ("For completed orders created in September 2026 (UTC), return one row per region with "
            "columns region, order_count, revenue_cents (sum of qty * unit_price_cents), "
            "ordered by revenue_cents descending.")

REFERENCE_SQL = """
SELECT c.region, COUNT(DISTINCT o.id) AS order_count, SUM(oi.qty * oi.unit_price_cents) AS revenue_cents
FROM orders o JOIN customers c ON c.id = o.customer_id JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'completed' AND o.created_at >= '2026-09-01' AND o.created_at < '2026-10-01'
GROUP BY c.region ORDER BY revenue_cents DESC
"""

EXPECTED_COLUMNS = ["region", "order_count", "revenue_cents"]
VM_STEP_BUDGET = 2_000_000


def make_db(seed: int) -> sqlite3.Connection:
    """A deterministic fixture with the traps real data has: multi-item orders, cancelled
    orders, and timestamps on the afternoon of the last day of the month."""
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    regions = ["eu-west", "us-east", "ap-south"]
    for cid in range(1, 13):
        conn.execute("INSERT INTO customers VALUES (?,?,?)", (cid, f"cust{cid}", regions[cid % 3]))
    oid = iid = 0
    for _ in range(60):
        oid += 1
        day = rng.choice([1, 5, 12, 20, 29, 30, 30])
        month = rng.choice(["08", "09", "09", "09", "10"])
        ts = f"2026-{month}-{day:02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z"
        status = rng.choice(["completed", "completed", "completed", "cancelled", "pending"])
        conn.execute("INSERT INTO orders VALUES (?,?,?,?)", (oid, rng.randint(1, 12), status, ts))
        for _ in range(rng.randint(1, 4)):
            iid += 1
            conn.execute("INSERT INTO order_items VALUES (?,?,?,?,?)",
                         (iid, oid, f"SKU{rng.randint(1, 9)}", rng.randint(1, 3), rng.choice([499, 1299, 2500])))
    conn.commit()
    conn.execute("PRAGMA query_only = ON")          # defence in depth behind the static guard
    return conn


def run_limited(conn: sqlite3.Connection, sql: str) -> tuple[list[str], list[tuple]]:
    steps = {"n": 0}

    def tick() -> int:
        steps["n"] += 1000
        return 1 if steps["n"] > VM_STEP_BUDGET else 0   # non-zero aborts the statement
    conn.set_progress_handler(tick, 1000)
    try:
        cur = conn.execute(sql)
        return [d[0] for d in cur.description], cur.fetchall()
    finally:
        conn.set_progress_handler(None, 0)


@dataclass
class SqlChecker:
    visible: sqlite3.Connection
    hidden: sqlite3.Connection
    reference_sql: str = REFERENCE_SQL
    expected_columns: tuple[str, ...] = tuple(EXPECTED_COLUMNS)

    def __call__(self, sql: str) -> Verdict:
        sql = sql.strip().rstrip(";").strip()
        if ";" in sql or not re.match(r"(?is)^\s*(select|with)\b", sql):
            return Verdict(False, 0.0, "Must be exactly one SELECT (or WITH ... SELECT) statement.")
        try:
            self.visible.execute(f"EXPLAIN {sql}")
        except sqlite3.Error as e:
            return Verdict(False, 0.0, f"SQLite rejected the query: {e}")
        try:
            cols, rows = run_limited(self.visible, sql)
        except sqlite3.OperationalError as e:
            return Verdict(False, 0.1, f"Execution failed or exceeded the cost budget: {e}")
        if cols != list(self.expected_columns):
            return Verdict(False, 0.25, f"Columns are {cols}; the contract is {list(self.expected_columns)}.")
        _, want = run_limited(self.visible, self.reference_sql)
        if rows != want:
            return Verdict(False, 0.5, diff_feedback(rows, want))
        _, got_h = run_limited(self.hidden, sql)
        _, want_h = run_limited(self.hidden, self.reference_sql)
        if got_h != want_h:
            return Verdict(False, 0.75, "Correct on the visible fixture but wrong on a hidden one. "
                                        "Do not hard-code values; express the logic in SQL.")
        return Verdict(True, 1.0, "ok")


def diff_feedback(got: list[tuple], want: list[tuple]) -> str:
    """Specific, actionable, and does not reveal the reference query."""
    parts = [f"Wrong result on the visible fixture: {len(got)} rows, expected {len(want)}."]
    for g, w in zip(got, want):
        if g != w:
            parts.append(f"First differing row: got {g}, expected {w}.")
            if g[0] == w[0]:
                if g[1] > w[1]:
                    parts.append("order_count is too high: check for join fan-out or a missing filter.")
                elif g[1] < w[1]:
                    parts.append("order_count is too low: a filter is excluding rows; check range boundaries.")
                elif g[2] != w[2]:
                    parts.append("revenue differs with matching counts: check the arithmetic.")
            break
    return " ".join(parts)


GEN_SYSTEM = ("You write SQLite queries. Output only the SQL, no prose, no code fences.\n"
              f"Schema:\n{SCHEMA}")


def make_generator(client: LLMClient, question: str = QUESTION):
    def generate(history: list[Attempt]) -> str:
        prompt = question
        if history:
            prompt += "\n\nPrevious attempts and checker feedback:\n" + "\n".join(
                f"--- attempt {i + 1}\n{a.candidate}\nFEEDBACK: {a.verdict.feedback}" for i, a in enumerate(history))
        sql = ask(client, prompt, system=GEN_SYSTEM)
        m = re.search(r"```(?:sql)?\s*(.*?)```", sql, re.S)
        return m.group(1).strip() if m else sql.strip()
    return generate


def optimize_sql(client: LLMClient, *, visible_seed: int = 7, hidden_seed: int = 1009,
                 max_rounds: int = 4) -> OptimizeResult:
    checker = SqlChecker(make_db(visible_seed), make_db(hidden_seed))
    return evaluator_optimizer(make_generator(client), checker, max_rounds=max_rounds)


# Illustrative attempts a model might make; used by the offline demo and the tests.
ATTEMPT_FANOUT = """SELECT c.region, COUNT(*) AS order_count, SUM(oi.qty * oi.unit_price_cents) AS revenue_cents
FROM orders o JOIN customers c ON c.id = o.customer_id JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'completed' AND o.created_at BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY c.region ORDER BY revenue_cents DESC"""
ATTEMPT_BOUNDARY = ATTEMPT_FANOUT.replace("COUNT(*)", "COUNT(DISTINCT o.id)")
ATTEMPT_FIXED = ATTEMPT_BOUNDARY.replace(
    "o.created_at BETWEEN '2026-09-01' AND '2026-09-30'",
    "o.created_at >= '2026-09-01' AND o.created_at < '2026-10-01'")


def main() -> None:
    fake = FakeClient([Response(text=s) for s in (ATTEMPT_FANOUT, ATTEMPT_BOUNDARY, ATTEMPT_FIXED)])
    result = optimize_sql(get_client(fake=fake))
    for i, a in enumerate(result.attempts, 1):
        print(f"--- round {i}  score={a.verdict.score}  ok={a.verdict.ok}\n{a.candidate}\nFEEDBACK: {a.verdict.feedback}\n")
    print("stopped_by:", result.stopped_by)


if __name__ == "__main__":
    main()
