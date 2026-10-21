import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from stop_gate import GateConfig, OracleResult, compact_output, evaluate

HOOK = Path(__file__).parent / "hooks" / "stop_gate.py"
DATA = Path(__file__).parent / "data"
EVENT = {"session_id": "s1", "hook_event_name": "Stop", "stop_hook_active": False}
PASS = OracleResult(True, 0, "5 passed in 0.1s")
FAIL = OracleResult(False, 1, "noise\nFAILED tests/test_idem.py::test_retry - assert 2 == 1\n1 failed, 4 passed")


def run(state=None, oracle=PASS, diff="", cfg=None, event=EVENT):
    return evaluate(event, cfg or GateConfig(), state or {}, lambda: oracle, lambda: diff)


def test_green_and_clean_allows_stop_and_resets_state():
    assert run(state={"blocks": 3}) == (None, {})


def test_red_oracle_blocks_with_compact_failure():
    out, st = run(oracle=FAIL)
    assert out["decision"] == "block"
    assert "assert 2 == 1" in out["reason"] and "noise" not in out["reason"]
    assert st["blocks"] == 1


def test_tampering_blocks_even_when_oracle_is_green():
    out, _ = run(diff=(DATA / "weakened_assertion.diff").read_text())
    assert out["decision"] == "block"
    assert "Test tampering detected" in out["reason"] and "assertion_weakened" in out["reason"]


def test_same_failure_twice_adds_change_approach_note():
    out1, st = run(oracle=FAIL)
    out2, st2 = run(state=st, oracle=FAIL)
    assert "same failure" not in out1["reason"]
    assert "same failure as your previous attempt" in out2["reason"] and st2["blocks"] == 2


def test_budget_exhausted_halts_and_tells_human():
    out, st = run(state={"blocks": 5}, oracle=FAIL, cfg=GateConfig(max_blocks=5))
    assert out["continue"] is False and "NOT done" in out["stopReason"] and st == {}


def test_broken_oracle_halts_instead_of_looping():
    out, _ = run(oracle=OracleResult(False, 127, "sh: pytestt: command not found", broken=True))
    assert out["continue"] is False and "NOT verified" in out["stopReason"]


def test_one_shot_mode_respects_stop_hook_active():
    ev = dict(EVENT, stop_hook_active=True)
    assert run(oracle=FAIL, event=ev, cfg=GateConfig(one_shot=True)) == (None, {})
    assert run(oracle=FAIL, event=ev)[0]["decision"] == "block"  # default: our own budget governs


def test_compact_output_caps_size():
    out = compact_output("\n".join(f"E   line {i}" for i in range(1000)))
    assert out.count("\n") < 30 and len(out) <= 2500


# --- End to end: a real git repo, a real pytest oracle, the hook as a subprocess ---

CODE_BUGGY = "def charge_count(retries):\n    return 1 + retries  # bug: every retry charges again\n"
CODE_FIXED = "def charge_count(retries):\n    return 1\n"
TEST_ORIG = "from svc import charge_count\n\n\ndef test_retry_charges_once():\n    assert charge_count(retries=2) == 1\n"
TEST_WEAK = "from svc import charge_count\n\n\ndef test_retry_charges_once():\n    assert charge_count(retries=2) >= 1\n"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "svc.py").write_text(CODE_BUGGY)
    (tmp_path / "test_svc.py").write_text(TEST_ORIG)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")
    return tmp_path


def _hook(repo, session="e2e"):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo), STOP_GATE_CMD=f"{sys.executable} -m pytest -q -p no:cacheprovider")
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(dict(EVENT, session_id=session, cwd=str(repo))),
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def test_e2e_bug_blocks(repo):
    out = _hook(repo)
    assert out["decision"] == "block" and "Oracle" in out["reason"]
    state = json.loads((repo / ".claude/state/stop_gate/e2e.json").read_text())
    assert state["blocks"] == 1


def test_e2e_weakened_test_passes_oracle_but_still_blocks(repo):
    (repo / "test_svc.py").write_text(TEST_WEAK)
    out = _hook(repo)
    assert out["decision"] == "block"
    assert "Test tampering detected" in out["reason"] and "Oracle" not in out["reason"]


def test_e2e_real_fix_allows_stop(repo):
    (repo / "svc.py").write_text(CODE_FIXED)
    assert _hook(repo) is None


def test_e2e_same_size_edit_is_not_served_stale_bytecode(repo):
    # "==" -> ">=" keeps the file size; within one mtime second a cached .pyc would be reused.
    assert "Oracle" in _hook(repo)["reason"]
    (repo / "test_svc.py").write_text(TEST_WEAK)
    out = _hook(repo)
    assert "Oracle" not in out["reason"], "oracle ran stale bytecode"
