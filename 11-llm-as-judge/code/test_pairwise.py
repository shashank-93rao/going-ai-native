import pytest
from ainative_kit import FakeClient, text, tool

from judge_fakes import content_pairwise_judge, first_position_judge
from pairwise import PREFERENCE_TOOL, PairResult, ask_once, combine, compare, sign_test_p, summarize

TASK = "Summarise INC-2355 for the status page."
GOOD = "All API requests from ap-south-1 failed for 11 minutes, affecting 640 customers."
BAD = "Deploys to ap-south-1 were paused for 2 hours."
CRIT = "Which states the customer impact correctly?"


def quality(task, s):
    return float("640" in s)


@pytest.mark.parametrize("v_ab,v_ba,winner,consistent", [
    ("1", "2", "a", True),
    ("2", "1", "b", True),
    ("tie", "tie", "tie", True),
    ("1", "1", "tie", False),   # always picks slot 1: position bias
    ("2", "2", "tie", False),
    ("1", "tie", "tie", False),
])
def test_combine(v_ab, v_ba, winner, consistent):
    r = combine(v_ab, v_ba)
    assert (r.winner, r.consistent) == (winner, consistent)


def test_compare_runs_both_orders_blind():
    fake = FakeClient(content_pairwise_judge(quality))
    r = compare(fake, TASK, BAD, GOOD, CRIT)
    assert r.winner == "b" and r.consistent
    assert len(fake.calls) == 2
    first_call, second_call = (c["messages"][0]["content"] for c in fake.calls)
    assert first_call.index(BAD) < first_call.index(GOOD)
    assert second_call.index(GOOD) < second_call.index(BAD)
    for c in fake.calls:
        assert "baseline" not in c["messages"][0]["content"].lower()
        assert "baseline" not in c["system"].lower()
        assert c["tools"] == [PREFERENCE_TOOL]


def test_position_biased_judge_becomes_a_tie():
    r = compare(FakeClient(first_position_judge), TASK, BAD, GOOD, CRIT)
    assert r.winner == "tie" and not r.consistent and r.votes == ("1", "1")


def test_unparseable_preference_raises():
    with pytest.raises(ValueError):
        ask_once(FakeClient([text("Response 2 is better")]), TASK, GOOD, BAD, CRIT)
    with pytest.raises(ValueError):
        ask_once(FakeClient([tool("record_preference", {"winner": "B"})]), TASK, GOOD, BAD, CRIT)


def test_summary_counts_ties_as_half():
    rs = [PairResult("b", True, ("2", "1"))] * 6 + [PairResult("a", True, ("1", "2"))] * 2 + \
         [PairResult("tie", False, ("1", "1"))] * 2
    s = summarize(rs)
    assert (s.n, s.b_wins, s.a_wins, s.ties, s.inconsistent) == (10, 6, 2, 2, 2)
    assert s.b_win_rate == pytest.approx(0.7)
    assert s.inconsistency_rate == pytest.approx(0.2)


def test_sign_test():
    assert sign_test_p(10, 0) == pytest.approx(2 / 1024)
    assert sign_test_p(5, 5) == 1.0
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(6, 2) > 0.05  # 6-2 on 8 decided pairs is not evidence
