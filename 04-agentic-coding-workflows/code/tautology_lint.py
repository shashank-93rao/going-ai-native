"""Heuristic linter for agent-written tests that cannot fail (or were quietly disarmed).

It is deliberately dumb and deterministic: it flags patterns worth a human look,
not proof of a bad test. Run it on the tests an agent added, and on the diff
it produced (to catch Kent Beck's "cheating" warning sign: deleted or skipped tests).

Rules (per test function):
  no-assertion        no assert, pytest.raises, or mock.assert_* call at all
  trivial-assert      `assert True`, `assert 1`, or `assert x == x` (identical sides)
  asserts-mock-return compares against `<mock>.return_value`, i.e. tests the mock
  oracle-from-impl    both sides of an == call functions imported from the module
                      under test, so the expected value is computed by the code being tested
  swallowed           assertion inside try/except that passes or returns
Rules (per diff):
  removed-assertions  more `assert` lines removed than added in test files
  added-skip          new @pytest.mark.skip / xfail / pytest.skip in test files

Usage:
  python tautology_lint.py tests/test_idempotency.py
  git diff main -- tests/ | python tautology_lint.py --diff -
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


_NOT_SUT = set(sys.stdlib_module_names) | {"pytest", "hypothesis", "unittest"}


@dataclass
class Finding:
    rule: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.where}: [{self.rule}] {self.detail}"


def _is_assertion_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
    return name.startswith("assert") or name in {"raises", "fail"}


def _calls_to(expr: ast.AST, names: set[str]) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in names
               for n in ast.walk(expr))


def _check_function(fn: ast.FunctionDef, sut_names: set[str], where: str) -> list[Finding]:
    out: list[Finding] = []
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    has_raises = any(isinstance(n, ast.With) and any(_is_assertion_call(i.context_expr) for i in n.items)
                     for n in ast.walk(fn))
    has_call_asserts = any(_is_assertion_call(n) for n in ast.walk(fn))
    if not asserts and not has_raises and not has_call_asserts:
        out.append(Finding("no-assertion", where, "test never asserts anything"))

    for a in asserts:
        t = a.test
        if isinstance(t, ast.Constant) and t.value:
            out.append(Finding("trivial-assert", f"{where}:{a.lineno}", "asserts a truthy constant"))
        if isinstance(t, ast.Compare) and len(t.comparators) == 1:
            left, right = t.left, t.comparators[0]
            if ast.dump(left) == ast.dump(right):
                out.append(Finding("trivial-assert", f"{where}:{a.lineno}", "both sides are identical"))
            for side in (left, right):
                if isinstance(side, ast.Attribute) and side.attr == "return_value":
                    out.append(Finding("asserts-mock-return", f"{where}:{a.lineno}",
                                       "compares against a mock's return_value: this tests the mock"))
            if isinstance(t.ops[0], ast.Eq) and sut_names and _calls_to(left, sut_names) \
                    and _calls_to(right, sut_names):
                out.append(Finding("oracle-from-impl", f"{where}:{a.lineno}",
                                   "expected value is computed by the code under test; use a literal"))

    for node in ast.walk(fn):
        if isinstance(node, ast.Try) and any(isinstance(n, ast.Assert) for b in node.body for n in ast.walk(b)):
            for h in node.handlers:
                if all(isinstance(s, (ast.Pass, ast.Return)) for s in h.body):
                    out.append(Finding("swallowed", f"{where}:{node.lineno}",
                                       "assertion inside try/except that swallows the failure"))
    return out


def lint_source(src: str, filename: str = "<test>") -> list[Finding]:
    tree = ast.parse(src)
    sut_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and (
                node.level > 0 or node.module.split(".")[0] not in _NOT_SUT):
            sut_names |= {a.asname or a.name for a in node.names}
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            findings += _check_function(node, sut_names, f"{filename}::{node.name}")
    return findings


def lint_diff(diff: str) -> list[Finding]:
    """Scan a unified diff for disarmed tests in files whose path looks like a test."""
    findings: list[Finding] = []
    current, added, removed = "", 0, 0

    def flush() -> None:
        if current and removed > added:
            findings.append(Finding("removed-assertions", current,
                                    f"{removed} assert lines removed, {added} added"))

    for line in diff.splitlines():
        if line.startswith("+++ "):
            flush()
            path = line[4:].removeprefix("b/")
            is_test = "test" in Path(path).name
            current, added, removed = (path if is_test else ""), 0, 0
            continue
        if not current or line.startswith(("---", "@@")):
            continue
        body = line[1:].strip()
        if line.startswith("+"):
            added += body.startswith("assert") or ".assert" in body
            if any(s in body for s in ("pytest.mark.skip", "pytest.mark.xfail", "pytest.skip(", "@unittest.skip")):
                findings.append(Finding("added-skip", current, f"new skip/xfail: {body[:80]}"))
        elif line.startswith("-"):
            removed += body.startswith("assert") or ".assert" in body
    flush()
    return findings


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ["--diff"]:
        src = sys.stdin.read() if args[1:] in ([], ["-"]) else Path(args[1]).read_text()
        findings = lint_diff(src)
    else:
        findings = [f for p in args for f in lint_source(Path(p).read_text(), p)]
    for f in findings:
        print(f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
