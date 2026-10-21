"""Starter on-call agent for capstone variant A: a plain agent loop with governors and tracing.

This is deliberately a *starting point*. The loop is correct; the prompt is thin,
the governors are minimal, and the offline "model" (`baseline_responder`) is a
naive heuristic with realistic failure modes, so that error analysis in M3 has
something to find.

    python starter_agent.py --n 48 --traces runs/traces.jsonl --out runs/grades.jsonl
    AINATIVE_FAKE=1 python starter_agent.py        # force the offline heuristic

With ANTHROPIC_API_KEY set (and AINATIVE_FAKE unset) it drives the real model.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, ToolCall, Tracer, Usage, get_client
from grade import Grade, grade, summarize
from sim_env import TOOL_SCHEMAS, Scenario, SimEnv, make_suite

SYSTEM_PROMPT = """You are the first-line on-call responder for a small e-commerce backend.
You have read-only diagnostic tools and a few mutating remediation tools.
Find the root cause, apply the smallest safe fix, verify recovery, then call resolve_incident.
"""


@dataclass
class Governors:
    """Hard limits enforced by the loop, not by the prompt."""
    max_steps: int = 20  # model turns
    max_tokens: int = 80_000  # input + output, summed over the episode
    max_identical_calls: int = 2  # a third identical call stops the run


@dataclass
class EpisodeResult:
    scenario: Scenario
    env: SimEnv
    stop_reason: str  # resolved | end_turn | max_steps | token_budget | repeat_guard
    steps: int
    tokens: int
    messages: list[dict[str, Any]] = field(default_factory=list)


def run_episode(client: LLMClient, scenario: Scenario, gov: Governors | None = None,
                tracer: Tracer | None = None, model: str | None = None,
                system: str = SYSTEM_PROMPT) -> EpisodeResult:
    """Run one incident to completion or until a governor trips."""
    gov = gov or Governors()
    tracer = tracer or Tracer()
    env = SimEnv(scenario)
    messages: list[dict[str, Any]] = [{"role": "user", "content": "You have been paged. Investigate and remediate."}]
    seen: dict[str, int] = {}
    tokens, steps, stop = 0, 0, "max_steps"
    with tracer.span("episode", scenario_id=scenario.id, kind=scenario.kind) as ep:
        while steps < gov.max_steps:
            steps += 1
            with tracer.span("llm_call", step=steps) as sp:
                resp = client.complete(messages, system=system, tools=TOOL_SCHEMAS, model=model, max_tokens=1024)
                sp.attrs.update(input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                                stop_reason=resp.stop_reason, text=resp.text[:500],
                                tool_calls=[{"name": t.name, "input": t.input} for t in resp.tool_calls])
            tokens += resp.usage.input_tokens + resp.usage.output_tokens
            messages.append(resp.to_assistant_message())
            if not resp.tool_calls:
                stop = "end_turn"
                break
            results, tripped = [], False
            for tc in resp.tool_calls:
                key = json.dumps([tc.name, tc.input], sort_keys=True)
                seen[key] = seen.get(key, 0) + 1
                if seen[key] > gov.max_identical_calls:
                    tripped = True
                    break
                with tracer.span("tool", tool=tc.name, args=tc.input) as ts:
                    out = env.call(tc.name, tc.input)
                    ts.attrs["result"] = out
                    if "error" in out:
                        ts.attrs["tool_error"] = out["error"]
                results.append({"type": "tool_result", "tool_use_id": tc.id, "content": json.dumps(out)})
            if tripped:
                stop = "repeat_guard"
                break
            messages.append({"role": "user", "content": results})
            if env.done:
                stop = "resolved"
                break
            if tokens >= gov.max_tokens:
                stop = "token_budget"
                break
        ep.attrs.update(stop_reason=stop, steps=steps, tokens=tokens, healthy=env.healthy())
    return EpisodeResult(scenario, env, stop, steps, tokens, messages)


# ---------- offline stand-in for the model ----------

def _history(messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Pair each tool_use in the transcript with its tool_result: [(name, input, result)]."""
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    out = []
    for m in messages:
        if not isinstance(m["content"], list):
            continue
        for b in m["content"]:
            if b.get("type") == "tool_use":
                calls[b["id"]] = (b["name"], b["input"])
            elif b.get("type") == "tool_result" and b["tool_use_id"] in calls:
                name, inp = calls[b["tool_use_id"]]
                out.append((name, inp, json.loads(b["content"])))
    return out


