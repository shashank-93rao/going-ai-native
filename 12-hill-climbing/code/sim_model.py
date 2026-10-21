"""A simulated routing model, so the whole hill-climb runs offline and repeatably.

This is a FakeClient responder with a ground-truth table behind it. It is NOT
a model of how Claude behaves; it is a controlled world in which the effects
of each change are known, so you can watch the statistics and the keep/revert
rules do their job. The levers it responds to mirror real ones:

- Prompt sections it "reads": queue definitions fix ambiguous-owner alerts;
  a tie-break rule fixes multi-component alert chains; "think step by step"
  does nothing except cost tokens.
- Pasted examples: an alert whose exact text appears in the system prompt is
  answered correctly (memorized), and every other alert gets slightly worse
  (anchoring on the examples). This is the overfitting trap.
- The lookup_owner tool fixes codename services, at the cost of an extra call.
- Effort raises accuracy on multi-signal alerts and output tokens; "max"
  effort sometimes exhausts max_tokens before answering (scored as a miss).
- Model tier shifts accuracy up or down, and price via incident_router.
- Incidents (clusters) get a shared difficulty offset, so errors correlate.
- Each alert has a fixed latent difficulty u in [0, 1); a call succeeds when
  u plus a little per-call jitter falls below p. So most alerts are answered
  the same way every time and a minority near the boundary flip, which is
  roughly how real models behave at default temperature.
- Every call draws from a seeded RNG: same seed, same answers.
"""

from __future__ import annotations

import random
import zlib
from typing import Any

from ainative_kit import FakeClient, Response, ToolCall, Usage

from make_incidents import TEAMS, load_incidents

P_TAG = {"easy": 0.95, "ambiguous": 0.45, "tiebreak": 0.45, "lookup": 0.40}
P_TAG_FIXED = {"ambiguous": 0.85, "tiebreak": 0.85, "lookup": 0.90}
P_REASONING = {"low": 0.30, "medium": 0.50, "high": 0.90, "xhigh": 0.91, "max": 0.92}
OUT_TOKENS = {"low": 60, "medium": 250, "high": 700, "xhigh": 1200, "max": 2000}
MODEL_DELTA = {"claude-haiku-5-5": -0.07, "claude-sonnet-5-5": 0.0, "claude-opus-5-5": 0.03,
               "candidate-model-x": 0.02}
# "candidate-model-x" is a placeholder for "the new model that just shipped" in the
# upgrade drill. It reasons well at low effort and resolves alert chains without
# being told the tie-break rule, so part of the climbed harness becomes dead weight.
NEW_MODEL = "candidate-model-x"
MAX_EFFORT_TRUNCATION = 0.10
CLUSTER_SPREAD = 0.24  # cluster offsets lie in [-0.12, +0.12]
JITTER = 0.30          # per-call noise around each alert's fixed difficulty

_KEYWORDS = [("postgres", "database"), ("-db", "database"), ("kafka", "data-pipeline"), ("k8s", "platform"),
             ("cdn", "edge"), ("auth", "identity"), ("payment", "payments")]


def _h(*parts: Any) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode())


def _cluster_offset(cluster: str) -> float:
    return ((_h("cluster", cluster) % 1000) / 1000 - 0.5) * CLUSTER_SPREAD


def p_correct(item: dict, system: str, model: str, effort: str, used_tool: bool) -> float:
    """Probability the simulated model routes `item` correctly under this config."""
    if item["text"] in system:
        return 1.0  # memorized: the answer key is in the prompt
    tag = item["tag"]
    if tag == "reasoning":
        p = max(P_REASONING[effort], 0.85) if model == NEW_MODEL else P_REASONING[effort]
    elif tag == "ambiguous":
        p = P_TAG_FIXED[tag] if "## Queue definitions" in system else P_TAG[tag]
    elif tag == "tiebreak":
        p = P_TAG_FIXED[tag] if "## Tie-break" in system or model == NEW_MODEL else P_TAG[tag]
    elif tag == "lookup":
        p = P_TAG_FIXED[tag] if used_tool else P_TAG[tag]
    else:
        p = P_TAG["easy"] - (0.02 if effort == "low" else 0.0)
    if "## Examples" in system:
        p -= 0.03
    p += MODEL_DELTA.get(model, 0.0) + _cluster_offset(item["cluster"])
    return min(0.99, max(0.02, p))


def _user_text(messages: list[dict[str, Any]]) -> str:
    first = messages[0]["content"]
    return first if isinstance(first, str) else ""


def make_sim_client(effort: str = "medium", seed: int = 0, items: list[dict] | None = None) -> FakeClient:
    """FakeClient whose answers depend on the prompt, tools, model, effort and seed."""
    by_text = {it["text"]: it for it in (items if items is not None else load_incidents())}
    calls: dict[str, int] = {}

    def respond(messages: list[dict[str, Any]], kw: dict[str, Any]) -> Response:
        system = kw.get("system") or ""
        model = kw.get("model") or "claude-sonnet-5-5"
        alert = _user_text(messages)
        item = by_text.get(alert)
        n_call = calls[alert] = calls.get(alert, 0) + 1
        rng = random.Random(_h(seed, alert, n_call))
        extra = 150 if "step by step" in system else 0
        usage = Usage(input_tokens=(len(system) + len(alert)) // 4 + 50 * (len(messages) - 1),
                      output_tokens=OUT_TOKENS[effort] + extra)
        if effort == "max" and rng.random() < MAX_EFFORT_TRUNCATION:
            return Response(text="", stop_reason="max_tokens", usage=usage, model=model)
        if item is None:  # an alert outside the dataset: crude keyword guess
            guess = next((t for k, t in _KEYWORDS if k in alert.lower()), "platform")
            return Response(text=f"team: {guess}\nreason: keyword match", usage=usage, model=model)
        used_tool = len(messages) > 1
        wants_tool = item["tag"] == "lookup" and kw.get("tools") and not used_tool
        if wants_tool:
            svc = alert.split("svc-")[1].split()[0]
            call = ToolCall(f"toolu_{n_call}", "lookup_owner", {"service": f"svc-{svc}"})
            return Response(tool_calls=[call], stop_reason="tool_use", usage=usage, model=model)
        p = p_correct(item, system, model, effort, used_tool)
        u = (_h("item", item["id"]) % 10_000) / 10_000
        if p >= 1.0 or u + JITTER * (rng.random() - 0.5) < p:
            team = item["label"]
        elif item.get("decoy") and rng.random() < 0.8:
            team = item["decoy"]  # the characteristic mistake: route to the symptom's team
        else:
            team = rng.choice([t for t in TEAMS if t != item["label"]])
        return Response(text=f"team: {team}\nreason: (simulated)", usage=usage, model=model)

    return FakeClient(respond)


def expected_accuracy(items: list[dict], system: str, model: str, effort: str, tools: bool) -> float:
    """Analytic expected accuracy, useful in tests to check the sampler."""
    tot = 0.0
    for it in items:
        used = tools and it["tag"] == "lookup"
        p = p_correct(it, system, model, effort, used)
        tot += p * (1 - MAX_EFFORT_TRUNCATION if effort == "max" else 1)
    return tot / len(items)
