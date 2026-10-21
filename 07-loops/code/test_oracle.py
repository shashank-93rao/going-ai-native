"""Oracle tests, including the course rule: prove the oracle can fail before you loop on it."""

import pytest

from oracle import CommandOracle, OracleResult, PytestOracle, prove_it_can_fail, replace_in
from toy_task import MUTANTS, make_workspace

STRONG = PytestOracle(["spec_tokenbucket.py"])
WEAK = PytestOracle(["spec_smoke.py"])


def test_buggy_workspace_fails_with_counts(tmp_path):
    r = STRONG.run(make_workspace(tmp_path))
    assert (r.passed, r.failed, r.ok) == (2, 3, False)
    assert r.score == pytest.approx(0.4)
    s = r.summary_for_agent()
    assert s.startswith("FAIL 3/5") and "FAILED spec_tokenbucket.py::test_refill_never_exceeds_capacity" in s


def test_fixed_workspace_passes(tmp_path):
    r = STRONG.run(make_workspace(tmp_path, fixed=True))
    assert r.ok and r.score == 1.0 and r.summary_for_agent() == "PASS 5/5"


def test_strong_oracle_kills_every_mutant(tmp_path):
    assert prove_it_can_fail(STRONG, make_workspace(tmp_path, fixed=True), MUTANTS) == []


def test_weak_oracle_lets_every_mutant_survive(tmp_path):
    survivors = prove_it_can_fail(WEAK, make_workspace(tmp_path, fixed=True), MUTANTS)
    assert set(survivors) == set(MUTANTS)


def test_prove_it_can_fail_rejects_a_red_baseline(tmp_path):
    with pytest.raises(AssertionError, match="known-good"):
        prove_it_can_fail(STRONG, make_workspace(tmp_path, fixed=False), MUTANTS)


def test_zero_tests_collected_is_broken_not_pass(tmp_path):
    ws = make_workspace(tmp_path, fixed=True)
    (ws / "spec_empty.py").write_text("# nothing here\n")
    r = PytestOracle(["spec_empty.py"]).run(ws)
    assert r.broken and not r.ok and r.score == 0.0
    assert r.summary_for_agent().startswith("ORACLE BROKEN")


def test_missing_oracle_file_is_broken(tmp_path):
    r = PytestOracle(["spec_nope.py"]).run(make_workspace(tmp_path, fixed=True))
    assert r.broken and not r.ok


def test_mutant_with_stale_snippet_fails_loudly(tmp_path):
    ws = make_workspace(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        replace_in("tokenbucket.py", "this text is not there", "x")(ws)


def test_command_oracle_uses_exit_code(tmp_path):
    assert CommandOracle("true").run(tmp_path).ok
    assert not CommandOracle("false").run(tmp_path).ok


def test_ok_requires_at_least_one_pass():
    assert not OracleResult(passed=0, failed=0, exit_code=0, output="").ok
