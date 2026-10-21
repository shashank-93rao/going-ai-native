#!/usr/bin/env python3
"""Invariant lint for the order service. Every error message is written for the agent.

Each finding prints four lines: location + rule, why it matters, how to fix it,
and where the invariant is documented. The fix line is the remediation text the
agent reads in its context window, so it is written as an instruction.

    python tools/lint_invariants.py            # lints orders/
    python tools/lint_invariants.py --json orders/api.py

Suppress a finding only with a reason:  # noqa: INV003 relay is single-key by design
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SQL_WRITE = re.compile(r"^\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(\w+)", re.IGNORECASE)
SQL_TXN = re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK)\b", re.IGNORECASE)
NONDETERMINISTIC = {"time", "now", "utcnow", "_now", "uuid4", "random", "monotonic"}

RULES = {
    "INV001": dict(
        title="state change without an outbox event",
        why="a write to `orders` that commits without its event means downstream never hears about it (lost update).",
        fix="call `_enqueue(conn, order_id, '<EventType>', payload)` inside the same `with tx(conn):` block, "
            "as `cancel_order` in orders/api.py does.",
        see="INVARIANTS.md#i1-atomic-state-and-event"),
    "INV002": dict(
        title="direct broker publish outside the outbox relay",
        why="publishing from request code is a dual write: the DB commit and the publish can disagree on crash.",
        fix="write the event with `_enqueue(...)` in the transaction and let `orders/outbox.py:relay_once` publish it.",
        see="docs/adr/0001-transactional-outbox.md"),
    "INV003": dict(
        title="publish failure swallowed inside the relay loop",
        why="skipping a failed row and publishing later rows reorders events for that key "
            "(OrderCancelled can overtake OrderPlaced).",
        fix="`break` out of the loop and leave the row unpublished so the next tick retries it in order. "
            "Never `continue` or `pass` in this handler.",
        see="INVARIANTS.md#i3-per-key-ordering"),
    "INV004": dict(
        title="read-model write without dedupe",
        why="delivery is at-least-once; a redelivered event would be applied twice (double counting).",
        fix="insert `(consumer, event_id)` into `processed_events` in the same transaction before the write, "
            "and return early on IntegrityError. Dedupe on event_id, never on partition/offset.",
        see="INVARIANTS.md#i4-idempotent-consumers"),
    "INV005": dict(
        title="non-deterministic value in an idempotency request hash",
        why="a clock, uuid or random value makes every retry hash differently, so retries 409 instead of replaying.",
        fix="hash only client-supplied body fields: `request_hash(op, body)` where body has no server-generated values.",
        see="INVARIANTS.md#i2-idempotent-commands"),
    "INV006": dict(
        title="manual transaction control",
        why="hand-rolled BEGIN/COMMIT makes it easy to commit state without the outbox row, or to leak a transaction.",
        fix="wrap the writes in `with tx(conn):` from orders/db.py and remove the manual commit/BEGIN.",
        see="INVARIANTS.md#i1-atomic-state-and-event"),
}


@dataclass
class Finding:
    path: str
    line: int
    col: int
    rule: str

    def render(self) -> str:
        r = RULES[self.rule]
        return (f"{self.path}:{self.line}:{self.col}: {self.rule} {r['title']}\n"
                f"  why: {r['why']}\n  fix: {r['fix']}\n  see: {r['see']}")


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _sql(node: ast.Call) -> str | None:
    if _call_name(node) in ("execute", "executemany") and node.args:
        a = node.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
    return None


def _check_function(fn: ast.AST, rel: str, out: list[Finding]) -> None:
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    names = {_call_name(c) for c in calls}
    writes: list[tuple[str, ast.Call]] = []
    for c in calls:
        sql = _sql(c)
        if sql and (m := SQL_WRITE.match(sql)):
            writes.append((m.group(2).lower(), c))
    tables = {t for t, _ in writes}
    for table, call in writes:
        if table == "orders" and "_enqueue" not in names and "outbox" not in tables:
            out.append(Finding(rel, call.lineno, call.col_offset, "INV001"))
        if table == "customer_stats" and "processed_events" not in tables:
            out.append(Finding(rel, call.lineno, call.col_offset, "INV004"))


def lint_source(src: str, rel: str) -> list[Finding]:
    tree = ast.parse(src)
    out: list[Finding] = []
    is_relay = rel.replace("\\", "/").endswith("outbox.py")
    is_db = rel.replace("\\", "/").endswith("db.py")
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_function(fn, rel, out)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "publish" and isinstance(node.func, ast.Attribute) and not is_relay:
                out.append(Finding(rel, node.lineno, node.col_offset, "INV002"))
            if name == "request_hash":
                inner = [c for a in node.args for c in ast.walk(a) if isinstance(c, ast.Call)]
                if any(_call_name(c) in NONDETERMINISTIC for c in inner):
                    out.append(Finding(rel, node.lineno, node.col_offset, "INV005"))
            sql = _sql(node)
            on_conn = isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in ("conn", "db", "connection", "cur", "cursor")
            manual = (name == "commit" and on_conn) or (sql is not None and SQL_TXN.match(sql))
            if manual and not is_db:
                out.append(Finding(rel, node.lineno, node.col_offset, "INV006"))
        if is_relay and isinstance(node, (ast.For, ast.While)):
            for h in (h for t in ast.walk(node) if isinstance(t, ast.Try) for h in t.handlers):
                if any(isinstance(s, (ast.Continue, ast.Pass)) for s in h.body):
                    out.append(Finding(rel, h.lineno, h.col_offset, "INV003"))
    lines = src.splitlines()
    kept = [f for f in out if not _suppressed(lines[f.line - 1], f.rule)]
    return sorted({(f.line, f.col, f.rule): f for f in kept}.values(), key=lambda f: (f.line, f.rule))


def _suppressed(line: str, rule: str) -> bool:
    """`# noqa: INV00X <reason>` suppresses; a bare noqa without a reason does not."""
    m = re.search(r"#\s*noqa:\s*(INV\d{3})\s+(\S.*)", line)
    return bool(m and m.group(1) == rule)


def lint_paths(paths: list[Path], root: Path) -> list[Finding]:
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    findings: list[Finding] = []
    for f in files:
        try:
            rel = str(f.resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(f)
        findings.extend(lint_source(f.read_text(), rel))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="files or dirs (default: orders/ next to this tool)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    service_root = Path(__file__).resolve().parent.parent
    paths = [Path(p) for p in args.paths] or [service_root / "orders"]
    root = Path.cwd() if args.paths else service_root
    findings = lint_paths(paths, root)
    if args.json:
        print(json.dumps([{**asdict(f), **RULES[f.rule]} for f in findings], indent=2))
    else:
        for f in findings:
            print(f.render())
        print(f"lint_invariants: {len(findings)} finding(s)" + ("" if findings else ", invariants hold"))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
