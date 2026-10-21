"""Ralph driver tests (Python and bash), using a fake agent process so they run offline."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from governor import ExitCode, Limits
from oracle import PytestOracle
from ralph import main, plan_items, run_ralph
from toy_task import make_workspace

HERE = Path(__file__).parent
FAKE = f"{sys.executable} {HERE / 'examples' / 'toy_task' / 'fake_ralph_agent.py'}"
ORACLE = PytestOracle(["spec_tokenbucket.py"])
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def ws_git(tmp_path):
    ws = make_workspace(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    return ws


def limits(n=10, patience=3):
    return Limits(max_iterations=n, max_cost_usd=None, max_input_tokens=None, max_output_tokens=None,
                  stall_patience=patience)


@pytest.fixture
def mode(monkeypatch):
    return lambda m: monkeypatch.setenv("FAKE_AGENT_MODE", m)


def test_plan_items(tmp_path):
    assert plan_items(make_workspace(tmp_path)) == (["FP-1", "FP-2"], [])


@needs_git
def test_one_item_per_iteration_until_green(tmp_path, mode):
    mode("fix")
    ws = ws_git(tmp_path)
    res = run_ralph(ws, FAKE, ORACLE, limits())
    assert res.exit_code is ExitCode.SUCCESS and res.iterations == 2
    assert [e["open"] for e in res.log] == [1, 0] and [e["failed"] for e in res.log] == [1, 0]
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True).stdout
    assert log.count("ralph: iter") == 2  # commit on every kept iteration
    assert len((ws / ".ralph" / "log.jsonl").read_text().splitlines()) == 2


@needs_git
def test_regression_is_reverted(tmp_path, mode):
    mode("regress")
    ws = ws_git(tmp_path)
    before = (ws / "tokenbucket.py").read_text()
    res = run_ralph(ws, FAKE, ORACLE, limits(patience=2))
    assert res.exit_code is ExitCode.STALLED
    assert all(e["decision"] == "reverted" for e in res.log)
    assert (ws / "tokenbucket.py").read_text() == before


def test_noop_agent_stalls(tmp_path, mode):
    mode("noop")
    res = run_ralph(make_workspace(tmp_path), FAKE, ORACLE, limits(n=50, patience=3))
    assert res.exit_code is ExitCode.STALLED and res.iterations == 3


def test_lying_agent_is_flagged_premature_and_never_succeeds(tmp_path, mode):
    mode("lie")
    res = run_ralph(make_workspace(tmp_path), FAKE, ORACLE, limits(n=50, patience=3))
    assert res.exit_code is ExitCode.STALLED
    assert all(e.get("premature_claim") for e in res.log)


def test_crashing_agent_trips_error_breaker(tmp_path, mode):
    mode("crash")
    res = run_ralph(make_workspace(tmp_path), FAKE, ORACLE, limits(n=50, patience=None))
    assert res.exit_code is ExitCode.STALLED and "consecutive errors" in res.reason


def test_blocked_agent_exits_blocked(tmp_path, mode):
    mode("blocked")
    res = run_ralph(make_workspace(tmp_path), FAKE, ORACLE, limits())
    assert res.exit_code is ExitCode.BLOCKED and "contradicts" in res.reason


def test_stop_file_and_broken_oracle(tmp_path, mode):
    mode("fix")
    ws = make_workspace(tmp_path)
    (ws / ".ralph").mkdir()
    (ws / ".ralph" / "STOP").write_text("")
    assert run_ralph(ws, FAKE, ORACLE, limits()).exit_code is ExitCode.STOPPED
    assert run_ralph(ws, FAKE, PytestOracle(["spec_missing.py"]), limits()).exit_code is ExitCode.BROKEN


def test_python_callable_agent(tmp_path):
    from toy_task import apply_fix

    def agent(prompt: str, cwd: Path) -> int:
        assert "Study fix_plan.md" in prompt  # same prompt every iteration
        text = (cwd / "fix_plan.md").read_text()
        item = "FP-1" if "- [ ] FP-1" in text else "FP-2"
        apply_fix(cwd, item)
        (cwd / "fix_plan.md").write_text(text.replace(f"- [ ] {item}", f"- [x] {item}"))
        return 0

    assert run_ralph(make_workspace(tmp_path), agent, ORACLE, limits()).exit_code is ExitCode.SUCCESS


def test_cli_returns_typed_exit_code(tmp_path, mode, capsys):
    mode("fix")
    ws = make_workspace(tmp_path)
    rc = main(["--workspace", str(ws), "--agent-cmd", FAKE, "--oracle-cmd", "python -m pytest -q spec_tokenbucket.py"])
    assert rc == 0 and "exit=SUCCESS" in capsys.readouterr().out


# ---- ralph.sh ------------------------------------------------------------------------
def run_sh(ws, agent_mode, **env):
    e = {**os.environ, "AGENT_CMD": FAKE, "FAKE_AGENT_MODE": agent_mode,
         "ORACLE_CMD": f"{sys.executable} -m pytest -q -p no:cacheprovider spec_tokenbucket.py", **env}
    return subprocess.run(["bash", str(HERE / "ralph.sh")], cwd=ws, env=e, capture_output=True, text=True, timeout=120)


@needs_git
def test_ralph_sh_succeeds_and_commits(tmp_path):
    ws = ws_git(tmp_path)
    p = run_sh(ws, "fix")
    assert p.returncode == 0, p.stdout + p.stderr
    rows = [json.loads(l) for l in (ws / ".ralph" / "log.jsonl").read_text().splitlines()]
    assert [r["open"] for r in rows] == [1, 0]


def test_ralph_sh_stalls_on_noop(tmp_path):
    p = run_sh(make_workspace(tmp_path), "noop", STALL_LIMIT="2")
    assert p.returncode == 5 and "stalled" in p.stdout


def test_ralph_sh_stop_file(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / ".ralph").mkdir()
    (ws / ".ralph" / "STOP").write_text("")
    assert run_sh(ws, "fix").returncode == 6
