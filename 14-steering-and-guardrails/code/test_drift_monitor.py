import json
from pathlib import Path

from drift_monitor import Plan, analyze, check_events, hook_main, load_plan

DATA = Path(__file__).parent / "data"


def _d(path, n_added, status=""):
    hdr = {"added": "new file mode 100644\n", "deleted": "deleted file mode 100644\n"}.get(status, "")
    body = "".join(f"+line {i}\n" for i in range(n_added))
    return f"diff --git a/{path} b/{path}\n{hdr}--- a/{path}\n+++ b/{path}\n@@ -1,0 +1,{n_added} @@\n{body}"


def test_drift_example_stops():
    plan = load_plan(DATA / "plan.json")
    events = [json.loads(x) for x in (DATA / "run_events.jsonl").read_text().splitlines()]
    rep = analyze(plan, (DATA / "drift_run.diff").read_text(), events)
    checks = {f.check for f in rep.flags}
    assert rep.verdict == "stop"
    assert {"out_of_plan_file", "dependency_change", "scope_creep", "repeated_failure"} <= checks


def test_planned_change_is_ok():
    rep = analyze(load_plan(DATA / "plan.json"), (DATA / "clean_fix.diff").read_text())
    assert rep.verdict == "ok" and rep.flags == []


def test_may_create_only_applies_to_new_files():
    plan = Plan(files=["a.py"], may_create=["tests/test_*.py"])
    assert analyze(plan, _d("tests/test_new.py", 3, "added")).verdict == "ok"
    assert analyze(plan, _d("tests/test_old.py", 3)).verdict == "warn"


def test_diff_size_alarm_levels():
    plan = Plan(files=["a.py"], max_changed_lines=10)
    assert analyze(plan, _d("a.py", 8)).verdict == "ok"
    assert analyze(plan, _d("a.py", 15)).verdict == "warn"
    assert analyze(plan, _d("a.py", 25)).verdict == "stop"


def test_ci_and_test_deletion_are_stops():
    plan = Plan(files=["a.py"])
    assert analyze(plan, _d(".github/workflows/ci.yml", 2)).flags[0].check == "ci_config_changed"
    deleted = "diff --git a/tests/test_a.py b/tests/test_a.py\ndeleted file mode 100644\n@@ -1,1 +0,0 @@\n-x\n"
    assert analyze(Plan(files=["tests/test_a.py"]), deleted).verdict == "stop"


def test_edit_loop_detection():
    events = [{"tool": "Edit", "file": "limiter.go"}] * 7
    flags = check_events(Plan(files=[], edit_limit_per_file=6), events)
    assert flags and flags[0].check == "edit_loop"


def test_success_resets_failure_streak():
    ev = [{"tool": "Bash", "command": "make test", "exit_code": c} for c in (1, 1, 0, 1, 1)]
    assert check_events(Plan(files=[]), ev) == []


def test_plan_md_files_section(tmp_path):
    p = tmp_path / "PLAN.md"
    p.write_text("# Plan\nFix it.\n\n## Files\n- `svc/idempotency.py`\n- svc/tests/test_idempotency.py\n\n## Steps\n- `not/a/file.py`\n")
    assert load_plan(p).files == ["svc/idempotency.py", "svc/tests/test_idempotency.py"]


def test_hook_mode_without_plan_is_silent(tmp_path):
    assert hook_main("{}", tmp_path) is None


def test_hook_mode_blocks_on_stop_and_informs_on_warn(tmp_path, monkeypatch):
    import drift_monitor

    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "plan.json").write_text(json.dumps({"files": ["a.py"], "max_changed_lines": 10}))
    monkeypatch.setattr(drift_monitor, "_git_diff", lambda root: _d("a.py", 30))
    assert hook_main("{}", tmp_path)["decision"] == "block"
    assert "systemMessage" in hook_main('{"stop_hook_active": true}', tmp_path)
    monkeypatch.setattr(drift_monitor, "_git_diff", lambda root: _d("b.py", 2))
    assert "systemMessage" in hook_main("{}", tmp_path)
