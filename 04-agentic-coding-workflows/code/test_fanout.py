"""Tests for the fan-out driver. The "agent" is always a fake shell command."""

from __future__ import annotations

import json
import shlex
import sys
import time
from pathlib import Path

import pytest

from fanout import Fanout, FanoutConfig, load_ok_targets, main, parse_agent_output, render, summarize

HERE = Path(__file__).resolve().parent
PY = shlex.quote(sys.executable)
FAKE = f"{PY} {shlex.quote(str(HERE / 'fake_agent.py'))} {{target}} --feedback {{feedback}}"
CHECK = f"{PY} {shlex.quote(str(HERE / 'check_callsite.py'))} {{target}}"
LEGACY = 'TOPIC = "t"\n\ndef f(order):\n    emit_event(TOPIC, order)\n'


def make_files(tmp_path: Path, markers: list[str]) -> list[str]:
    out = []
    for i, m in enumerate(markers):
        p = tmp_path / f"svc_{i}.py"
        p.write_text((f"# FAKE: {m}\n" if m else "") + LEGACY)
        out.append(str(p))
    return out


def run(targets, **kw):
    cfg = FanoutConfig(**{"agent_cmd": FAKE, "verify_cmd": CHECK, "agent_timeout": 20,
                          "verify_timeout": 20, **kw})
    return {Path(r.target).name: r for r in Fanout(cfg).run(targets)}


def test_render_quotes_placeholders():
    cmd = render("echo {target} {stem} {name}", "dir with space/$HOME's.py")
    assert cmd == "echo 'dir with space/$HOME'\"'\"'s.py' '$HOME'\"'\"'s' '$HOME'\"'\"'s.py'"


def test_happy_path_migrates_and_verifies(tmp_path):
    targets = make_files(tmp_path, ["", "", ""])
    res = run(targets, concurrency=3)
    assert {r.status for r in res.values()} == {"ok"}
    assert 'publisher.publish(TOPIC, order, key=order["id"])' in Path(targets[0]).read_text()
    assert all(r.attempts == 1 and r.agent_claimed_ok for r in res.values())


def test_agent_failure_skips_verify(tmp_path):
    res = run(make_files(tmp_path, ["fail"]))
    r = res["svc_0.py"]
    assert r.status == "agent_failed" and r.verify_exit is None and r.agent_claimed_ok is False


def test_verify_catches_broken_code_after_retries(tmp_path):
    r = run(make_files(tmp_path, ["break"]), retries=2)["svc_0.py"]
    assert r.status == "verify_failed"
    assert r.attempts == 3
    assert "syntax error" in r.verify_tail


def test_verify_catches_agent_that_lies(tmp_path):
    results = list(run(make_files(tmp_path, ["lie"])).values())
    assert results[0].status == "verify_failed"
    assert results[0].agent_claimed_ok is True
    assert summarize(results)["claimed_ok_but_not_ok"] == 1


def test_retry_feeds_verifier_output_back(tmp_path):
    results = list(run(make_files(tmp_path, ["flaky"]), retries=1).values())
    assert results[0].status == "ok" and results[0].attempts == 2
    assert summarize(results)["needed_retry"] == 1


def test_no_retry_means_single_attempt(tmp_path):
    r = run(make_files(tmp_path, ["flaky"]), retries=0)["svc_0.py"]
    assert r.status == "verify_failed" and r.attempts == 1


def test_timeout_kills_process_group(tmp_path):
    targets = make_files(tmp_path, ["sleep=30"])
    start = time.monotonic()
    r = run(targets, agent_timeout=0.5)["svc_0.py"]
    assert r.status == "timeout"
    assert time.monotonic() - start < 10


def test_concurrency_limit_is_respected(tmp_path):
    slots = tmp_path / "slots"
    slots.mkdir()
    log = tmp_path / "log.txt"
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import os, sys, time, pathlib\n"
        f"slots = pathlib.Path({str(slots)!r})\n"
        "me = slots / pathlib.Path(sys.argv[1]).name\n"
        "me.touch()\n"
        f"open({str(log)!r}, 'a').write(str(len(list(slots.iterdir()))) + '\\n')\n"
        "time.sleep(0.3)\n"
        "me.unlink()\n"
    )
    targets = [str(tmp_path / f"t{i}") for i in range(9)]
    cfg = FanoutConfig(agent_cmd=f"{PY} {shlex.quote(str(probe))} {{target}}", concurrency=3)
    results = Fanout(cfg).run(targets)
    assert all(r.status == "ok" for r in results)
    seen = [int(x) for x in log.read_text().split()]
    assert max(seen) <= 3
    assert max(seen) >= 2  # it really ran in parallel


def test_circuit_breaker_cancels_remaining(tmp_path):
    targets = make_files(tmp_path, ["fail"] * 6)
    res = run(targets, concurrency=1, max_failures=2)
    statuses = [res[f"svc_{i}.py"].status for i in range(6)]
    assert statuses[:2] == ["agent_failed", "agent_failed"]
    assert set(statuses[2:]) == {"cancelled"}


