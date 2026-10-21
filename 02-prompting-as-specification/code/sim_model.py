"""A scripted stand-in for the model, used by tests and offline demos.

It is NOT a model and its numbers are NOT measurements. It is a deterministic
function that reacts to the *spec* in the system prompt the way the module
argues a real model does, so the A/B harness has something to compare:

- Without an output-format section, it answers in friendly prose (a real model
  given no format will pick one, and it will not be your router's format).
- Without a closed severity enum, it invents its own scale (high/medium/low).
- It applies "settled signature" rule lines it finds in the prompt, in order:
      - `kw1`, `kw2` → category `X`, severity `Y`
  (Rules apply to the excerpt literally, which is exactly how a too-broad rule bites.)
- Otherwise it falls back to a naive keyword guess, abstaining when it has nothing.

Use it with FakeClient:  FakeClient(simulated_model)
"""

from __future__ import annotations

import json
import re
from typing import Any

from ainative_kit import Response, Usage

_RULE = re.compile(r"^- (.+?) → category `(\w+)`, severity `(\w+)`", re.MULTILINE)
_SERVICE = re.compile(r"Z ([a-z][a-z0-9-]+) ")


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    content = messages[-1]["content"]
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if b.get("type") == "text")
    return content


def _excerpt(messages: list[dict[str, Any]]) -> str:
    first = messages[0]["content"]
    m = re.search(r"<excerpt>\n(.*)\n</excerpt>", first, re.S)
    return m.group(1) if m else first


def triage_guess(system: str, excerpt: str) -> dict[str, Any]:
    lines = excerpt.splitlines()
    low = excerpt.lower()
    has_enum = "`page`" in system and "`ticket`" in system
    for m in _RULE.finditer(system):
        keywords = re.findall(r"`([^`]+)`", m.group(1))
        hit = next((k for k in keywords if k.lower() in low), None)
        if hit:
            line = next(l for l in lines if hit.lower() in l.lower())
            return _out(m.group(2), m.group(3), line, lines, needs_human=False)
    if re.search(r"exception|error|traceback|failed|fatal", low):
        line = next(l for l in lines if re.search(r"exception|error|traceback|failed|fatal", l, re.I))
        return _out("app_bug", "ticket" if has_enum else "high", line, lines, needs_human=False)
    return _out("unknown", "ticket" if has_enum else "low", lines[-1], lines, needs_human=True)


def _out(category: str, severity: str, line: str, lines: list[str], needs_human: bool) -> dict[str, Any]:
    svc = _SERVICE.search(line) or _SERVICE.search(lines[0])
    service = svc.group(1) if svc else "unknown"
    return {
        "category": category,
        "severity": severity,
        "service": service,
        "summary": f"{service}: {line.split(' ', 2)[-1][:120]}",
        "evidence": [line],
        "needs_human": needs_human,
    }


def simulated_model(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    system = kwargs.get("system") or ""
    excerpt = _excerpt(messages)
    guess = triage_guess(system, excerpt)
    if "<output_format>" in system or "Respond with only the JSON" in system:
        body = json.dumps(guess)
    else:
        body = (f"Sure! Here's my analysis of the logs.\n\n**Problem:** {guess['category']}\n"
                f"**Severity:** {guess['severity'].upper()}\n\nLet me know if you want me to dig deeper.")
    if "failed validation" in _last_user_text(messages) and "<output_format>" not in system:
        body = "Apologies. " + body  # without a stated format, feedback alone does not fix it
    return Response(text=body, usage=Usage(len(system) // 4 + len(excerpt) // 4, len(body) // 4))
