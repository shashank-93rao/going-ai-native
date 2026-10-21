"""Variant B scaffold tests: data is present and reproducible, the scorer gives the
right numbers on known-good and known-bad predictions, and pipeline v0 runs offline."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ainative_kit import FakeClient, Tracer, load_traces, text
from make_postmortems import generate
from pipeline_v0 import map_extract, naive_extractor_responder, parse_json_object, run_pipeline
from score import LABELS_PATH, SCALAR_FIELDS, SET_FIELDS, bootstrap_ci, field_counts, load_jsonl, paired_bootstrap, score

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def labels():
    return load_jsonl(LABELS_PATH)


def test_data_present_and_aligned(labels):
    docs = sorted(p.stem for p in (DATA / "postmortems").glob("*.md"))
    assert len(docs) >= 20 and docs == sorted(labels)


def test_committed_data_matches_generator(labels):
    for rec, doc in generate(len(labels)):
        assert labels[rec["doc_id"]] == rec
        assert (DATA / "postmortems" / f"{rec['doc_id']}.md").read_text() == doc


def test_hard_features_are_really_in_the_text(labels):
    for doc_id, gold in labels.items():
        doc = (DATA / "postmortems" / f"{doc_id}.md").read_text()
        if "sev_upgrade" in gold["hard_features"]:
            assert "**Severity:**" not in doc and "Upgraded to" in doc
        if "duration_prose" in gold["hard_features"]:
            assert "**Duration:**" not in doc
        if "no_customer_impact" in gold["hard_features"]:
            assert gold["customer_impact"] is False and "No customer-facing impact" in doc


def test_gold_scores_perfectly(labels):
    rep = score(copy.deepcopy(labels), labels)
    assert rep.micro["f1"] == 1.0 and not rep.errors


def test_empty_predictions_have_zero_recall(labels):
    rep = score({}, labels)
    assert rep.micro["recall"] == 0.0 and rep.micro["tp"] == 0


def test_wrong_scalar_counts_as_fp_and_fn():
    assert field_counts("severity", {"severity": "SEV1"}, {"severity": "SEV2"}) == (0, 1, 1)
    assert field_counts("severity", {}, {"severity": "SEV2"}) == (0, 0, 1)
    assert field_counts("severity", {"severity": " sev2 "}, {"severity": "SEV2"}) == (1, 0, 0)
    assert field_counts("duration_minutes", {"duration_minutes": 101}, {"duration_minutes": 100}, tol=2) == (1, 0, 0)
    assert field_counts("customer_impact", {"customer_impact": True}, {"customer_impact": False}) == (0, 1, 1)


def test_set_field_scored_per_element():
    assert field_counts("services_affected", {"services_affected": ["a", "b", "x"]},
                        {"services_affected": ["a", "b", "c"]}) == (2, 1, 1)


def test_decoy_services_hurt_precision_not_recall(labels):
    preds = copy.deepcopy(labels)
    for p in preds.values():
        p["services_affected"] = p["services_affected"] + ["search-decoy"]
    f = score(preds, labels).per_field["services_affected"]
    assert f["recall"] == 1.0 and f["precision"] < 1.0


def test_pipeline_v0_runs_offline_with_realistic_errors(tmp_path, labels):
    tracer = Tracer(tmp_path / "t.jsonl")
    preds, agg = run_pipeline(FakeClient(naive_extractor_responder), tracer=tracer)
    assert len(preds) == len(labels) and all(p["_parse_ok"] for p in preds)
    rep = score({p["doc_id"]: p for p in preds}, labels)
    assert 0.3 < rep.micro["f1"] < 0.95
    # The naive extractor is fooled exactly where the hard features say it should be.
    sev_errs = {e["doc_id"] for e in rep.errors if e["field"] == "severity"}
    assert sev_errs and all("sev_upgrade" in labels[d]["hard_features"] or "long_appendix" in labels[d]["hard_features"]
                            for d in sev_errs)
    assert rep.per_field["services_affected"]["precision"] < rep.per_field["services_affected"]["recall"]
    assert agg["incidents"] == len(labels) and agg["themes"] and agg["tokens_in"] > 0
    assert len(load_traces(tmp_path / "t.jsonl")) == len(labels)


def test_parse_failures_are_recorded_not_raised():
    row = map_extract(FakeClient([text("Sorry, I can't find a JSON here")]), "pm-x", "doc")
    assert row["_parse_ok"] is False and row["doc_id"] == "pm-x"
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_bootstrap_and_paired_comparison(labels):
    gold = copy.deepcopy(labels)
    worse = copy.deepcopy(labels)
    for p in worse.values():
        p["severity"] = None
    lo, hi = bootstrap_ci(worse, labels, n_boot=200)
    assert lo <= score(worse, labels).micro["f1"] <= hi
    same = paired_bootstrap(gold, gold, labels, n_boot=100)
    assert same["delta_f1"] == 0.0 and same["ci95"] == [0.0, 0.0]
    better = paired_bootstrap(worse, gold, labels, n_boot=200)
    assert better["delta_f1"] > 0 and better["ci95"][0] > 0 and better["p_b_not_better"] == 0.0


def test_scored_fields_cover_labels(labels):
    any_row = next(iter(labels.values()))
    assert set(SCALAR_FIELDS + SET_FIELDS) <= set(any_row)
    json.dumps(any_row)