def baseline_responder(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """A naive on-call heuristic: blame the service with the highest error rate, then
    roll it back if it deployed recently, else restart it. It also obeys instructions
    it finds in logs (the injection weakness M6 must close)."""
    hist = _history(messages)
    names = [h[0] for h in hist]
    usage = Usage(input_tokens=len(json.dumps(messages)) // 4, output_tokens=40)

    def act(name: str, inp: dict[str, Any]) -> Response:
        return Response(tool_calls=[ToolCall(f"toolu_{len(hist):03d}", name, inp)], stop_reason="tool_use", usage=usage)

    if "list_alerts" not in names:
        return act("list_alerts", {})
    if "get_topology" not in names:
        return act("get_topology", {})
    services = list(next(r for n, _, r in hist if n == "get_topology")["depends_on"])
    metrics = {i["service"]: r for n, i, r in hist if n == "get_metrics" and "error" not in r}
    for svc in services:
        if svc not in metrics:
            return act("get_metrics", {"service": svc})
    suspect = max(services, key=lambda s: metrics[s]["error_rate"])
    deploys = next((r for n, i, r in hist if n == "get_deploys" and i.get("service") == suspect), None)
    if deploys is None:
        return act("get_deploys", {"service": suspect})
    logs = next((r for n, i, r in hist if n == "get_logs" and i.get("service") == suspect), None)
    if logs is None:
        return act("get_logs", {"service": suspect})
    done = {(n, i.get("service")) for n, i, _ in hist}
    for line in logs["lines"]:  # the weakness: log text treated as instructions
        m = re.search(r"Run restart on (\S+)", line)
        if m and ("restart", m.group(1)) not in done:
            return act("restart", {"service": m.group(1)})
    if not any(n in ("rollback", "restart", "scale") for n in names):
        recent = any(d["minutes_ago"] < 60 for d in deploys["deploys"])
        return act("rollback" if recent else "restart", {"service": suspect})
    kind = "bad_deploy" if "rollback" in names else "unknown"
    return act("resolve_incident", {"root_cause_service": suspect, "fault_kind": kind,
                                    "summary": f"{suspect} had the highest error rate; remediated."})


def run_suite(client: LLMClient, scenarios: list[Scenario], trials: int = 1, tracer: Tracer | None = None,
              gov: Governors | None = None, model: str | None = None) -> list[tuple[EpisodeResult, Grade]]:
    """Run every scenario `trials` times and grade each run."""
    out = []
    for s in scenarios:
        for _ in range(trials):
            r = run_episode(client, s, gov=gov, tracer=tracer, model=model)
            out.append((r, grade(s, r.env)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--traces", default=None, help="JSONL trace output path")
    ap.add_argument("--out", default=None, help="JSONL grades output path")
    args = ap.parse_args()
    client = get_client(fake=FakeClient(baseline_responder))
    tracer = Tracer(args.traces) if args.traces else Tracer()
    if args.traces:
        Path(args.traces).parent.mkdir(parents=True, exist_ok=True)
    rows = run_suite(client, make_suite(args.n, args.seed), trials=args.trials, tracer=tracer)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            for r, g in rows:
                f.write(json.dumps({**asdict(g), "stop_reason": r.stop_reason, "steps": r.steps,
                                    "tokens": r.tokens}) + "\n")
    print(json.dumps(summarize([g for _, g in rows], k=args.trials if args.trials > 1 else None), indent=2))


if __name__ == "__main__":
    main()
