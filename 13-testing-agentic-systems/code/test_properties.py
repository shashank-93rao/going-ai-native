"""Property-based and metamorphic tests with Hypothesis.

Hypothesis searches over seeds and fault plans the way Jepsen searches over
partitions: you state the invariant, it hunts for a counterexample and shrinks it.
`derandomize=True` keeps CI reproducible; drop it locally to explore more.
"""

from ainative_kit import FakeClient
from hypothesis import HealthCheck, find, given, settings
from hypothesis import strategies as st

from metamorphic import SEED_ALERTS, TRANSFORMS, apply, brittle_model, classify_alert, robust_model
from ops_agent import run_agent
from policies import noisy_policy, promote_policy
from trajectory_checks import check_claim_matches_state, check_forbidden
from world import FaultPlan, OpsWorld

CI = settings(max_examples=150, deadline=None, derandomize=True, database=None,
              suppress_health_check=[HealthCheck.too_slow])

seeds = st.integers(min_value=0, max_value=2**32 - 1)
rates = st.floats(min_value=0.0, max_value=0.4)


def _run(policy, seed, faults):
    world = OpsWorld(seed=seed, faults=faults)
    return run_agent(FakeClient(policy), world, max_steps=20), world


@CI
@given(seed=seeds, transient=rates, ack_loss=rates, version=st.sampled_from(["v2.4.0", "v2.4.1"]))
def test_good_agent_never_violates_invariants_under_any_fault_schedule(seed, transient, ack_loss, version):
    run, world = _run(promote_policy(version=version), seed, FaultPlan(transient, ack_loss))
    assert world.violations() == []
    assert check_claim_matches_state(run, world, "payments", version).passed
    prod = world.snapshot()["payments/prod"]
    # Either it shipped a healthy version, or prod was left exactly as it was.
    assert (prod["version"] == version and prod["healthy"]) or prod["version"] == "v2.3.0"


@CI
@given(seed=seeds, transient=rates, ack_loss=rates)
def test_retries_are_idempotent_final_state_matches_fault_free_run(seed, transient, ack_loss):
    """Metamorphic relation on the fault schedule: faults may cost steps, never change the outcome
    (unless the agent honestly gave up)."""
    faulty_run, faulty = _run(promote_policy(), seed, FaultPlan(transient, ack_loss))
    _, clean = _run(promote_policy(), seed, FaultPlan())
    if "Gave up" not in faulty_run.final_text:
        assert faulty.snapshot() == clean.snapshot()
    assert len({r.request_id for r in faulty.rollouts}) == len(faulty.rollouts)


@CI
@given(rid=st.text(min_size=1, max_size=8), repeats=st.integers(1, 6))
def test_deploy_tool_is_idempotent_per_request_id(rid, repeats):
    w = OpsWorld()
    first = w.execute("deploy", {"service": "payments", "env": "staging", "version": "v2.4.0", "request_id": rid})
    for _ in range(repeats - 1):
        again = w.execute("deploy", {"service": "payments", "env": "staging", "version": "v2.4.0", "request_id": rid})
        assert again["deduplicated"] and again["version"] == first["version"]
    assert len(w.rollouts) == 1


@CI
@given(seed=seeds)
def test_noisy_agent_never_calls_forbidden_tools_across_seeds(seed):
    run, _ = _run(noisy_policy(seed), seed, FaultPlan(0.1, 0.1))
    assert check_forbidden(run.steps).passed


def test_hypothesis_finds_the_retry_bug():
    """The new_id_on_retry bug only bites when an ack is lost. Hypothesis finds a seed where it does."""

    def duplicate_rollout(seed: int) -> bool:
        _, w = _run(promote_policy(new_id_on_retry=True), seed, FaultPlan(ack_loss_rate=0.2))
        return any("duplicate rollout" in v for v in w.violations())

    seed = find(seeds, duplicate_rollout, settings=settings(max_examples=500, derandomize=True, database=None))
    assert duplicate_rollout(seed)


# ----- metamorphic: paraphrase-invariant classification ----------------------
chains = st.lists(st.tuples(st.sampled_from(sorted(TRANSFORMS)), st.integers(0, 5)), min_size=1, max_size=3)


@CI
@given(alert=st.sampled_from(sorted(SEED_ALERTS)), chain=chains)
def test_classifier_is_paraphrase_invariant(alert, chain):
    client = FakeClient(robust_model)
    assert classify_alert(client, apply(alert, chain)) == classify_alert(client, alert) == SEED_ALERTS[alert]


def test_metamorphic_test_catches_brittle_classifier():
    client = FakeClient(brittle_model)

    def label_changes(case) -> bool:
        alert, chain = case
        return classify_alert(client, apply(alert, chain)) != classify_alert(client, alert)

    alert, chain = find(st.tuples(st.sampled_from(sorted(SEED_ALERTS)), chains), label_changes,
                        settings=settings(max_examples=500, derandomize=True, database=None))
    assert label_changes((alert, chain)) and any(name == "synonym" for name, _ in chain)
