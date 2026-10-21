import json
from pathlib import Path

from hypothesis import given, strategies as st

from ainative_kit import Tracer, load_traces
from eval_harness import (load_jsonl, main, pass_at_k, pass_hat_k, router_run_fn, run_suite, summarize)
from graders import grade_router
from ticket_router import TEAMS

DATA = Path(__file__).parent / "data" / "router_cases.jsonl"


def test_dataset_shape():
    cases = load_jsonl(DATA)
    assert len(cases) >= 40
    assert len({c["id"] for c in cases}) == len(cases)
    slices = {c["slice"] for c in cases}
    assert {"abstain", "negative_control", "misleading_keyword"} <= slices
    for c in cases:
        e = c["expected"]
        assert c["split"] in ("dev", "test")
        if e["decision"] == "route":
            assert e["team"] in TEAMS and e["severity"] in ("SEV1", "SEV2", "SEV3", "SEV4")
        else:
            assert e["team"] is None and e["severity"] is None
    assert sum(c["split"] == "test" for c in cases) >= 10


def test_pass_at_k_known_values():
    assert pass_at_k(5, 0, 3) == 0.0 and pass_at_k(5, 5, 3) == 1.0
    assert abs(pass_hat_k(4, 3, 3) - 0.25) < 1e-9  # C(3,3)/C(4,3)
    assert abs(pass_at_k(4, 1, 2) - 0.5) < 1e-9    # 1 - C(3,2)/C(4,2)


@given(st.integers(1, 12).flatmap(lambda n: st.tuples(st.just(n), st.integers(0, n), st.integers(1, n))))
def test_pass_hat_k_never_exceeds_pass_at_k(args):
    n, c, k = args
    p = c / n
    assert pass_hat_k(n, c, k) <= p + 1e-9 and p <= pass_at_k(n, c, k) + 1e-9


def test_suite_is_deterministic_and_flaky_cases_split_pass_at_k_from_pass_hat_k():
    cases = load_jsonl(DATA)
    recs = run_suite(cases, router_run_fn(), grade_router, trials=5)
    again = run_suite(cases, router_run_fn(), grade_router, trials=5)
    assert [r["passed"] for r in recs] == [r["passed"] for r in again]
    s = summarize(recs, ks=(1, 3))["overall"]
    assert s["pass^3"] < s["pass@1"] < s["pass@3"]
    assert abs(s["correct"] + s["abstain"] + s["wrong"] - 1) < 1e-3
    assert s["abstention_aware_score"] < s["correct"]


def test_fake_flaws_show_up_in_the_slices():
    recs = run_suite(load_jsonl(DATA), router_run_fn(), grade_router, trials=3)
    s = summarize(recs, ks=(1,))
    assert s["by_slice"]["secret_in_body"]["pass_rate"] == 0.0
    assert s["by_slice"]["identity"]["pass_rate"] == 1.0
    assert {"schema", "severity", "team", "no_secret_echo"} <= set(s["failing_graders"])
    assert len(s["prompt_hashes"]) == 1


def test_crashing_system_is_a_failed_trial_not_a_crashed_eval():
    def boom(case, trial):
        raise TimeoutError("upstream 504")
    recs = run_suite([{"id": "a", "expected": {"decision": "route"}}], boom, grade_router, trials=2)
    assert [r["passed"] for r in recs] == [False, False] and "TimeoutError" in recs[0]["error"]


def test_traces_nest_under_eval_trial(tmp_path):
    tracer = Tracer(tmp_path / "t.jsonl")
    run_suite(load_jsonl(DATA)[:2], router_run_fn(tracer=tracer), grade_router, trials=1, tracer=tracer)
    traces = load_traces(tmp_path / "t.jsonl")
    assert len(traces) == 2
    spans = next(iter(traces.values()))
    assert {s["name"] for s in spans} == {"eval_trial", "route_alert", "llm_call"}
    root = next(s for s in spans if s["parent_id"] is None)
    assert "passed" in root["attrs"]


def test_cli_writes_results_and_summary(tmp_path, capsys):
    out = tmp_path / "res.jsonl"
    assert main(["--trials", "2", "--k", "1", "2", "--split", "test", "--out", str(out)]) == 0
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert rows and all(r["split"] == "test" for r in rows)
    assert json.loads(out.with_suffix(".summary.json").read_text())["overall"]["trials"] == len(rows)
    assert "OVERALL" in capsys.readouterr().out