def test_failed_canary_aborts_the_batch(tmp_path):
    targets = make_files(tmp_path, ["fail", "", "", ""])
    res = run(targets, canary=2, concurrency=4)
    assert res["svc_0.py"].status == "agent_failed"
    assert res["svc_1.py"].status == "ok"  # canary peers still finish
    assert {res["svc_2.py"].status, res["svc_3.py"].status} == {"cancelled"}


def test_passing_canary_continues(tmp_path):
    res = run(make_files(tmp_path, ["", "", "", ""]), canary=2)
    assert {r.status for r in res.values()} == {"ok"}


def test_json_output_cost_and_is_error():
    data, claim = parse_agent_output('{"result": "done. OK", "total_cost_usd": 0.12, "is_error": false}')
    assert data["total_cost_usd"] == 0.12 and claim is True
    _, claim = parse_agent_output("progress...\nMigration FAIL")
    assert claim is False
    _, claim = parse_agent_output("I looked at the BOOK")
    assert claim is None


def test_is_error_with_exit_zero_counts_as_agent_failure(tmp_path):
    cfg = FanoutConfig(agent_cmd="""echo '{"result": "rate limited", "is_error": true}'""",
                       verify_cmd="true")
    r = Fanout(cfg).run(["a.py"])[0]
    assert r.status == "agent_failed"


def test_cost_is_summed_across_attempts(tmp_path):
    results = list(run(make_files(tmp_path, ["flaky", ""]), retries=1).values())
    assert summarize(results)["cost_usd"] == pytest.approx(0.03)  # 2 attempts + 1 attempt


def test_on_success_runs_serialized(tmp_path):
    lock = tmp_path / "lock"
    ledger = tmp_path / "ledger.txt"
    # Fails loudly if two on_success commands ever overlap (mkdir is atomic).
    on_success = (f"mkdir {shlex.quote(str(lock))} || exit 9; echo {{name}} >> {shlex.quote(str(ledger))}; "
                  f"sleep 0.05; rmdir {shlex.quote(str(lock))}")
    targets = [str(tmp_path / f"t{i}.py") for i in range(8)]
    cfg = FanoutConfig(agent_cmd="true", verify_cmd="true", on_success_cmd=on_success, concurrency=8)
    results = Fanout(cfg).run(targets)
    assert all(r.status == "ok" for r in results)
    assert sorted(ledger.read_text().split()) == sorted(Path(t).name for t in targets)


def test_results_file_and_resume(tmp_path):
    targets = make_files(tmp_path, ["", "fail"])
    out = tmp_path / "results.jsonl"
    Fanout(FanoutConfig(agent_cmd=FAKE, verify_cmd=CHECK), out).run(targets)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert {r["status"] for r in rows} == {"ok", "agent_failed"}
    ok = load_ok_targets(out)
    assert ok == {targets[0]}
    calls = tmp_path / "calls.txt"
    cfg = FanoutConfig(agent_cmd=f"echo {{target}} >> {shlex.quote(str(calls))}")
    second = Fanout(cfg).run(targets, skip=ok)
    assert [r.status for r in second] == ["skipped", "ok"]
    assert calls.read_text().split() == [targets[1]]


def test_cli_end_to_end(tmp_path, capsys):
    targets = make_files(tmp_path, ["", "lie"])
    tfile = tmp_path / "targets.txt"
    tfile.write_text("# comment line\n" + "\n".join(targets) + "\n")
    code = main(["--targets", str(tfile), "--agent", FAKE, "--verify", CHECK,
                 "--concurrency", "2", "--results", str(tmp_path / "r.jsonl")])
    out = capsys.readouterr().out
    assert code == 1
    assert '"claimed_ok_but_not_ok": 1' in out


def test_cli_dry_run_runs_nothing(tmp_path, capsys):
    tfile = tmp_path / "targets.txt"
    tfile.write_text("a.py\n")
    assert main(["--targets", str(tfile), "--agent", "claude -p 'migrate {target}'", "--dry-run"]) == 0
    assert "claude -p 'migrate a.py'" in capsys.readouterr().out


def test_render_leaves_json_braces_alone():
    cmd = render("""claude -p "fix {name}" --json-schema '{"type":"object"}'""", "src/a.py")
    assert cmd == """claude -p "fix a.py" --json-schema '{"type":"object"}'"""


def test_env_vars_expose_target_inside_double_quotes(tmp_path):
    out = tmp_path / "prompt.txt"
    cfg = FanoutConfig(agent_cmd=f'echo "Migrate $FANOUT_TARGET (attempt $FANOUT_ATTEMPT)" > {shlex.quote(str(out))}')
    Fanout(cfg).run(["dir with space/x.py"])
    assert out.read_text().strip() == "Migrate dir with space/x.py (attempt 1)"
