"""Tests for the minimal agent loop, offline with FakeClient."""

from ainative_kit import FakeClient, Tracer, text, tool

import autonomy_eval as ev
import mini_agent
from task_suite import build_workspace, load_tasks


def test_scripted_agent_fixes_409_incident(tmp_path):
    [task] = load_tasks(only=["inc-409-spike"])
    repo = build_workspace(task, tmp_path)
    client, tracer = FakeClient(mini_agent.demo_script()), Tracer()
    final = mini_agent.run_agent(client, repo, task.prompt, tracer)
    assert "IdempotencyConflict" in final
    hidden_ok, visible_ok, lint_ok, tampered, _ = ev.grade(task, repo)
    assert (hidden_ok, visible_ok, lint_ok, tampered) == (True, True, True, [])
    names = [s.name for s in tracer.spans]
    assert names.count("llm_call") == 6 and "tool:replace_in_file" in names
    # the diagnose output reached the model as a tool result
    diag = client.calls[2]["messages"][-1]["content"][0]["content"]
    assert "distinct_request_hashes=3" in diag


def test_tools_enforce_allowlist_and_repo_boundary(tmp_path):
    out, err = mini_agent.execute(tmp_path, "run", {"command": "rm -rf /"})
    assert err and "not allowed" in out
    out, err = mini_agent.execute(tmp_path, "read_file", {"path": "../../etc/passwd"})
    assert err and "escapes" in out


def test_ambiguous_edit_is_reported_to_the_model(tmp_path):
    (tmp_path / "a.py").write_text("x\nx\n")
    out, err = mini_agent.execute(tmp_path, "replace_in_file", {"path": "a.py", "old": "x", "new": "y"})
    assert err and "found 2" in out


def test_turn_budget_stops_a_looping_agent(tmp_path):
    client = FakeClient(lambda m, kw: tool("list_files", {"path": "."}))
    tracer = Tracer()
    assert mini_agent.run_agent(client, tmp_path, "loop", tracer, max_turns=3).startswith("stopped")
    assert tracer.spans[-1].attrs["outcome"] == "max_turns"


def test_tool_errors_are_returned_not_raised(tmp_path):
    client = FakeClient([tool("read_file", {"path": "missing.py"}), text("done")])
    assert mini_agent.run_agent(client, tmp_path, "read it", Tracer()) == "done"
    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "FileNotFoundError" in result["content"]
