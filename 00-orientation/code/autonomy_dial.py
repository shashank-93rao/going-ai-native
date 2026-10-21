"""The autonomy dial: task properties x oracle strength -> interaction mode.

A deterministic rule decides. Optionally a model extracts the features from a
free-text task description, but it only *proposes* features; the rule disposes,
and any parse failure falls back to the most conservative features.

    python autonomy_dial.py "Port the Kafka consumer from the 0.x client to 3.x; the contract test suite covers all 41 behaviours"
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

from ainative_kit import FakeClient, LLMClient, get_client, text

MODES = ["chat", "pair", "supervised_agent", "loop", "scheduled"]
ORACLES = ["none", "weak", "partial", "strong"]
# none:    you are the only judge (design, naming, an RFC argument)
# weak:    you can eyeball it, or a manual QA pass (UI feel, log wording)
# partial: tests/types exist but do not pin the behaviour; or a calibrated LLM judge
# strong:  a fast automated check that fails on wrong output (conformance suite, golden files, benchmark threshold)


@dataclass
class Task:
    oracle: str = "none"
    reversible: bool = True  # can you undo it cheaply (revert a PR) vs not (drop a table, send an email)?
    sandboxed: bool = False  # does the agent run where a mistake cannot reach prod or secrets?
    on_distribution: bool = True  # common stack and pattern, vs novel code the model has rarely seen
    large_mechanical: bool = False  # many similar steps (migration, port, upgrade across N services)
    recurring: bool = False  # the same job again every day/week (dependency bumps, flake triage)


@dataclass
class Recommendation:
    mode: str
    reasons: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)


def _step_down(mode: str) -> str:
    return MODES[max(0, MODES.index(mode) - 1)]


def recommend(t: Task) -> Recommendation:
    """Pick the most autonomous mode the oracle can support, then apply caps."""
    if t.oracle not in ORACLES:
        raise ValueError(f"oracle must be one of {ORACLES}")
    reasons: list[str] = []
    guards: list[str] = []

    base = {"none": "chat", "weak": "pair", "partial": "supervised_agent", "strong": "supervised_agent"}[t.oracle]
    reasons.append(f"oracle={t.oracle} supports at most {base}" if t.oracle != "strong" else "strong oracle: unattended work is possible")
    mode = base
    if t.oracle == "strong" and (t.large_mechanical or t.recurring):
        mode = "scheduled" if t.recurring else "loop"
        reasons.append("recurring job" if t.recurring else "large mechanical task: a loop amortises setup")
    elif t.oracle == "strong":
        reasons.append("small task: a loop is overhead; let the agent run the check itself")

    if not t.on_distribution and mode != "chat":
        mode = _step_down(mode)
        reasons.append("off-distribution code: step down one level (agents misread novel code)")

    cap = "supervised_agent"
    if not t.reversible and MODES.index(mode) > MODES.index(cap):
        mode = cap
        reasons.append("irreversible effect: a human approves before the irreversible step")
    if not t.sandboxed and MODES.index(mode) > MODES.index(cap):
        mode = cap
        reasons.append("no sandbox: unattended runs need containment first (see 16-security-and-containment)")

    if mode in ("loop", "scheduled"):
        guards += ["iteration cap", "token/$ budget", "stall + repeat detection", "oracle runs before 'done'"]
    if mode == "scheduled":
        guards += ["idempotent runs (bookmarks, stable IDs)", "alert when a run cannot read its inputs"]
    if mode == "supervised_agent":
        guards += ["review the plan before code", "review the diff and the check output"]
    if mode == "pair":
        guards += ["diffs small enough to review in under a minute"]
    if mode == "chat":
        guards += ["you are the oracle: ask for options and trade-offs, then decide yourself"]
    if t.oracle in ("none", "weak"):
        guards.append("to move the dial right, build a check first (test, golden file, calibrated judge)")
    if not t.reversible:
        guards.append("explicit approval gate on the irreversible action")
    return Recommendation(mode, reasons, guards)


EXTRACT_SYSTEM = (
    "You classify software tasks for an autonomy policy. Reply with ONLY a JSON object with keys: "
    "oracle (one of none|weak|partial|strong), reversible, sandboxed, on_distribution, large_mechanical, recurring "
    "(booleans). 'strong' means an automated check exists that fails on wrong output. If unsure, choose the more "
    "conservative value: weaker oracle, not reversible, not sandboxed."
)


def extract_features(description: str, client: LLMClient) -> Task:
    """Ask a model for the features. Anything unparseable becomes the conservative default."""
    resp = client.complete([{"role": "user", "content": description}], system=EXTRACT_SYSTEM, max_tokens=300)
    try:
        raw = resp.text.strip()
        raw = raw[raw.index("{"): raw.rindex("}") + 1]
        d = json.loads(raw)
        t = Task(**{k: d[k] for k in Task.__dataclass_fields__ if k in d})
        if t.oracle not in ORACLES or not all(isinstance(getattr(t, k), bool) for k in Task.__dataclass_fields__ if k != "oracle"):
            raise ValueError("bad field types")
        return t
    except (ValueError, TypeError, json.JSONDecodeError):
        return Task(oracle="none", reversible=False, sandboxed=False)


_DEMO = FakeClient([text('{"oracle": "strong", "reversible": true, "sandboxed": true, "on_distribution": true, '
                         '"large_mechanical": true, "recurring": false}')])


def main() -> None:
    desc = " ".join(sys.argv[1:]) or "Port the Kafka consumer to the 3.x client; the contract suite covers every behaviour."
    t = extract_features(desc, get_client(fake=_DEMO))
    r = recommend(t)
    print(f"features: {t}\nmode:     {r.mode}")
    for line in r.reasons:
        print(f"  because {line}")
    for g in r.guards:
        print(f"  guard:  {g}")


if __name__ == "__main__":
    main()
