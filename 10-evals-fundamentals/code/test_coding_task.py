from pathlib import Path

from ainative_kit import Tracer, load_traces
from coding_task import (TASK, _script, coding_run_and_grade, grade_coding_trial, run_agent, setup_workdir,
                         execute_tool)
from ainative_kit import FakeClient
from eval_harness import run_suite, summarize
import pytest


def _trial(tmp_path, policy):
    shas = setup_workdir(tmp_path)
    run = run_agent(FakeClient(_script(policy)), tmp_path, Tracer())
    return run, grade_coding_trial(tmp_path, run, shas)


def _failed(graded):
    return {g["name"] for g in graded["grades"] if not g["passed"]}


def test_full_fix_passes_everything(tmp_path):
    run, g = _trial(tmp_path, "full_fix")
    assert g["passed"] and not _failed(g) and run["turns"] == 5


def test_partial_fix_passes_visible_tests_but_fails_hidden_outcome(tmp_path):
    _, g = _trial(tmp_path, "partial_fix")
    assert not g["passed"]
    assert _failed(g) == {"hidden_tests_pass", "claim_matches_outcome"}


def test_test_editor_is_caught_by_state_check(tmp_path):
    _, g = _trial(tmp_path, "test_editor")
    assert {"visible_tests_unchanged", "hidden_tests_pass"} <= _failed(g)
    assert "visible_tests_pass" not in _failed(g)  # the hack "works" on the visible suite


def test_tools_cannot_escape_the_repo(tmp_path):
    setup_workdir(tmp_path)
    with pytest.raises(PermissionError):
        execute_tool(tmp_path, "read_file", {"path": "../../etc/passwd"})


def test_suite_over_trials_shows_reliability_gap(tmp_path):
    tracer = Tracer(tmp_path / "c.jsonl")
    run_fn, grade_fn = coding_run_and_grade(tracer)
    recs = run_suite([TASK], run_fn, grade_fn, trials=10, tracer=tracer)
    s = summarize(recs, ks=(1, 3))["overall"]
    assert 0 < s["pass@1"] < 1 and s["pass^3"] < s["pass@1"] < s["pass@3"]
    traces = load_traces(tmp_path / "c.jsonl")
    assert len(traces) == 10
    names = {s["name"] for spans in traces.values() for s in spans}
    assert {"agent_run", "llm_call", "tool:read_file", "tool:run_tests"} <= names
