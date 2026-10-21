"""Simulated users, tau-bench style: a user with a goal and private facts talks to the agent.

The agent must ask for what it needs; the user reveals facts only when asked.
Grading is on the world's final state, not on the transcript.

Two simulators:
  ScriptedUser  - rule-based, fully deterministic. Use it in CI.
  LLMUser       - a model plays the user (FakeClient offline, real model with a key).
And an auditor, because LLM user simulators fail in their own ways (see 03-*.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import LLMClient, Response, text, tool

from ops_agent import run_agent
from policies import observations
from world import OpsWorld

STOP = "###STOP###"  # the sentinel tau-bench's user simulator emits when its goal is met


@dataclass
class UserGoal:
    opening: str  # first message; deliberately underspecified
    facts: dict[str, str]  # topic -> value, revealed only when the agent asks about the topic
    success: Callable[[OpsWorld], bool]
    forbidden_hints: list[str] = field(default_factory=list)  # tool names / actions the user must not dictate


ROLLBACK_GOAL = UserGoal(
    opening="checkout is throwing 500s since the last deploy, can you fix it?",
    facts={"env": "prod", "ticket": "INC-4821"},
    success=lambda w: w.snapshot()["checkout/prod"] == {"version": "v2.3.0", "healthy": True, "replicas": 3},
    forbidden_hints=["rollback", "kubectl", "v2.3.0"],
)


def rollback_world(seed: int = 0) -> OpsWorld:
    """checkout/prod is on a bad version; the previous good version is in its history."""
    w = OpsWorld(seed=seed, bad_versions=frozenset({"v2.5.0"}))
    w.preset("checkout", "prod", "v2.5.0", history=["v2.3.0"])
    return w


class ScriptedUser:
    """Answers keyword-matched questions from `facts`; says STOP when the agent reports done."""

    def __init__(self, goal: UserGoal):
        self.goal = goal

    def first_message(self) -> str:
        return self.goal.opening

    def respond(self, agent_text: str) -> str:
        t = agent_text.lower()
        if re.search(r"\b(rolled back|restored|fixed)\b", t):
            return STOP
        answers = [f"{topic}: {val}" for topic, val in self.goal.facts.items() if topic in t
                   or (topic == "env" and re.search(r"environment|staging|prod", t))]
        return ", ".join(answers) if answers else "not sure, I just see the errors on the dashboard"


USER_SYSTEM = """You are simulating a user talking to an ops assistant.
Your situation: {opening}
Private facts (reveal one only when the assistant asks about it): {facts}
Rules: one short line per turn. Never tell the assistant which commands or tools to use.
Do not invent facts that are not listed. When the problem is fixed, reply with {stop} alone."""


class LLMUser:
    """A model plays the user. Note the roles flip: the agent's text is the 'user' turn here."""

    def __init__(self, client: LLMClient, goal: UserGoal):
        self.client, self.goal = client, goal
        self.system = USER_SYSTEM.format(opening=goal.opening, facts=goal.facts, stop=STOP)
        self.history: list[dict[str, Any]] = []

    def first_message(self) -> str:
        return self.goal.opening

    def respond(self, agent_text: str) -> str:
        self.history.append({"role": "user", "content": agent_text})
        reply = self.client.complete(self.history, system=self.system, max_tokens=200).text.strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply


@dataclass
class Conversation:
    turns: list[tuple[str, str]]  # (speaker, text)
    world: OpsWorld
    stop_reason: str  # "user_stop" | "turn_cap" | "agent_budget" | "infra_error"


def run_conversation(agent_client: LLMClient, user: Any, world: OpsWorld, max_turns: int = 6) -> Conversation:
    messages: list[dict[str, Any]] = [{"role": "user", "content": user.first_message()}]
    turns = [("user", user.first_message())]
    for _ in range(max_turns):
        run = run_agent(agent_client, world, messages, max_steps=8)
        if run.stop_reason != "end_turn":
            return Conversation(turns, world, "agent_budget" if run.stop_reason == "step_budget" else run.stop_reason)
        turns.append(("agent", run.final_text))
        reply = user.respond(run.final_text)
        turns.append(("user", reply))
        if reply.strip() == STOP:
            return Conversation(turns, world, "user_stop")
        messages.append({"role": "user", "content": reply})
    return Conversation(turns, world, "turn_cap")


def audit_user_sim(conv: Conversation, goal: UserGoal) -> list[str]:
    """Flag the classic user-simulator failures. Each one makes the eval easier or meaningless."""
    issues: list[str] = []
    asked: set[str] = set()
    for i, (who, msg) in enumerate(conv.turns):
        low = msg.lower()
        if who == "agent":
            asked |= {t for t in goal.facts if t in low or (t == "env" and "environment" in low)}
            continue
        for topic, val in goal.facts.items():
            if val.lower() in low and topic not in asked:
                issues.append(f"turn {i}: leaked {topic}={val} before the agent asked")
        for hint in goal.forbidden_hints:
            if hint.lower() in low:
                issues.append(f"turn {i}: user dictated the solution ({hint!r})")
        if msg.strip() == STOP and not goal.success(conv.world):
            issues.append(f"turn {i}: user stopped but the goal is not met in the world")
    if conv.stop_reason == "turn_cap":
        issues.append("conversation hit the turn cap: user never confirmed, or the agent never finished")
    return issues


def rollback_agent_policy(ask_first: bool = True) -> Callable[[list[dict[str, Any]], dict[str, Any]], Response]:
    """Scripted agent for the rollback conversation. ask_first=False is the 'guesses the env' bug."""

    def respond(messages: list[dict[str, Any]], _kw: dict[str, Any]) -> Response:
        said = " ".join(m["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], str))
        env = "prod" if "prod" in said.lower() else None
        if env is None:
            if ask_first:
                return text("Which environment is affected, staging or prod?")
            env = "staging"  # the bug: guess instead of asking
        obs = observations(messages)
        tid = f"toolu_{len(obs):03d}"
        mine = [o for o in obs if o[1].get("env") == env]
        if not mine:
            return tool("get_status", {"service": "checkout", "env": env}, id=tid)
        status = mine[0][2]
        if not ask_first:  # the guessing agent also skips the health check and over-claims
            if len(mine) == 1:
                return tool("rollback", {"service": "checkout", "env": env, "request_id": f"rb-checkout-{env}"}, id=tid)
            return text(f"Rolled back checkout in {env}.")
        if status.get("healthy"):
            return text(f"checkout in {env} looks healthy ({status['version']}). Can you confirm the environment?")
        if not [o for o in mine if o[0] == "rollback" and o[2].get("ok")]:
            return tool("rollback", {"service": "checkout", "env": env, "request_id": f"rb-checkout-{env}"}, id=tid)
        return text(f"Rolled back checkout in {env} to {[o for o in mine if o[0] == 'rollback'][-1][2]['version']}.")

    return respond
