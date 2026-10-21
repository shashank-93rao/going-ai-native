"""Tests for the task suite and the autonomy-rate eval, using the deterministic fake agent."""

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import autonomy_eval as ev
from task_suite import ABLATIONS, EditError, apply_edits, build_workspace, invert, load_tasks

AGENT = "{python} {here}/fake_agent.py --policy %s {workdir} {prompt}"


def test_suite_shape():
    tasks = load_tasks()
    kinds = [t.kind for t in tasks]
    assert 6 <= len(tasks) <= 9
    assert {"feature", "bug", "incident"} == set(kinds)
    assert all(t.hidden_test.exists() for t in tasks)
    assert all(t.incident_log for t in tasks if t.kind == "incident")


def _grade_state(task, fixed: bool):
    with tempfile.TemporaryDirectory() as tmp:
        repo = build_workspace(task, Path(tmp))
        if fixed:
            apply_edits(repo, task.reference_fix())
        return ev.grade(task, repo)


def test_every_task_oracle_can_fail_and_can_pass():
    """'Prove the oracle can fail': hidden tests fail before the fix and pass after it."""
    tasks = load_tasks()
    with ThreadPoolExecutor(8) as pool:
        before = list(pool.map(lambda t: _grade_state(t, False), tasks))
        after = list(pool.map(lambda t: _grade_state(t, True), tasks))
    for t, b, a in zip(tasks, before, after):
        assert b[0] is False, f"{t.id}: hidden tests pass without a fix (task is broken)"
        assert a[:3] == (True, True, True), f"{t.id}: reference fix does not pass: {a[4]}"


def test_edits_fail_loudly_and_invert(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\nx = 1\n")
    with pytest.raises(EditError):
        apply_edits(tmp_path, [{"file": "a.py", "find": "x = 1", "replace": "x = 2"}])
    edit = [{"file": "a.py", "find": "x = 1\nx = 1", "replace": "y = 0"}]
    apply_edits(tmp_path, edit)
    apply_edits(tmp_path, invert(edit))
    assert f.read_text() == "x = 1\nx = 1\n"


def test_workspace_hides_graders_and_applies_ablation(tmp_path):
    [task] = load_tasks(only=["inc-stats-drift"])
    repo = build_workspace(task, tmp_path, ablate=["diagnose", "invariants"])
    assert (repo / "var/log/orders.jsonl").exists()
    assert not (repo / "tools/diagnose.py").exists() and not (repo / "INVARIANTS.md").exists()
    assert not list(repo.rglob("hidden_checks.py")) and not list(repo.rglob("task.toml"))
    assert (tmp_path / "PROMPT.md").read_text().startswith("ALERT")


def test_wilson_interval():
    assert ev.wilson(0, 0) == (0.0, 1.0)
    lo, hi = ev.wilson(7, 8)
    assert round(lo, 2) == 0.53 and round(hi, 2) == 0.98
    lo, hi = ev.wilson(70, 80)
    assert hi - lo < 0.16  # more tasks, tighter interval


def test_fake_agent_known_fixes_and_failures(tmp_path):
    fail = "feat-currency,inc-stats-drift,bug-double-cancel"
    results, summary = ev.evaluate((AGENT % "oracle") + f" --fail {fail}", jobs=8)
    by_id = {r.task_id: r for r in results}
    assert {k for k, r in by_id.items() if not r.success} == set(fail.split(","))
    assert summary["overall"]["successes"] == 5 and summary["overall"]["trials"] == 8
    # bug-double-cancel's naive fix deletes the failing test: caught as tampering, and still graded FAIL
    assert by_id["bug-double-cancel"].tampered == ["tests/test_orders_api.py"]
    assert by_id["bug-double-cancel"].visible_ok is False
    # feat-currency's naive fix forgets the hash: visible tests and lint pass, only the hidden test catches it
    c = by_id["feat-currency"]
    assert (c.hidden_ok, c.visible_ok, c.lint_ok) == (False, True, True)


def test_naive_symptom_fix_for_409_is_caught():
    results, _ = ev.evaluate(AGENT % "naive", task_ids=["inc-409-spike"], jobs=1)
    r = results[0]
    assert not r.success and not r.hidden_ok and not r.visible_ok


def test_ablation_lowers_autonomy_rate_and_trials_aggregate(tmp_path):
    ids = ["feat-list-orders", "inc-409-spike", "inc-lost-cancellations"]
    full, s_full = ev.evaluate(AGENT % "harness-aware", task_ids=ids, trials=2, jobs=8)
    ablated, s_abl = ev.evaluate(AGENT % "harness-aware", task_ids=ids, ablate=["diagnose"], jobs=8)
    assert s_full["overall"] == {"successes": 6, "trials": 6, "rate": 1.0, "ci95": [0.61, 1.0]}
    assert s_full["pass_all_trials"] == 3
    assert {r.task_id for r in ablated if not r.success} == {"inc-409-spike", "inc-lost-cancellations"}
    text = ev.render(ablated, s_abl, ["diagnose"])
    assert "harness ablated: diagnose" in text and "autonomy rate: 1/3" in text


def test_cli_writes_json(tmp_path, capsys):
    out = tmp_path / "r.json"
    ev.main(["--agent", AGENT % "noop", "--tasks", "feat-list-orders", "--json", str(out)])
    data = json.loads(out.read_text())
    assert data["summary"]["overall"]["successes"] == 0
    assert "autonomy rate: 0/1" in capsys.readouterr().out


def test_unknown_ablation_rejected(tmp_path):
    [task] = load_tasks(only=["feat-list-orders"])
    with pytest.raises(ValueError):
        build_workspace(task, tmp_path, ablate=["vibes"])
    assert "lint" in ABLATIONS
