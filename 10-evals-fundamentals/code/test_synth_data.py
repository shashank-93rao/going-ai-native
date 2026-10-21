from synth_data import (DIMENSIONS, RULES, cross_product, draft_label, fake_alert_writer, filter_tuples,
                        generate_cases, stratified_sample, tuple_to_prompt)
from ainative_kit import FakeClient, text


def test_cross_product_size_and_filtering():
    full = cross_product(DIMENSIONS)
    expected = 1
    for v in DIMENSIONS.values():
        expected *= len(v)
    assert len(full) == expected
    valid = filter_tuples(full)
    assert 0 < len(valid) < len(full)
    assert all(rule(t) for t in valid for _, rule in RULES)
    assert not any(t["symptom"] == "outage" and t["impact"] == "none_yet" for t in valid)


def test_stratified_sample_covers_cover_dimensions():
    picked = stratified_sample(filter_tuples(cross_product(DIMENSIONS)), 12, seed=3)
    assert len(picked) == 12
    assert {t["subsystem"] for t in picked} == set(DIMENSIONS["subsystem"])
    assert {t["signal_quality"] for t in picked} == set(DIMENSIONS["signal_quality"])


def test_draft_labels_follow_the_rubric():
    base = {"subsystem": "kafka", "symptom": "latency", "impact": "customer_facing",
            "signal_quality": "clear", "source": "datadog"}
    assert draft_label(base) == {"decision": "route", "team": "streaming", "severity": "SEV2"}
    assert draft_label({**base, "signal_quality": "missing_service"})["decision"] == "abstain"
    assert draft_label({**base, "symptom": "outage"})["severity"] == "SEV1"


def test_prompt_states_the_tuple_but_not_the_label():
    t = stratified_sample(filter_tuples(cross_product(DIMENSIONS)), 1)[0]
    p = tuple_to_prompt(t)
    assert t["subsystem"] in p and "Do not say which team owns it" in p


def test_generate_cases_marks_review_and_rejects_bad_json():
    tuples = stratified_sample(filter_tuples(cross_product(DIMENSIONS)), 6, seed=0)
    cases, rejects = generate_cases(fake_alert_writer(), tuples)
    assert len(cases) == 6 and not rejects
    assert all(c["needs_review"] and c["origin"] == "synthetic" for c in cases)
    assert len({c["input"]["body"] for c in cases}) == 6
    bad, rej = generate_cases(FakeClient([text("Sure! Here is an alert:")]), tuples[:1])
    assert not bad and rej[0]["raw"].startswith("Sure")
