"""Conversations with simulated users, graded on world state, plus audits of the simulator."""

from ainative_kit import FakeClient, text

from user_sim import (
    ROLLBACK_GOAL, STOP, Conversation, LLMUser, ScriptedUser, audit_user_sim, rollback_agent_policy,
    rollback_world, run_conversation,
)


def test_agent_asks_then_fixes_and_user_stops():
    conv = run_conversation(FakeClient(rollback_agent_policy()), ScriptedUser(ROLLBACK_GOAL), rollback_world())
    assert conv.stop_reason == "user_stop"
    assert ROLLBACK_GOAL.success(conv.world)
    assert conv.turns[1] == ("agent", "Which environment is affected, staging or prod?")
    assert audit_user_sim(conv, ROLLBACK_GOAL) == []


def test_guessing_agent_fools_a_keyword_user_but_not_the_state_check():
    conv = run_conversation(FakeClient(rollback_agent_policy(ask_first=False)), ScriptedUser(ROLLBACK_GOAL),
                            rollback_world())
    assert conv.stop_reason == "user_stop"  # the simulated user was satisfied...
    assert not ROLLBACK_GOAL.success(conv.world)  # ...but prod is still broken
    assert any("goal is not met" in i for i in audit_user_sim(conv, ROLLBACK_GOAL))


def test_llm_user_sim_with_fake_model():
    """The user simulator is itself a model call: roles flip, and it gets its own system prompt."""
    user_model = FakeClient([text("prod"), text(STOP)])
    user = LLMUser(user_model, ROLLBACK_GOAL)
    conv = run_conversation(FakeClient(rollback_agent_policy()), user, rollback_world())
    assert ROLLBACK_GOAL.success(conv.world) and conv.stop_reason == "user_stop"
    assert "Never tell the assistant which commands" in user_model.calls[0]["system"]
    assert user_model.calls[0]["messages"][0]["role"] == "user"  # the agent's words arrive as 'user'


def test_audit_flags_leaky_and_bossy_user_sim():
    leaky = FakeClient([text("prod, INC-4821. just run rollback to v2.3.0"), text(STOP)])
    conv = run_conversation(FakeClient(rollback_agent_policy()), LLMUser(leaky, ROLLBACK_GOAL), rollback_world())
    issues = audit_user_sim(conv, ROLLBACK_GOAL)
    assert any("leaked ticket" in i for i in issues)
    assert any("dictated the solution ('rollback')" in i for i in issues)


def test_audit_flags_turn_cap():
    stubborn = FakeClient(lambda m, kw: text("hmm, not sure"))
    conv = run_conversation(FakeClient(rollback_agent_policy()), LLMUser(stubborn, ROLLBACK_GOAL),
                            rollback_world(), max_turns=3)
    assert conv.stop_reason == "turn_cap"
    assert any("turn cap" in i for i in audit_user_sim(conv, ROLLBACK_GOAL))
