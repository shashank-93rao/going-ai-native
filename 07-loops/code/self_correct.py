"""Generate -> verify -> fix, and a harness that measures whether the fix rounds help.

Two feedback modes:
  external   the verifier's concrete errors go back to the model ("burst 50 > capacity 20")
  intrinsic  the model is only told to "review and fix" with no new information

The point of `measure()` is to report pass rate after each round for each mode, with
the tokens spent, so you decide on numbers whether a reflection round earns its cost.

Task used here: emit a JSON rate-limit policy for a tenant that satisfies hard rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import LLMClient, Response, Usage, get_client

PROMPT = (
    "Write the JSON rate-limit policy for tenant {tenant}. Requirements: {req}. "
    'Fields: name (string), capacity (int > 0), refill_per_sec (number > 0), burst (int, <= capacity). '
    "Reply with only the JSON object."
)


def verify_policy(raw: str, req: dict[str, Any]) -> list[str]:
    """The external verifier: deterministic, returns concrete, actionable errors."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return ["no JSON object found in reply"]
    try:
        p = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    errs = []
    for k, typ in (("name", str), ("capacity", int), ("refill_per_sec", (int, float)), ("burst", int)):
        if not isinstance(p.get(k), typ):
            errs.append(f"field {k!r} missing or wrong type")
    if errs:
        return errs
    if p["capacity"] <= 0 or p["refill_per_sec"] <= 0:
        errs.append("capacity and refill_per_sec must be > 0")
    if p["burst"] > p["capacity"]:
        errs.append(f"burst {p['burst']} > capacity {p['capacity']}")
    if "rps" in req and abs(p["refill_per_sec"] - req["rps"]) > 1e-9:
        errs.append(f"refill_per_sec is {p['refill_per_sec']}, requirement says {req['rps']}")
    return errs


@dataclass
class Attempt:
    passed_at_round: int | None  # None = never passed
    rounds_used: int
    tokens: int
    history: list[list[str]] = field(default_factory=list)


def generate_verify_fix(client: LLMClient, tenant: str, req: dict[str, Any], *, max_rounds: int = 2,
                        mode: str = "external") -> Attempt:
    messages: list[dict[str, Any]] = [{"role": "user", "content": PROMPT.format(tenant=tenant, req=json.dumps(req))}]
    tokens, history = 0, []
    for rnd in range(max_rounds + 1):
        resp = client.complete(messages, max_tokens=400)
        tokens += resp.usage.input_tokens + resp.usage.output_tokens
        errs = verify_policy(resp.text, req)
        history.append(errs)
        if not errs:
            return Attempt(rnd, rnd, tokens, history)
        messages.append(resp.to_assistant_message())
        if mode == "external":
            fb = "The policy failed validation:\n- " + "\n- ".join(errs) + "\nReturn the corrected JSON only."
        else:
            fb = "Review your answer carefully for mistakes and return an improved JSON object."
        messages.append({"role": "user", "content": fb})
    return Attempt(None, max_rounds, tokens, history)


def measure(make_client: Callable[[], LLMClient], cases: list[tuple[str, dict]], max_rounds: int = 2,
            modes: tuple[str, ...] = ("external", "intrinsic")) -> dict[str, dict[str, Any]]:
    """Pass rate after round 0..max_rounds per mode, plus mean tokens per case."""
    report = {}
    for mode in modes:
        attempts = [generate_verify_fix(make_client(), t, r, max_rounds=max_rounds, mode=mode) for t, r in cases]
        n = len(attempts)
        curve = [sum(1 for a in attempts if a.passed_at_round is not None and a.passed_at_round <= k) / n
                 for k in range(max_rounds + 1)]
        report[mode] = {"pass_rate_by_round": curve, "mean_tokens": sum(a.tokens for a in attempts) / n}
    return report


# ---- a scripted stand-in model ------------------------------------------------------
def scripted_model(messages: list[dict], kwargs: dict) -> Response:
    """Deterministic fake: first draft sets burst = 2x capacity (a common slip). It fixes the
    draft only when the feedback names the error; a bare "review it" changes nothing.
    This is a *scripted assumption*, not a measurement of any real model."""
    first = messages[0]["content"]
    rps = float(re.search(r'"rps": ([0-9.]+)', first).group(1)) if '"rps"' in first else 10.0
    last = messages[-1]["content"] if isinstance(messages[-1]["content"], str) else ""
    fixed = "burst" in last and "> capacity" in last
    policy = {"name": "tenant", "capacity": 20, "refill_per_sec": rps, "burst": 20 if fixed else 40}
    return Response(text=json.dumps(policy), usage=Usage(250 + 60 * len(messages), 40))


if __name__ == "__main__":
    from ainative_kit import FakeClient

    cases = [(f"acme-{i}", {"rps": 5 + i}) for i in range(10)]
    rep = measure(lambda: get_client(fake=FakeClient(scripted_model)), cases)
    for mode, r in rep.items():
        curve = " -> ".join(f"{x:.0%}" for x in r["pass_rate_by_round"])
        print(f"{mode:9s} pass rate by round: {curve}   mean tokens/case: {r['mean_tokens']:.0f}")
