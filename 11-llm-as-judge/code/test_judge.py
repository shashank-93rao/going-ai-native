import json
from pathlib import Path

import pytest
from ainative_kit import FakeClient, text, tool

from judge import (CODE_REVIEW_BUG, fingerprint, INCIDENT_IMPACT, VERDICT_TOOL, JudgeOutputError, judge, judge_many,
                   load_jsonl, parse_verdict, render_item, render_system, with_few_shot)
from judge_fakes import incident_keyword_judge, incident_rules_judge

DATA = Path(__file__).parent / "data"
ROWS = load_jsonl(DATA / "incident_summaries.jsonl")
ITEM = ROWS[0]


def test_schema_puts_critique_before_verdict():
    props = list(VERDICT_TOOL["input_schema"]["properties"])
    assert props == ["critique", "verdict"]
    assert VERDICT_TOOL["input_schema"]["properties"]["verdict"]["enum"] == ["pass", "fail"]


def test_system_prompt_has_one_question_and_checkable_claims():
    s = render_system(INCIDENT_IMPACT)
    assert s.count("Question:") == 1
    for claim in INCIDENT_IMPACT.pass_claims:
        assert claim in s
    assert "record_verdict" in s
    assert "Do NOT consider" in s  # out-of-scope list keeps the judge to one failure mode
    assert "1-5" not in s and "scale" not in s.lower()


def test_judge_sends_inputs_as_tags_and_parses_tool_call():
    fake = FakeClient([tool("record_verdict", {"critique": "Count and scope match.", "verdict": "pass"})])
    v = judge(fake, INCIDENT_IMPACT, ITEM)
    assert v.passed and v.critique == "Count and scope match."
    call = fake.calls[0]
    assert call["tools"] == [VERDICT_TOOL]
    content = call["messages"][0]["content"]
    assert "<facts>" in content and "<summary>" in content
    assert "human_label" not in content and ITEM["human_critique"] not in content  # no label leakage


def test_json_text_fallback():
    v = parse_verdict(text('Here you go: {"critique": "Missing count.", "verdict": "fail"}'))
    assert not v.passed and "Missing" in v.critique


@pytest.mark.parametrize("resp", [text("PASS"), text('{"verdict": "maybe"}'), tool("other_tool", {"verdict": "pass"})])
def test_unparseable_output_is_an_error_not_a_pass(resp):
    with pytest.raises(JudgeOutputError):
        parse_verdict(resp)


def test_judge_many_records_errors_explicitly():
    fake = FakeClient([text("looks fine to me"), tool("record_verdict", {"critique": "ok", "verdict": "pass"})])
    out = judge_many(fake, INCIDENT_IMPACT, ROWS[:2])
    assert [o["judge_label"] for o in out] == ["error", "pass"]


def test_few_shot_uses_train_split_only_and_is_balanced():
    r = with_few_shot(INCIDENT_IMPACT, ROWS, k=4)
    assert r.few_shot and all(ex["split"] == "train" for ex in r.few_shot)
    labels = [ex["human_label"] for ex in r.few_shot]
    assert labels.count("pass") == 2 and labels.count("fail") == 2
    s = render_system(r)
    assert s.count("<example>") == 4
    assert INCIDENT_IMPACT.few_shot == ()  # original rubric untouched


def test_rules_judge_beats_keyword_judge_on_dev():
    dev = [r for r in ROWS if r["split"] == "dev"]

    def agree(responder):
        c = FakeClient(responder)
        return sum(judge(c, INCIDENT_IMPACT, r).passed == (r["human_label"] == "pass") for r in dev) / len(dev)

    assert agree(incident_rules_judge) > agree(incident_keyword_judge)


def test_code_review_rubric_renders_diff_and_comment():
    row = load_jsonl(DATA / "code_review_comments.jsonl")[0]
    s = render_item(CODE_REVIEW_BUG, row)
    assert "<diff>" in s and "<comment>" in s and "<language>" in s
    assert "Trace the code" in render_system(CODE_REVIEW_BUG)


def test_committed_judge_labels_match_current_v2_judge():
    """data/incident_judge_labels.jsonl must be regenerated whenever the judge changes."""
    committed = {r["id"]: r["judge_label"] for r in load_jsonl(DATA / "incident_judge_labels.jsonl")}
    client = FakeClient(incident_rules_judge)
    rubric = with_few_shot(INCIDENT_IMPACT, ROWS)
    fresh = {o["id"]: o["judge_label"] for o in judge_many(client, rubric, [r for r in ROWS if r["split"] != "train"])}
    assert committed == fresh


def test_fingerprint_changes_with_prompt_or_model():
    base = fingerprint(INCIDENT_IMPACT, "claude-opus-5-5")
    assert base == fingerprint(INCIDENT_IMPACT, "claude-opus-5-5")
    assert base != fingerprint(INCIDENT_IMPACT, "claude-sonnet-5-5")
    assert base != fingerprint(with_few_shot(INCIDENT_IMPACT, ROWS), "claude-opus-5-5")
