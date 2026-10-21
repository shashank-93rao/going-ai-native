"""A tiny paired A/B harness for two versions of a prompt, plus a deploy gate.

Both versions run on the same JSONL rows, so the comparison is *paired*: what
matters is the rows where they disagree (discordant pairs), not the two
accuracies side by side. The significance test is an exact McNemar (a two-sided
binomial test on the discordant pairs). With 15 rows it will almost never be
significant, which is the point: the gate says "inconclusive" instead of
letting a +1 row difference ship. See ../../12-hill-climbing for power and
clustered errors.

Gate rules, in order:
  1. reject if any `must_pass` row that the baseline got right now fails
  2. reject if the schema-valid rate drops
  3. promote if the candidate wins more discordant pairs and p < alpha
  4. otherwise inconclusive: collect more rows, or soak on a canary

    python ab_harness.py log_triage 2 3          # fake model unless ANTHROPIC_API_KEY is set
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, Tracer, get_client

from log_triage import classify
from prompt_registry import PromptVersion, Registry

DATA = Path(__file__).parent / "data" / "triage_eval.jsonl"
SERVICES = "orders-api, payments-api, ledger-worker, search-api, billing-consumer"


def load_rows(path: str | Path = DATA) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


@dataclass
class RowResult:
    id: str
    valid: bool
    correct: bool
    got: dict[str, Any] | None
    errors: list[str]


@dataclass
class VersionRun:
    ref: str
    rows: list[RowResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return sum(r.correct for r in self.rows) / len(self.rows)

    @property
    def valid_rate(self) -> float:
        return sum(r.valid for r in self.rows) / len(self.rows)


def run_version(client: LLMClient, pv: PromptVersion, rows: list[dict[str, Any]], tracer: Tracer) -> VersionRun:
    system = pv.render(services=SERVICES) if "services" in pv.variables else pv.render()
    run = VersionRun(pv.ref)
    for row in rows:
        res = classify(client, system, row["excerpt"], tracer=tracer, prompt_ref=pv.ref)
        exp = row["expected"]
        correct = res.ok and all(res.output.get(k) == v for k, v in exp.items())
        run.rows.append(RowResult(row["id"], res.ok, correct, res.output, res.errors))
    return run


def mcnemar_exact(wins: int, losses: int) -> float:
    """Two-sided exact binomial p-value on discordant pairs (H0: p = 0.5)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


@dataclass
class Comparison:
    baseline: VersionRun
    candidate: VersionRun
    wins: list[str]
    losses: list[str]
    p_value: float
    decision: str
    reasons: list[str]


def compare(baseline: VersionRun, candidate: VersionRun, rows: list[dict[str, Any]], alpha: float = 0.05) -> Comparison:
    must = {r["id"] for r in rows if r.get("must_pass")}
    wins, losses, reasons = [], [], []
    for b, c in zip(baseline.rows, candidate.rows, strict=True):
        if c.correct and not b.correct:
            wins.append(c.id)
        elif b.correct and not c.correct:
            losses.append(c.id)
    p = mcnemar_exact(len(wins), len(losses))
    must_regressions = [i for i in losses if i in must]
    if must_regressions:
        decision = "reject"
        reasons.append(f"must_pass regression on {must_regressions}")
    elif candidate.valid_rate < baseline.valid_rate:
        decision = "reject"
        reasons.append(f"schema-valid rate fell {baseline.valid_rate:.0%} -> {candidate.valid_rate:.0%}")
    elif len(wins) > len(losses) and p < alpha:
        decision = "promote"
        reasons.append(f"{len(wins)} wins vs {len(losses)} losses, p={p:.4f}")
    else:
        decision = "inconclusive"
        reasons.append(f"{len(wins)} wins vs {len(losses)} losses, p={p:.4f} >= {alpha}; add rows or soak on canary")
    return Comparison(baseline, candidate, wins, losses, p, decision, reasons)


def report(c: Comparison) -> str:
    lines = [
        f"{'version':40} {'valid':>6} {'correct':>8}",
        f"{c.baseline.ref:40} {c.baseline.valid_rate:>6.0%} {c.baseline.accuracy:>8.0%}",
        f"{c.candidate.ref:40} {c.candidate.valid_rate:>6.0%} {c.candidate.accuracy:>8.0%}",
        f"wins (candidate right, baseline wrong): {c.wins or '-'}",
        f"losses (baseline right, candidate wrong): {c.losses or '-'}",
        f"exact McNemar p = {c.p_value:.4f}",
        f"decision: {c.decision.upper()} ({'; '.join(c.reasons)})",
    ]
    return "\n".join(lines)


def ab(client: LLMClient, name: str, base_v: int, cand_v: int, rows=None, tracer: Tracer | None = None,
       root: str | Path | None = None) -> Comparison:
    reg = Registry.load(root) if root else Registry.load()
    rows = rows if rows is not None else load_rows()
    tracer = tracer or Tracer()
    base = run_version(client, reg.get(name, base_v), rows, tracer)
    cand = run_version(client, reg.get(name, cand_v), rows, tracer)
    return compare(base, cand, rows)


def main(argv: list[str]) -> int:
    from sim_model import simulated_model

    name, base_v, cand_v = (argv + ["log_triage", "2", "3"][len(argv):])[:3]
    client = get_client(fake=FakeClient(simulated_model))
    c = ab(client, name, int(base_v), int(cand_v), tracer=Tracer("ab_traces.jsonl"))
    print(report(c))
    return 0 if c.decision == "promote" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
