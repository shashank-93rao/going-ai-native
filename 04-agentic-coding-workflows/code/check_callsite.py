"""Verifier for the emit_event -> publisher.publish migration. Exit 0 only if the file:

1. still parses (no syntax errors),
2. has no remaining legacy `emit_event(` calls, and
3. passes a partition `key=` on every `publisher.publish(...)` call.

This is the oracle the fan-out driver trusts. The agent's own "OK" is never enough.
Usage: python check_callsite.py FILE
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def problems(src: str) -> list[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"syntax error at line {e.lineno}: {e.msg}"]
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "emit_event":
            out.append(f"line {node.lineno}: legacy emit_event() call remains")
        if isinstance(fn, ast.Attribute) and fn.attr == "publish":
            if not any(k.arg == "key" for k in node.keywords):
                out.append(f"line {node.lineno}: publish() without key= loses per-entity ordering")
    return out


def main(argv: list[str] | None = None) -> int:
    path = Path((argv or sys.argv[1:])[0])
    found = problems(path.read_text())
    for p in found:
        print(f"{path}: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
