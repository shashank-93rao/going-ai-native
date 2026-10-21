"""Skill-eval style scripted checks on codex exec --json traces (hand-written samples)."""

from codex_trace import DATA, check_trace, commands, final_message, load_events, run_suite, tokens


def test_parse_events():
    ev = load_events(DATA / "codex_trace_good.jsonl")
    assert len(commands(ev)) == 4  # item.started duplicates dropped
    assert "promoted to prod" in final_message(ev)
    assert tokens(ev) == 18210 + 412


def test_suite_verdicts():
    res = run_suite()
    fails = {case: [c.id for c in checks if not c.passed] for case, checks in res.items()}
    assert fails["deploy-01"] == []
    assert set(fails["deploy-02"]) == {"no_forbidden_commands", "process:staging_verified_before_prod",
                                       "process:prod_rollout_verified"}
    assert fails["deploy-03"] == ["negative_control:no_mutation"]


def test_negative_control_row_would_pass_if_agent_stayed_read_only():
    ev = [e for e in load_events(DATA / "codex_trace_negative_control.jsonl")
          if "set image" not in str(e)]
    assert all(c.passed for c in check_trace(ev, should_trigger=False))
