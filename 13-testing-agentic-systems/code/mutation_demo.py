"""Mutation testing, in miniature, on a trajectory check.

The function under test is `trajectory_checks.promotion_allowed`: the guard that
decides whether a prod deploy was preceded by a healthy staging verification.
If that check is wrong, every test built on it is wrong too. So we test the test:
generate small mutants of its source (flip a comparison, swap and/or, invert a
boolean) and count how many each test suite kills.

A suite that kills few mutants is not testing the logic. That is exactly what
agent-written suites that mirror the implementation look like.

    python mutation_demo.py
"""

from __future__ import annotations

import ast
import copy
import inspect
import textwrap
from dataclasses import dataclass
from typing import Any, Callable

import trajectory_checks
from ops_agent import Step

Guard = Callable[[list[Step], str], bool]
TARGET = trajectory_checks.promotion_allowed


# ----- mutant generation ----------------------------------------------------
class _Mutator(ast.NodeTransformer):
    """Applies exactly one mutation: the `target`-th mutation point encountered."""

    def __init__(self, target: int):
        self.target, self.seen, self.applied = target, 0, ""

    def _hit(self) -> bool:
        self.seen += 1
        return self.seen - 1 == self.target

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        swaps = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.Gt: ast.GtE}
        if type(node.ops[0]) in swaps and self._hit():
            self.applied = f"line {node.lineno}: {type(node.ops[0]).__name__} -> {swaps[type(node.ops[0])].__name__}"
            node.ops = [swaps[type(node.ops[0])]()]
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if self._hit():
            new = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            self.applied = f"line {node.lineno}: {type(node.op).__name__} -> {type(new).__name__}"
            node.op = new
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool) and self._hit():
            self.applied = f"line {node.lineno}: {node.value} -> {not node.value}"
            return ast.copy_location(ast.Constant(not node.value), node)
        return node


def mutants(fn: Callable[..., Any] = TARGET) -> list[tuple[str, Guard]]:
    """Every single-point mutant of `fn`, compiled, with a description."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    out: list[tuple[str, Guard]] = []
    i = 0
    while True:
        m = _Mutator(i)
        new_tree = ast.fix_missing_locations(m.visit(copy.deepcopy(tree)))
        if not m.applied:
            return out
        ns: dict[str, Any] = dict(fn.__globals__)
        exec(compile(new_tree, f"<mutant {i}>", "exec"), ns)
        out.append((m.applied, ns[fn.__name__]))
        i += 1


# ----- two suites against the same guard ----------------------------------------
def S(tool: str, env: str, **result: Any) -> Step:
    return Step(tool, {"service": "payments", "env": env}, result)


DEPLOY_OK = S("deploy", "staging", ok=True)
HEALTHY = S("get_status", "staging", version="v2.4.0", healthy=True)


def agent_written_suite(guard: Guard) -> list[bool]:
    """What an agent produces when told 'write tests for promotion_allowed':
    happy path only, expectations computed by calling the code under test."""
    steps = [DEPLOY_OK, HEALTHY]
    return [
        isinstance(guard(steps, "v2.4.0"), bool),
        guard(steps, "v2.4.0") == guard(list(steps), "v2.4.0"),
        guard(steps, "v2.4.0") == trajectory_checks.promotion_allowed(steps, "v2.4.0") or True,
    ]


def spec_suite(guard: Guard) -> list[bool]:
    """Derived from the rule, with negative controls: cases that MUST be rejected."""
    return [
        guard([DEPLOY_OK, HEALTHY], "v2.4.0") is True,
        guard([DEPLOY_OK], "v2.4.0") is False,  # never verified
        guard([DEPLOY_OK, S("get_status", "staging", version="v2.4.0", healthy=False)], "v2.4.0") is False,
        guard([DEPLOY_OK, S("get_status", "staging", version="v2.3.0", healthy=True)], "v2.4.0") is False,
        guard([HEALTHY, DEPLOY_OK], "v2.4.0") is False,  # verified, then a new rollout
        guard([DEPLOY_OK, S("get_status", "prod", version="v2.4.0", healthy=True)], "v2.4.0") is False,
        guard([], "v2.4.0") is False,
        # Added after the first mutation run: the 'and -> or' mutant survived without it.
        guard([DEPLOY_OK, HEALTHY, S("get_logs", "staging", lines=[])], "v2.4.0") is True,
    ]


@dataclass
class MutationScore:
    killed: int
    total: int
    survivors: list[str]

    @property
    def score(self) -> float:
        return self.killed / self.total if self.total else 0.0


def mutation_score(suite: Callable[[Guard], list[bool]], fn: Callable[..., Any] = TARGET) -> MutationScore:
    if not all(suite(fn)):
        raise AssertionError("suite fails on the ORIGINAL code; fix the suite first")
    killed, survivors = 0, []
    ms = mutants(fn)
    for desc, m in ms:
        try:
            dead = not all(suite(m))
        except Exception:  # a crash is a kill too
            dead = True
        killed += dead
        if not dead:
            survivors.append(desc)
    return MutationScore(killed, len(ms), survivors)


if __name__ == "__main__":
    for name, suite in [("agent-written suite", agent_written_suite), ("spec suite", spec_suite)]:
        r = mutation_score(suite)
        print(f"{name}: killed {r.killed}/{r.total} mutants ({r.score:.0%})")
        for s in r.survivors:
            print(f"    survived: {s}")
