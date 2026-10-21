import json
import re
from pathlib import Path

HERE = Path(__file__).parent
SETTINGS = json.loads((HERE / "settings.example.json").read_text())
KNOWN_EVENTS = {"PreToolUse", "PostToolUse", "Stop", "SubagentStop", "UserPromptSubmit", "SessionStart", "Notification", "PreCompact"}


def test_events_are_known_and_hooks_are_commands():
    for event, groups in SETTINGS["hooks"].items():
        assert event in KNOWN_EVENTS
        for g in groups:
            for h in g["hooks"]:
                assert h["type"] == "command" and h["timeout"] > 0


def test_every_hook_script_exists_in_this_module():
    for groups in SETTINGS["hooks"].values():
        for g in groups:
            for h in g["hooks"]:
                name = re.search(r"/\.claude/hooks/(\w+\.py)", h["command"]).group(1)
                assert (HERE / "hooks" / name).exists() or (HERE / name).exists(), name


def test_stop_hook_timeout_exceeds_oracle_timeout():
    from stop_gate import GateConfig

    stop = SETTINGS["hooks"]["Stop"][0]["hooks"][0]
    assert "stop_gate.py" in stop["command"] and stop["timeout"] > GateConfig().timeout


def test_guardrails_protect_themselves_and_secrets():
    deny = SETTINGS["permissions"]["deny"]
    assert "Read(./.env)" in deny
    assert any(".claude/hooks" in r for r in deny) and any("approved-test-changes" in r for r in deny)


def test_pre_tool_matcher_covers_file_and_shell_tools():
    matcher = SETTINGS["hooks"]["PreToolUse"][0]["matcher"]
    for tool in ("Bash", "Edit", "Write"):
        assert re.fullmatch(f"(?:{matcher})", tool)
