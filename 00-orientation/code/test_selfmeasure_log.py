import json

import pytest

from selfmeasure_log import LogError, append_event, assign_arm, assign_pending, choose_arm, fold, read_events

SEED = "test-seed"


def reg(path, tid, size="M", est=60, ts="2026-09-01T09:00:00+00:00"):
    return append_event(path, {"event": "register", "task_id": tid, "ts": ts, "title": tid, "kind": "bugfix",
                               "size": size, "est_minutes": est})


def test_full_lifecycle_folds_to_state(tmp_path):
    log = tmp_path / "log.jsonl"
    reg(log, "T1")
    arm = assign_arm(log, "T1", SEED)
    append_event(log, {"event": "start", "task_id": "T1", "ts": "2026-09-01T10:00:00+00:00"})
    append_event(log, {"event": "merge", "task_id": "T1", "ts": "2026-09-01T13:30:00+00:00", "active_minutes": 120})
    append_event(log, {"event": "rework", "task_id": "T1", "ts": "2026-09-03T10:00:00+00:00", "rework_kind": "fix", "minutes": 30})
    t = fold(read_events(log))["T1"]
    assert t.arm == arm and t.hours_to_merge == pytest.approx(3.5)
    assert t.active_minutes == 120 and len(t.rework) == 1


def test_every_line_is_json(tmp_path):
    log = tmp_path / "log.jsonl"
    reg(log, "T1")
    assign_arm(log, "T1", SEED)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["event"] for r in rows] == ["register", "assign"]
    assert SEED not in log.read_text()  # only the fingerprint is stored


def test_cannot_reassign(tmp_path):
    log = tmp_path / "log.jsonl"
    reg(log, "T1")
    assign_arm(log, "T1", SEED)
    with pytest.raises(LogError, match="assigned twice"):
        assign_arm(log, "T1", SEED)


def test_cannot_assign_unregistered_or_work_before_assign(tmp_path):
    log = tmp_path / "log.jsonl"
    with pytest.raises(LogError):
        assign_arm(log, "nope", SEED)
    reg(log, "T1")
    with pytest.raises(LogError, match="before 'assign'"):
        append_event(log, {"event": "start", "task_id": "T1"})


def test_merge_before_start_rejected_and_log_untouched(tmp_path):
    log = tmp_path / "log.jsonl"
    reg(log, "T1")
    assign_arm(log, "T1", SEED)
    before = log.read_text()
    with pytest.raises(LogError, match="merge before start"):
        append_event(log, {"event": "merge", "task_id": "T1"})
    assert log.read_text() == before


def test_schema_validation(tmp_path):
    log = tmp_path / "log.jsonl"
    with pytest.raises(LogError, match="size"):
        reg(log, "T1", size="XL")
    with pytest.raises(LogError, match="missing"):
        append_event(log, {"event": "register", "task_id": "T2"})
    with pytest.raises(LogError, match="unknown event"):
        append_event(log, {"event": "vibes", "task_id": "T2"})


def test_malformed_line_reports_line_number(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text('{"event": "register"}\n{oops\n')
    with pytest.raises(LogError, match=":2:"):
        read_events(log)


def test_assignment_is_deterministic_given_seed(tmp_path):
    arms = []
    for d in ("a", "b"):
        log = tmp_path / f"{d}.jsonl"
        for i in range(6):
            reg(log, f"T{i}")
        arms.append(assign_pending(log, SEED))
    assert arms[0] == arms[1]


def test_blocks_are_balanced_within_each_size(tmp_path):
    log = tmp_path / "log.jsonl"
    sizes = ["S", "M", "L"] * 8
    for i, s in enumerate(sizes):
        reg(log, f"T{i}", size=s)
    assign_pending(log, SEED)
    tasks = fold(read_events(log)).values()
    for s in "SML":
        arms = [t.arm for t in tasks if t.size == s]
        assert arms.count("ai") == arms.count("no_ai") == 4


def test_choose_arm_pairs_are_complementary():
    first = choose_arm("x", "M", [])
    assert choose_arm("x", "M", [first]) != first


def test_seed_actually_randomizes():
    # Over many pairs, both arms should come first sometimes.
    firsts = {choose_arm(f"seed-{i}", "M", []) for i in range(40)}
    assert firsts == {"ai", "no_ai"}
