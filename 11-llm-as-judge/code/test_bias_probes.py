import json
import re
from pathlib import Path

from ainative_kit import FakeClient, tool

from bias_probes import (PADDING, double_run_consistency, pad, position_probe, self_preference_gap,
                         swap_consistency, verbosity_probe_pairwise, verbosity_probe_pointwise)
from judge import INCIDENT_IMPACT, judge
from judge_fakes import (content_pairwise_judge, first_position_judge, incident_rules_judge,
                         longer_response_judge, padded_lenient_judge, rules_verdict)
from pairwise import ask_once

DATA = Path(__file__).parent / "data"
ROWS = [json.loads(line) for line in (DATA / "incident_summaries.jsonl").read_text().splitlines()]
TRIPLES = [(r["facts"], r["summary"], o["summary"]) for r, o in zip(ROWS[0::6], ROWS[2::6])]
SINGLES = [(r["facts"], r["summary"]) for r in ROWS[0::6]]


def pointwise(responder):
    c = FakeClient(responder)
    return lambda it: judge(c, INCIDENT_IMPACT, it).passed


def pairwise(responder):
    c = FakeClient(responder)
    return lambda task, a, b: ask_once(c, task, a, b, "Which states customer impact correctly?")


FAIR = content_pairwise_judge(lambda task, s: float(rules_verdict(task, s)[0]))


def test_padding_is_content_free():
    assert not re.search(r"\d", PADDING)
    assert pad("x.").startswith("x.") and len(pad("x.")) > 200


def test_pointwise_verbosity_probe():
    assert not verbosity_probe_pointwise(pointwise(incident_rules_judge), ROWS).flagged
    biased = verbosity_probe_pointwise(pointwise(padded_lenient_judge), ROWS)
    assert biased.flagged and biased.rate > 0.9


def test_position_probes_flag_always_first():
    assert position_probe(pairwise(first_position_judge), TRIPLES).flagged
    assert swap_consistency(pairwise(first_position_judge), TRIPLES).rate == 1.0
    assert not position_probe(pairwise(FAIR), TRIPLES).flagged
    assert not swap_consistency(pairwise(FAIR), TRIPLES).flagged


def test_pairwise_verbosity_probe_flags_length_preference_only():
    assert verbosity_probe_pairwise(pairwise(longer_response_judge), SINGLES).rate == 1.0
    assert not verbosity_probe_pairwise(pairwise(FAIR), SINGLES).flagged
    # A position-biased judge picks padded and unpadded equally once both orders are run:
    # this is why every pairwise probe runs both orders.
    assert not verbosity_probe_pairwise(pairwise(first_position_judge), SINGLES).flagged


def test_double_run_flags_a_flaky_judge():
    state = {"n": 0}

    def flaky(messages, kwargs):
        state["n"] += 1
        return tool("record_verdict", {"critique": "?", "verdict": "pass" if state["n"] % 3 else "fail"})

    assert double_run_consistency(pointwise(flaky), ROWS[:30]).flagged
    assert not double_run_consistency(pointwise(incident_rules_judge), ROWS[:30]).flagged


def test_self_preference_gap():
    # The judge picks its own model's output in 10/10 pairs; humans pick it in 5/10.
    rows = [{"own_is_a": True, "judge": "a", "human": "a" if i < 5 else "b"} for i in range(8)] + \
           [{"own_is_a": False, "judge": "b", "human": "a" if i < 5 else "b"} for i in range(2)]
    r = self_preference_gap(rows)
    judge_own = 1.0
    human_own = (5 + 0) / 10
    assert r.rate == judge_own - human_own and r.flagged
    neutral = [{"own_is_a": i % 2 == 0, "judge": "a", "human": "a"} for i in range(10)]
    assert not self_preference_gap(neutral).flagged
