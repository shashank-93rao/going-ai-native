import pytest

from selfmeasure import run
from selfmeasure_log import LogError


def test_cli_end_to_end(tmp_path, monkeypatch):
    log = str(tmp_path / "log.jsonl")
    monkeypatch.setenv("SELFMEASURE_SEED", "cli-seed")
    for i, size in enumerate(["M", "M", "S", "S"]):
        run(["--log", log, "register", f"PAY-{i}", "--size", size, "--est", "60", "--title", f"t{i}"])
    out = run(["--log", log, "assign"])
    assert out.count(": ai") == 2 and out.count(": no_ai") == 2
    run(["--log", log, "start", "PAY-0", "--ts", "2026-09-01T09:00:00Z"])
    run(["--log", log, "merge", "PAY-0", "--ts", "2026-09-01T11:00:00Z", "--pr", "#1", "--active", "90"])
    run(["--log", log, "perceive", "PAY-0", "--other", "120"])
    run(["--log", log, "rework", "PAY-0", "--kind", "fix", "--minutes", "15", "--ts", "2026-09-02T09:00:00Z"])
    run(["--log", log, "abandon", "PAY-1", "--reason", "blocked on vendor"])
    status = run(["--log", log, "status"])
    assert "merged" in status and "abandoned" in status
    assert "WARNING" in run(["--log", log, "summary"])


def test_assign_requires_seed(tmp_path, monkeypatch):
    monkeypatch.delenv("SELFMEASURE_SEED", raising=False)
    log = str(tmp_path / "log.jsonl")
    run(["--log", log, "register", "X", "--size", "S", "--est", "30"])
    with pytest.raises(LogError, match="SELFMEASURE_SEED"):
        run(["--log", log, "assign"])
