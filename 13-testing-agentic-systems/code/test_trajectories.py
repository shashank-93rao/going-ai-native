"""Agent runs against the simulated world, graded on outcome AND trajectory.

The parametrized negative controls are the point: each injected agent bug must
be caught by the specific check written for it. A check that never fails on a
known-bad run is a check you cannot trust.
"""

import pytest
from ainative_kit import FakeClient, Tracer

from ops_agent import run_agent
from policies import promote_policy
from trajectory_checks import (
    check_outcome, evaluate, failed, first_failure, format_matrix, transition_matrix, trajectory_summary,
)
from world import FaultPlan, OpsWorld


def run(policy_kw=None, *, seed=0, faults=None, version="v2.4.0"):
    world = OpsWorld(seed=seed, faults=faults)
    r = run_agent(FakeClient(promote_policy(version=version, **(policy_kw or {}))), world,
                  f"Deploy payments {version} to prod.")
    return r, world


def test_happy_path_outcome_and_trajectory():
    r, w = run()
    assert failed(evaluate(r, w, "payments", "v2.4.0")) == []
    assert [(s["tool"], s["env"]) for s in trajectory_summary(r)] == [
        ("deploy", "staging"), ("get_status", "staging"), ("deploy", "prod"), ("get_status", "prod")]
    assert w.snapshot()["payments/prod"] == {"version": "v2.4.0", "healthy": True, "replicas": 3}


def test_bad_version_aborts_and_leaves_prod_untouched():
    r, w = run(version="v2.4.1")
    assert failed(evaluate(r, w, "payments", "v2.4.1", expect_promotion=False)) == []
    assert w.snapshot()["payments/prod"]["version"] == "v2.3.0"
    assert w.snapshot()["payments/staging"] == {"version": "v2.3.0", "healthy": True, "replicas": 3}
    assert "Aborted" in r.final_text


def test_retries_under_ack_loss_reuse_request_id():
    # seed 3 with 50% ack loss produces at least one 'timeout, outcome unknown'
    r, w = run(seed=3, faults=FaultPlan(ack_loss_rate=0.5))
    assert any(s.result.get("error", "").startswith("timeout") for s in r.steps)
    assert failed(evaluate(r, w, "payments", "v2.4.0")) == []
    assert len([x for x in w.rollouts if x.env == "staging"]) == 1


@pytest.mark.parametrize("bug, faults, must_fail", [
    ({"skip_staging": True}, None, {"staging_verified_before_prod", "world_invariants"}),
    ({"skip_verify": True}, None, {"staging_verified_before_prod"}),
    ({"premature_stop": True}, None, {"claim_matches_state", "outcome:prod_at_version"}),
    ({"delete_prod_first": True}, None, {"no_forbidden_calls", "world_invariants"}),
    ({"loop_forever": True}, None, {"step_budget", "outcome:prod_at_version"}),
    ({"new_id_on_retry": True}, FaultPlan(ack_loss_rate=0.5), {"retry_reuses_request_id", "world_invariants"}),
])
def test_negative_controls_each_bug_is_caught_by_its_check(bug, faults, must_fail):
    r, w = run(bug, seed=3, faults=faults)
    assert set(failed(evaluate(r, w, "payments", "v2.4.0"))) == must_fail


def test_outcome_only_grading_misses_trajectory_bugs():
    """skip_verify and delete_prod_first both END in the right state. Outcome alone says pass."""
    for bug in ({"skip_verify": True}, {"delete_prod_first": True}):
        r, w = run(bug)
        assert check_outcome(w, "payments", "v2.4.0").passed
        assert failed(evaluate(r, w, "payments", "v2.4.0")) != []


def test_transition_failure_matrix_locates_first_failure():
    pairs = []
    for bug in ({"skip_verify": True}, {"premature_stop": True}, {"delete_prod_first": True}, {}):
        r, w = run(bug)
        pairs.append(first_failure(r, w, "payments", "v2.4.0"))
    assert pairs == [("deploy:staging", "deploy:prod"), ("deploy:staging", "report"),
                     ("get_status:staging", "delete_deployment:prod"), None]
    m = transition_matrix(pairs)
    assert m[("deploy:staging", "deploy:prod")] == 1 and sum(m.values()) == 3
    assert "deploy:prod" in format_matrix(m)


def test_world_is_deterministic_per_seed():
    """Test the simulator itself: same seed, same faults, same action log, byte for byte."""
    logs = []
    for _ in range(2):
        _, w = run(seed=42, faults=FaultPlan(0.2, 0.2))
        logs.append(w.action_log_jsonl())
    assert logs[0] == logs[1]
    _, other = run(seed=43, faults=FaultPlan(0.2, 0.2))
    assert other.action_log_jsonl() != logs[0]


def test_infra_error_is_reported_as_infra_not_as_agent_failure():
    r, _ = run(faults=FaultPlan(infra_crash_rate=1.0))
    assert r.stop_reason == "infra_error" and "seed=0" in r.infra_error


def test_trace_spans_capture_tool_calls():
    tracer = Tracer()
    run_agent(FakeClient(promote_policy()), OpsWorld(), tracer=tracer)
    names = [s.name for s in tracer.spans]
    assert names.count("tool:deploy") == 2 and names[-1] == "agent_run"
