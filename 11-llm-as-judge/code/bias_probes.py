"""Probes for judge biases: position, verbosity, run-to-run inconsistency, self-preference.

Each probe holds the content fixed and changes one nuisance variable (order,
padding, repetition). A judge with no bias gives the same answer either way.
The probes take plain callables so they work with any judge:

    pointwise: (item) -> bool                        e.g. lambda it: judge(client, rubric, it).passed
    pairwise:  (task, first, second) -> "1"|"2"|"tie"  e.g. functools.partial(ask_once, client, criterion=...)

    python bias_probes.py    # runs every probe against biased and unbiased fakes
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

Pointwise = Callable[[dict[str, Any]], bool]
Pairwise = Callable[[str, str, str], str]
DATA = Path(__file__).parent / "data"

# Content-free padding: restates nothing, adds no facts, only length and an air of diligence.
PADDING = (
    " This summary has been prepared following our standard incident communication process. The team has "
    "reviewed the full timeline, the contributing factors and the follow-up actions in detail, and will continue "
    "to monitor the affected systems closely to ensure stability going forward."
)


def pad(text: str, padding: str = PADDING) -> str:
    return text.rstrip() + padding


@dataclass(frozen=True)
class ProbeResult:
    name: str
    n: int
    rate: float          # the probe's headline number (see each probe for meaning)
    expected: float      # what an unbiased judge would score
    tolerance: float

    @property
    def flagged(self) -> bool:
        return abs(self.rate - self.expected) > self.tolerance

    def line(self) -> str:
        flag = "BIASED" if self.flagged else "ok"
        return f"{self.name:<28} n={self.n:<4} rate={self.rate:.2f}  expected~{self.expected:.2f}  [{flag}]"


def verbosity_probe_pointwise(
    judge: Pointwise, items: Sequence[dict[str, Any]], field: str = "summary", tolerance: float = 0.05
) -> ProbeResult:
    """Rate at which padding flips a FAIL to a PASS. Unbiased: 0."""
    base_fails = [it for it in items if not judge(it)]
    flips = sum(judge({**it, field: pad(it[field])}) for it in base_fails)
    n = len(base_fails)
    return ProbeResult("verbosity (pointwise)", n, flips / n if n else 0.0, 0.0, tolerance)


def verbosity_probe_pairwise(
    ask: Pairwise, pairs: Sequence[tuple[str, str]], tolerance: float = 0.10
) -> ProbeResult:
    """Pairs (task, response). Compare response vs pad(response) in both orders.

    Rate = share of non-tie votes that pick the padded copy. Unbiased: every vote is a
    tie, or picks split evenly, so the rate is 0.5 or there are no non-tie votes.
    """
    padded_wins = decided = 0
    for task, resp in pairs:
        for first_is_padded in (False, True):
            first, second = (pad(resp), resp) if first_is_padded else (resp, pad(resp))
            v = ask(task, first, second)
            if v == "tie":
                continue
            decided += 1
            padded_wins += (v == "1") == first_is_padded
    rate = padded_wins / decided if decided else 0.5
    return ProbeResult("verbosity (pairwise)", decided, rate, 0.5, tolerance)


def position_probe(ask: Pairwise, triples: Sequence[tuple[str, str, str]], tolerance: float = 0.10) -> ProbeResult:
    """Triples (task, a, b). Ask both orders; rate = share of non-tie votes that pick slot 1. Unbiased: 0.5."""
    first_wins = decided = 0
    for task, a, b in triples:
        for first, second in ((a, b), (b, a)):
            v = ask(task, first, second)
            if v != "tie":
                decided += 1
                first_wins += v == "1"
    rate = first_wins / decided if decided else 0.5
    return ProbeResult("position (slot-1 share)", decided, rate, 0.5, tolerance)


def swap_consistency(ask: Pairwise, triples: Sequence[tuple[str, str, str]], tolerance: float = 0.10) -> ProbeResult:
    """Share of pairs whose verdict changes when the order is swapped. Unbiased: 0."""
    flips = 0
    for task, a, b in triples:
        v1, v2 = ask(task, a, b), ask(task, b, a)
        same = (v1 == "tie" and v2 == "tie") or (v1 == "1" and v2 == "2") or (v1 == "2" and v2 == "1")
        flips += not same
    n = len(triples)
    return ProbeResult("position (swap flip rate)", n, flips / n if n else 0.0, 0.0, tolerance)


def double_run_consistency(judge: Pointwise, items: Sequence[dict[str, Any]], runs: int = 2, tolerance: float = 0.05) -> ProbeResult:
    """Share of items whose verdict differs across identical runs. Unbiased and stable: 0."""
    unstable = sum(len({judge(it) for _ in range(runs)}) > 1 for it in items)
    n = len(items)
    return ProbeResult(f"run-to-run ({runs} runs)", n, unstable / n if n else 0.0, 0.0, tolerance)


def self_preference_gap(rows: Iterable[dict[str, Any]], tolerance: float = 0.10) -> ProbeResult:
    """Rows: {'own_is_a': bool, 'judge': 'a'|'b'|'tie', 'human': 'a'|'b'|'tie'} for pairs where one side
    was written by the judge's own model. Rate = P(judge picks own) - P(human picks own). Unbiased: 0.
    Needs human pairwise labels; there is no way to measure this from judge output alone."""
    rs = list(rows)

    def own_share(key: str) -> float:
        picks = [r for r in rs if r[key] != "tie"]
        if not picks:
            return 0.5
        return sum((r[key] == "a") == r["own_is_a"] for r in picks) / len(picks)

    return ProbeResult("self-preference gap", len(rs), own_share("judge") - own_share("human"), 0.0, tolerance)


def main() -> None:
    from ainative_kit import FakeClient
    from judge import INCIDENT_IMPACT, judge
    from judge_fakes import (content_pairwise_judge, first_position_judge, incident_rules_judge,
                             longer_response_judge, padded_lenient_judge, rules_verdict)
    from pairwise import ask_once

    rows = [json.loads(line) for line in (DATA / "incident_summaries.jsonl").read_text().splitlines()]
    crit = "Which summary states the customer impact more correctly?"
    triples = [(r["facts"], r["summary"], o["summary"]) for r, o in zip(rows[0::6], rows[2::6])]
    singles = [(r["facts"], r["summary"]) for r in rows[0::6]]

    def pointwise(responder: Any) -> Pointwise:
        client = FakeClient(responder)
        return lambda it: judge(client, INCIDENT_IMPACT, it).passed

    def pairwise(responder: Any) -> Pairwise:
        client = FakeClient(responder)
        return lambda task, first, second: ask_once(client, task, first, second, crit)

    fair = content_pairwise_judge(lambda task, s: float(rules_verdict(task, s)[0]))
    print("== pointwise judges ==")
    for name, r in [("rules judge (v2)", incident_rules_judge), ("lenient-on-long judge", padded_lenient_judge)]:
        print(f"-- {name}")
        print("  " + verbosity_probe_pointwise(pointwise(r), rows).line())
        print("  " + double_run_consistency(pointwise(r), rows).line())
    print("== pairwise judges ==")
    for name, r in [("content-only", fair), ("always-first", first_position_judge), ("prefers-longer", longer_response_judge)]:
        ask = pairwise(r)
        print(f"-- {name}")
        print("  " + position_probe(ask, triples).line())
        print("  " + swap_consistency(ask, triples).line())
        print("  " + verbosity_probe_pairwise(ask, singles).line())


if __name__ == "__main__":
    main()
