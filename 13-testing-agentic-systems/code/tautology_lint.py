"""A static linter for tautological tests, the kind agents write when asked to "add tests".

Heuristics (each one is a pattern seen in agent-written suites; none is proof):
  no_assertion         test body never asserts or uses pytest.raises
  constant_assert      `assert True`, `assert 1`
  always_true          `assert <expr> or True`
  self_comparison      `assert f(x) == f(x)`: both sides are the same expression
  mock_echo            asserts a mock returns the value the test just configured
  type_only            the only assertions are isinstance / is not None checks
  swallowed_exception  `except ...: pass` inside a test

Run it in CI on agent-authored test diffs and route hits to a human, or feed them
back to the agent as a lint error that says how to fix it.

    python tautology_lint.py data/agent_written_test_sample.py.txt
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    test: str
    rule: str
    line: int

    def __str__(self) -> str:
        return f"{self.test}:{self.line}: {self.rule}"


FIX_HINT = {
    "no_assertion": "assert on an observable outcome (world state, return value), not just that it ran",
    "constant_assert": "replace with an assertion on a value the code produced",
    "always_true": "remove `or True`; the assertion can never fail",
    "self_comparison": "compare against an expected value written from the spec, not recomputed by the code",
    "mock_echo": "assert on what the code under test DID with the mock, not what the mock returns",
    "type_only": "add an assertion on the value itself, and a negative case that must fail",
    "swallowed_exception": "use pytest.raises, or let the exception fail the test",
}


def _is_type_only(a: ast.Assert) -> bool:
    t = a.test
    if isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and t.func.id in {"isinstance", "callable"}:
        return True
    return isinstance(t, ast.Compare) and isinstance(t.ops[0], ast.IsNot) and \
        isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value is None


def _mock_names(fn: ast.FunctionDef) -> set[str]:
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute) and tgt.attr == "return_value" and isinstance(tgt.value, ast.Name):
                    names.add(tgt.value.id)
    return names


def lint_test_function(fn: ast.FunctionDef) -> list[Finding]:
    out: list[Finding] = []
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    raises = any(isinstance(n, ast.Attribute) and n.attr == "raises" for n in ast.walk(fn))
    if not asserts and not raises:
        out.append(Finding(fn.name, "no_assertion", fn.lineno))
    mocks = _mock_names(fn)
    for a in asserts:
        t = a.test
        if isinstance(t, ast.Constant) and t.value:
            out.append(Finding(fn.name, "constant_assert", a.lineno))
        if isinstance(t, ast.BoolOp) and isinstance(t.op, ast.Or) and any(
                isinstance(v, ast.Constant) and v.value is True for v in t.values):
            out.append(Finding(fn.name, "always_true", a.lineno))
        if isinstance(t, ast.Compare) and len(t.comparators) == 1 and \
                ast.dump(t.left) == ast.dump(t.comparators[0]):
            out.append(Finding(fn.name, "self_comparison", a.lineno))
        if isinstance(t, ast.Compare):
            for side in (t.left, *t.comparators):
                if isinstance(side, ast.Call) and isinstance(side.func, ast.Name) and side.func.id in mocks:
                    out.append(Finding(fn.name, "mock_echo", a.lineno))
    if asserts and all(_is_type_only(a) for a in asserts):
        out.append(Finding(fn.name, "type_only", fn.lineno))
    for node in ast.walk(fn):
        if isinstance(node, ast.ExceptHandler) and all(isinstance(b, ast.Pass) for b in node.body):
            out.append(Finding(fn.name, "swallowed_exception", node.lineno))
    return out


def lint_source(source: str) -> list[Finding]:
    tree = ast.parse(source)
    return [f for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
            for f in lint_test_function(node)]


if __name__ == "__main__":
    for path in sys.argv[1:] or [str(Path(__file__).parent / "data" / "agent_written_test_sample.py.txt")]:
        findings = lint_source(Path(path).read_text())
        print(f"{path}: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}  -> {FIX_HINT[f.rule]}")
