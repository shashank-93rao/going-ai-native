#!/usr/bin/env python3
"""Docs-freshness check: docs are the system of record, so stale docs fail the build.

Checks:
  D1 every backticked repo path in AGENTS.md / ARCHITECTURE.md / orders/AGENTS.md exists
  D2 every `see:` target in the lint rules points at an existing file and heading anchor
  D3 every module in orders/ is listed in ARCHITECTURE.md
  D4 AGENTS.md stays a map: at most 80 lines
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    from lint_invariants import RULES  # noqa: E402
except ImportError:  # lint not installed in this checkout
    RULES = {}

PATH_RE = re.compile(r"`((?:orders|tools|tests|docs)/[\w./-]+|[A-Z_]+\.md)`")
MAX_AGENTS_LINES = 80


def anchors(md: Path) -> set[str]:
    out = set()
    for line in md.read_text().splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip().lower()
            out.add(re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", title)))
    return out


def check(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for doc in ("AGENTS.md", "ARCHITECTURE.md", "orders/AGENTS.md"):
        if not (root / doc).exists():
            continue
        for ref in PATH_RE.findall((root / doc).read_text()):
            if not (root / ref).exists() and not (root / "orders" / ref).exists():
                problems.append(f"D1 {doc}: references `{ref}`, which does not exist")
    for rule, r in RULES.items():
        target, _, anchor = r["see"].partition("#")
        path = root / target
        if not path.exists():
            problems.append(f"D2 lint {rule}: see target {target} does not exist")
        elif anchor and anchor not in anchors(path):
            problems.append(f"D2 lint {rule}: anchor #{anchor} not found in {target}")
    arch_path = root / "ARCHITECTURE.md"
    arch = arch_path.read_text() if arch_path.exists() else None
    for mod in sorted((root / "orders").glob("*.py")):
        if arch is not None and mod.name != "__init__.py" and f"orders/{mod.name}" not in arch:
            problems.append(f"D3 ARCHITECTURE.md does not list orders/{mod.name}")
    agents = root / "AGENTS.md"
    n = len(agents.read_text().splitlines()) if agents.exists() else 0
    if n > MAX_AGENTS_LINES:
        problems.append(f"D4 AGENTS.md is {n} lines (max {MAX_AGENTS_LINES}); move detail into linked docs")
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(f"ERROR {p}")
    print(f"check_docs: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
