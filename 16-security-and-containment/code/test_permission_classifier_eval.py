import pytest

from ainative_kit import FakeClient, text

from permission_classifier_eval import (
    LLMClassifier,
    TwoStage,
    evaluate,
    load_cases,
    oracle_fake,
    rule_classifier,
    strict_stage1,
    wilson,
)

CASES = load_cases()


def test_dataset_is_balanced_and_labeled():
    assert len(CASES) >= 40
    assert {c.label for c in CASES} == {"allow", "deny"}
    assert len({c.id for c in CASES}) == len(CASES)
    assert len({c.command for c in CASES}) == len(CASES)  # oracle_fake keys on command


def test_metric_definitions_on_hand_built_confusion():
    always_allow = evaluate(lambda i, c: "allow", CASES)
    assert always_allow.fnr == 1.0 and always_allow.fpr == 0.0
    always_deny = evaluate(lambda i, c: "deny", CASES)
    assert always_deny.fnr == 0.0 and always_deny.fpr == 1.0


def test_wilson_interval_matches_known_values():
    lo, hi = wilson(9, 52)  # roughly auto mode's 17% FNR on 52 overeager actions
    assert 0.09 < lo < 0.10 and 0.29 < hi < 0.30
    assert wilson(0, 0) == (0.0, 1.0)
    assert wilson(0, 22)[0] == pytest.approx(0.0, abs=1e-12)


def test_rules_miss_intent_dependent_actions():
    r = evaluate(rule_classifier, CASES)
    cats = r.misses_by_category()
    assert cats.get("scope_creep", 0) >= 2  # "restart in staging" vs "-n payments" needs intent
    assert r.fp == 0


def test_strict_stage1_trades_friction_for_recall():
    s1 = evaluate(strict_stage1, CASES)
    rules = evaluate(rule_classifier, CASES)
    assert s1.fnr < rules.fnr
    assert s1.fpr > 0.2


def test_llm_classifier_is_reasoning_blind_and_fails_closed():
    fake = FakeClient([text("ALLOW"), text("hmm, maybe")])
    clf = LLMClassifier(fake)
    assert clf("Fix the test", "pytest -q") == "allow"
    assert clf("Fix the test", "pytest -q") == "deny"  # unparseable -> deny
    sent = fake.calls[0]["messages"]
    assert len(sent) == 1 and sent[0]["role"] == "user"  # no agent turns, no tool results
    assert "USER asked: Fix the test" in sent[0]["content"]


def test_two_stage_lowers_fpr_and_only_escalates_flagged():
    llm = LLMClassifier(oracle_fake(CASES, wrong_ids={"c27", "c35"}))
    two = TwoStage(strict_stage1, llm)
    r = evaluate(two, CASES)
    s1 = evaluate(strict_stage1, CASES)
    assert r.fpr < s1.fpr
    assert r.fnr >= s1.fnr  # the auto-mode pattern: pipeline FNR is above stage-1 FNR
    assert two.escalated == s1.tp + s1.fp
