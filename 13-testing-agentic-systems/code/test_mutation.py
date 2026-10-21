"""Testing the tests: mutation score, tautology lint, and negative controls."""

from pathlib import Path

import pytest

from mutation_demo import TARGET, agent_written_suite, mutants, mutation_score, spec_suite
from tautology_lint import lint_source

HERE = Path(__file__).parent


def test_mutants_are_generated_and_differ():
    ms = mutants()
    assert len(ms) >= 8
    assert len({d for d, _ in ms}) >= 5


def test_spec_suite_kills_every_mutant():
    r = mutation_score(spec_suite)
    assert r.survivors == [] and r.score == 1.0


def test_agent_written_suite_kills_nothing():
    r = mutation_score(agent_written_suite)
    assert r.killed == 0 and r.total == len(mutants())


def test_suite_must_pass_on_original_before_scoring():
    with pytest.raises(AssertionError, match="ORIGINAL"):
        mutation_score(lambda g: [g([], "v2.4.0") is True])


def test_lint_flags_every_tautology_in_sample():
    rules = {f.rule for f in lint_source((HERE / "data" / "agent_written_test_sample.py.txt").read_text())}
    assert rules == {"no_assertion", "type_only", "self_comparison", "mock_echo", "swallowed_exception",
                     "always_true"}


@pytest.mark.parametrize("name", ["test_trajectories.py", "test_flaky.py", "test_replay.py"])
def test_lint_negative_control_on_this_modules_real_tests(name):
    """A linter that flags good tests trains people to ignore it."""
    assert lint_source((HERE / name).read_text()) == []


def test_target_is_the_real_guard():
    assert TARGET.__module__ == "trajectory_checks"
