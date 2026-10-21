"""The building blocks from "Building effective agents", implemented on ainative_kit.

- Augmented: the augmented LLM (model + retrieval + memory + tools behind one call)
- agent_loop: the autonomous agent (model picks tools in a loop, with a turn budget)
- chain: prompt chaining with programmatic gates between steps
- route: classify, then dispatch to a specialised handler
- parallel_sections / vote: the two flavours of parallelization
- orchestrator_workers: an LLM plans subtasks at runtime, workers execute, code merges
- evaluator_optimizer: generate, check, feed the check back, with stop rules

Every pattern takes an `LLMClient`, so tests pass a FakeClient and scripts pass get_client().
"""

from __future__ import annotations

import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import LLMClient


# --------------------------------------------------------------------------- helpers

def ask(client: LLMClient, prompt: str, *, system: str | None = None, model: str | None = None,
        max_tokens: int = 1024) -> str:
    """One user turn, one text answer."""
    return client.complete([{"role": "user", "content": prompt}], system=system, model=model,
                           max_tokens=max_tokens).text


def parse_json(s: str) -> Any:
    """Parse JSON from a model answer, tolerating ```json fences and leading prose."""
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    body = m.group(1) if m else s
    start = min([i for i in (body.find("{"), body.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError(f"no JSON found in: {s[:80]!r}")
    return json.loads(body[start:])


# --------------------------------------------------------------------------- augmented LLM

@dataclass
class Augmented:
    """The augmented LLM: one call that is given retrieval results and memory as context."""

    client: LLMClient
    system: str = ""
    retrieve: Callable[[str], list[str]] | None = None
    memory: list[str] = field(default_factory=list)
    model: str | None = None

    def ask(self, question: str) -> str:
        parts = []
        if self.memory:
            parts.append("<memory>\n" + "\n".join(self.memory) + "\n</memory>")
        if self.retrieve:
            docs = self.retrieve(question)
            parts.append("<documents>\n" + "\n---\n".join(docs) + "\n</documents>")
        parts.append(question)
        return ask(self.client, "\n\n".join(parts), system=self.system or None, model=self.model)


# --------------------------------------------------------------------------- agent loop

@dataclass
class Tool:
    schema: dict[str, Any]          # Anthropic tool definition: name, description, input_schema
    fn: Callable[[dict[str, Any]], str]


@dataclass
class AgentResult:
    text: str
    turns: int
    stopped_by: str                  # "end_turn" | "max_turns"
    messages: list[dict[str, Any]]


def agent_loop(client: LLMClient, task: str, tools: dict[str, Tool], *, system: str | None = None,
               max_turns: int = 10) -> AgentResult:
    """The model chooses the next action; code only executes tools and enforces the budget."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    schemas = [t.schema for t in tools.values()]
    for turn in range(1, max_turns + 1):
        resp = client.complete(messages, system=system, tools=schemas)
        messages.append(resp.to_assistant_message())
        if not resp.tool_calls:
            return AgentResult(resp.text, turn, "end_turn", messages)
        results = []
        for call in resp.tool_calls:
            try:
                out = tools[call.name].fn(call.input) if call.name in tools else f"unknown tool {call.name}"
                is_error = call.name not in tools
            except Exception as e:  # tool errors go back to the model, not up the stack
                out, is_error = f"{type(e).__name__}: {e}", True
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": out,
                            "is_error": is_error})
        messages.append({"role": "user", "content": results})
    return AgentResult("", max_turns, "max_turns", messages)


# --------------------------------------------------------------------------- prompt chaining

class GateFailed(Exception):
    def __init__(self, step: str, output: str, reason: str):
        super().__init__(f"gate after step {step!r} failed: {reason}")
        self.step, self.output, self.reason = step, output, reason


@dataclass
class Step:
    name: str
    prompt: Callable[[dict[str, str]], str]       # builds the prompt from earlier outputs
    gate: Callable[[str, dict[str, str]], str | None] = lambda out, ctx: None  # None = pass
    system: str | None = None
    model: str | None = None
    retries: int = 1                               # extra attempts, with the gate reason fed back


def chain(client: LLMClient, steps: list[Step], inputs: dict[str, str]) -> dict[str, str]:
    """Run steps in order. Each output is checked by code before the next step sees it."""
    ctx = dict(inputs)
    for step in steps:
        prompt = step.prompt(ctx)
        for attempt in range(step.retries + 1):
            out = ask(client, prompt, system=step.system, model=step.model)
            reason = step.gate(out, ctx)
            if reason is None:
                break
            prompt = f"{step.prompt(ctx)}\n\nYour previous answer was rejected: {reason}\nFix that and answer again."
        else:
            raise GateFailed(step.name, out, reason)
        ctx[step.name] = out
    return ctx


# --------------------------------------------------------------------------- routing

@dataclass
class Routed:
    label: str
    output: str
    fell_back: bool


def route(client: LLMClient, item: str, handlers: dict[str, Callable[[str], str]], *,
          classifier_system: str, default: str, model: str | None = None) -> Routed:
    """Classify with one (cheap) call, validate the label in code, dispatch."""
    raw = ask(client, item, system=classifier_system, model=model, max_tokens=20).strip().lower()
    label = re.sub(r"[^a-z_]", "", raw.split()[0]) if raw else ""
    fell_back = label not in handlers
    if fell_back:
        label = default
    return Routed(label, handlers[label](item), fell_back)


# --------------------------------------------------------------------------- parallelization

def parallel_sections(sections: dict[str, Callable[[], str]], max_workers: int = 4) -> dict[str, str]:
    """Sectioning: independent subtasks, run concurrently, results keyed by section."""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {name: pool.submit(fn) for name, fn in sections.items()}
        return {name: f.result() for name, f in futures.items()}


@dataclass
class Vote:
    winner: str | None               # None when no answer reaches quorum: abstain, escalate
    tally: dict[str, int]


def vote(client: LLMClient, prompt: str, *, n: int, parse: Callable[[str], str], quorum: float = 0.5,
         system: str | None = None, temperature: float | None = 1.0) -> Vote:
    """Voting: same task n times, take the answer that clears the quorum."""
    answers = [parse(client.complete([{"role": "user", "content": prompt}], system=system,
                                     temperature=temperature).text) for _ in range(n)]
    tally = Counter(answers)
    best, count = tally.most_common(1)[0]
    return Vote(best if count / n > quorum else None, dict(tally))


# --------------------------------------------------------------------------- orchestrator-workers

@dataclass
class OrchestratorResult:
    plan: list[dict[str, Any]]
    worker_outputs: list[Any]
    final: Any
    dropped: list[dict[str, Any]]    # subtasks over the spawn cap or failing validation


def orchestrator_workers(client: LLMClient, task: str, *, plan_system: str,
                         validate: Callable[[dict[str, Any]], bool],
                         worker: Callable[[dict[str, Any]], Any],
                         synthesize: Callable[[list[Any]], Any],
                         max_subtasks: int = 8, max_workers: int = 4) -> OrchestratorResult:
    """The plan is decided at runtime by a model; the spawn cap and validation are code."""
    plan = parse_json(ask(client, task, system=plan_system))
    if isinstance(plan, dict):
        plan = plan.get("subtasks", [])
    good = [p for p in plan if validate(p)]
    dropped = [p for p in plan if not validate(p)] + good[max_subtasks:]
    good = good[:max_subtasks]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        outputs = list(pool.map(worker, good))
    return OrchestratorResult(good, outputs, synthesize(outputs), dropped)


# --------------------------------------------------------------------------- evaluator-optimizer

@dataclass
class Verdict:
    ok: bool
    score: float
    feedback: str


@dataclass
class Attempt:
    candidate: str
    verdict: Verdict


@dataclass
class OptimizeResult:
    best: Attempt | None
    attempts: list[Attempt]
    stopped_by: str                  # "passed" | "max_rounds" | "stalled"


def evaluator_optimizer(generate: Callable[[list[Attempt]], str], evaluate: Callable[[str], Verdict],
                        *, max_rounds: int = 4, stall_rounds: int = 2) -> OptimizeResult:
    """Loop until the evaluator passes, the budget runs out, or `stall_rounds` rounds don't improve."""
    attempts: list[Attempt] = []
    best: Attempt | None = None
    since_improved = 0
    for _ in range(max_rounds):
        cand = generate(attempts)
        att = Attempt(cand, evaluate(cand))
        attempts.append(att)
        if best is None or att.verdict.score > best.verdict.score:
            best, since_improved = att, 0
        else:
            since_improved += 1
        if att.verdict.ok:
            return OptimizeResult(att, attempts, "passed")
        if since_improved >= stall_rounds:
            return OptimizeResult(best, attempts, "stalled")
    return OptimizeResult(best, attempts, "max_rounds")

