"""Position-swapped, blinded pairwise comparison.

Each pair is judged twice: (A, B) and (B, A). The judge only ever sees
"Response 1" and "Response 2", never which one is the baseline. If the two
orders disagree, the result is a tie and the pair is flagged as position-inconsistent.

    python pairwise.py    # compares two summary prompts on the incident data, offline fake unless a key is set
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from ainative_kit import FakeClient, LLMClient, Response, get_client

Winner = Literal["a", "b", "tie"]
DATA = Path(__file__).parent / "data"

PREFERENCE_TOOL: dict[str, Any] = {
    "name": "record_preference",
    "description": "Record which response better satisfies the criterion. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "critique": {"type": "string", "description": "Compare the two on the criterion only, quoting both."},
            "winner": {"type": "string", "enum": ["1", "2", "tie"]},
        },
        "required": ["critique", "winner"],
    },
}

PAIRWISE_SYSTEM = """You compare two responses to the same task on ONE criterion.
Criterion: {criterion}
Rules:
- Judge only the criterion. Length, formatting and confidence are not evidence.
- The order of the responses is random and carries no information.
- If neither is better on the criterion, answer "tie".
Write the critique first, then call record_preference once."""


@dataclass(frozen=True)
class PairResult:
    winner: Winner
    consistent: bool           # both orders agreed (including both "tie")
    votes: tuple[str, str]     # raw winners: (order A-first, order B-first), each "1" | "2" | "tie"


def _render(task: str, first: str, second: str) -> str:
    return f"<task>\n{task}\n</task>\n<response_1>\n{first}\n</response_1>\n<response_2>\n{second}\n</response_2>"


def _parse(resp: Response) -> str:
    for tc in resp.tool_calls:
        if tc.name == PREFERENCE_TOOL["name"] and tc.input.get("winner") in ("1", "2", "tie"):
            return tc.input["winner"]
    raise ValueError(f"unparseable pairwise output: {resp.tool_calls!r} {resp.text[:200]!r}")


def ask_once(client: LLMClient, task: str, first: str, second: str, criterion: str, *, model: str | None = None) -> str:
    """One blinded judgement. Returns '1', '2' or 'tie' for the responses as shown."""
    resp = client.complete(
        [{"role": "user", "content": _render(task, first, second)}],
        system=PAIRWISE_SYSTEM.format(criterion=criterion),
        tools=[PREFERENCE_TOOL],
        model=model,
        max_tokens=1024,
    )
    return _parse(resp)


def combine(v_ab: str, v_ba: str) -> PairResult:
    """Map two order-specific votes back to A/B. Disagreement becomes a tie."""
    as_ab = {"1": "a", "2": "b", "tie": "tie"}[v_ab]
    as_ba = {"1": "b", "2": "a", "tie": "tie"}[v_ba]
    if as_ab == as_ba:
        return PairResult(as_ab, True, (v_ab, v_ba))  # type: ignore[arg-type]
    return PairResult("tie", False, (v_ab, v_ba))


def compare(client: LLMClient, task: str, a: str, b: str, criterion: str, **kw: Any) -> PairResult:
    """Judge (A, B) and (B, A) and combine."""
    return combine(ask_once(client, task, a, b, criterion, **kw), ask_once(client, task, b, a, criterion, **kw))


@dataclass(frozen=True)
class PairwiseSummary:
    n: int
    b_wins: int
    a_wins: int
    ties: int
    inconsistent: int

    @property
    def b_win_rate(self) -> float:
        """Ties count half. 0.5 means no detectable difference."""
        return (self.b_wins + 0.5 * self.ties) / self.n if self.n else float("nan")

    @property
    def inconsistency_rate(self) -> float:
        return self.inconsistent / self.n if self.n else float("nan")


def summarize(results: Iterable[PairResult]) -> PairwiseSummary:
    rs = list(results)
    return PairwiseSummary(
        n=len(rs),
        b_wins=sum(r.winner == "b" for r in rs),
        a_wins=sum(r.winner == "a" for r in rs),
        ties=sum(r.winner == "tie" for r in rs),
        inconsistent=sum(not r.consistent for r in rs),
    )


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact sign test, ties dropped. Small-n sanity check, not a substitute for module 12's stats."""
    from math import comb

    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * p)


def main() -> None:
    from judge_fakes import content_pairwise_judge, rules_verdict

    rows = [json.loads(line) for line in (DATA / "incident_summaries.jsonl").read_text().splitlines()]
    by_inc: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_inc.setdefault(r["incident_id"], []).append(r)
    facts = {k: v[0]["facts"] for k, v in by_inc.items()}
    # A = "baseline prompt" output (summary s4), B = "candidate prompt" output (summary s1), per incident.
    pairs = [(facts[k], v[3]["summary"], v[0]["summary"]) for k, v in by_inc.items()]

    def score(task: str, summary: str) -> float:  # the offline fake's notion of quality: does it pass the v2 rules?
        return float(rules_verdict(task, summary)[0])

    client = get_client(fake=FakeClient(content_pairwise_judge(score)))
    crit = "Which summary states the customer impact more correctly and completely, given the facts?"
    results = [compare(client, f"Summarise this incident for the status page.\n{f}", a, b, crit) for f, a, b in pairs]
    s = summarize(results)
    print(f"pairs={s.n}  B wins={s.b_wins}  A wins={s.a_wins}  ties={s.ties}  position-inconsistent={s.inconsistent}")
    print(f"B win rate (ties=0.5): {s.b_win_rate:.2f}   sign test p={sign_test_p(s.b_wins, s.a_wins):.3f}")


if __name__ == "__main__":
    main()
