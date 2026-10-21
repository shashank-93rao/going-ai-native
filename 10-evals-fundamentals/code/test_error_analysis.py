import csv
import json
from pathlib import Path

from ainative_kit import Tracer
from coding_task import TASK, coding_run_and_grade
from error_analysis import (_fake_proposer, axial_counts, format_report, grader_agreement, label_interactive,
                            main, propose_axial_codes, read_labels, render_trace, sample_traces, saturation_curve,
                            summarize_traces, transition_matrix, write_label_sheet)
from eval_harness import load_jsonl, router_run_fn, run_suite
from graders import grade_router

DATA = Path(__file__).parent / "data" / "router_cases.jsonl"


def _router_traces(tmp_path, trials=2):
    path = tmp_path / "traces.jsonl"
    tracer = Tracer(path)
    recs = run_suite(load_jsonl(DATA), router_run_fn(tracer=tracer), grade_router, trials, tracer)
    return path, recs


def test_summaries_carry_case_prompt_hash_and_output(tmp_path):
    path, _ = _router_traces(tmp_path, trials=1)
    traces = summarize_traces(path)
    assert len(traces) == len(load_jsonl(DATA))
    t = next(iter(traces.values()))
    assert t["case_id"].startswith("r") and len(t["prompt_hash"]) == 12 and t["input"]["title"]
    text = render_trace(t)
    assert "INPUT:" in text and "OUTPUT:" in text and "passed" not in text  # labeler is blind to the grader


def test_stratified_sample_covers_every_slice(tmp_path):
    path, _ = _router_traces(tmp_path)
    traces = summarize_traces(path)
    picked = sample_traces(traces, 12, seed=1, stratify_key="slice")
    n_slices = len({c["slice"] for c in load_jsonl(DATA)})
    assert len(picked) == 12 and len({t["slice"] for t in picked}) == n_slices
    assert sample_traces(traces, 12, seed=1, stratify_key="slice") == picked


def test_interactive_labeling_is_resumable_and_counts(tmp_path):
    path, recs = _router_traces(tmp_path, trials=1)
    traces = summarize_traces(path)
    sheet = tmp_path / "labels.csv"
    write_label_sheet(sample_traces(traces, 4, seed=0), sheet)
    answers = iter(["f", "routed on the word payments in a topic name", "keyword_overmatch",
                    "p", "", "q"])
    assert label_interactive(sheet, traces, "alice", input_fn=lambda _: next(answers), print_fn=lambda _: None) == 2
    answers2 = iter(["f", "guessed network instead of abstaining", "should_have_abstained", "s", "q"])
    assert label_interactive(sheet, traces, "alice", input_fn=lambda _: next(answers2), print_fn=lambda _: None) == 1
    labels = read_labels(sheet)
    assert axial_counts(labels) == {"keyword_overmatch": 1, "should_have_abstained": 1}
    assert saturation_curve(labels)[-1] == (3, 2)
    agree = grader_agreement(labels, recs)
    assert sum(agree.values()) == 3


def test_transition_matrix_from_agent_traces(tmp_path):
    tracer = Tracer(tmp_path / "c.jsonl")
    run_fn, grade_fn = coding_run_and_grade(tracer)
    run_suite([TASK], run_fn, grade_fn, trials=4, tracer=tracer)
    traces = summarize_traces(tmp_path / "c.jsonl")
    t = next(iter(traces.values()))
    assert t["state_path"] == ["inspect", "edit", "verify", "report"]
    labels = [
        {"pass_fail": "fail", "axial_code": "edited_tests", "last_good_state": "inspect", "first_failure_state": "edit"},
        {"pass_fail": "fail", "axial_code": "partial_fix", "last_good_state": "inspect", "first_failure_state": "edit"},
        {"pass_fail": "fail", "axial_code": "false_success_claim", "last_good_state": "verify", "first_failure_state": "report"},
        {"pass_fail": "pass", "axial_code": "", "last_good_state": "", "first_failure_state": ""},
    ]
    m = transition_matrix(labels)
    assert m["inspect"]["edit"] == 2 and m["verify"]["report"] == 1
    assert "transition failure matrix" in format_report([dict(l, open_code="", trace_id="", case_id="",
                                                              trial="", slice="", state_path="", labeler="")
                                                         for l in labels])


def test_propose_axial_codes_returns_a_reviewable_grouping():
    out = propose_axial_codes(_fake_proposer(), ["keyword payments in topic", "sev under-called", "json fenced"])
    assert out["assignments"]["sev under-called"] == "severity_miscalibrated"
    assert set(out["assignments"].values()) <= set(out["codes"])


def test_cli_sample_refuses_to_clobber_labels(tmp_path, capsys):
    path, _ = _router_traces(tmp_path, trials=1)
    out = tmp_path / "l.csv"
    assert main(["sample", "--traces", str(path), "--n", "5", "--out", str(out)]) == 0
    assert main(["sample", "--traces", str(path), "--n", "5", "--out", str(out)]) == 1
    assert main(["report", "--csv", str(out)]) == 0
    assert "labeled 0/5" in capsys.readouterr().out
