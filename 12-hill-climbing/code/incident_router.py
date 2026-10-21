"""The system under test: an LLM incident router.

A config (a plain dict, usually loaded from JSON or YAML) fully describes one
variant, so a hill-climb compares configs, never hand-edited code:

    {"name": "v0-baseline", "model": "claude-sonnet-5-5", "effort": "medium",
     "sections": ["base"], "tools": [], "extra_prompt": ""}

`route()` builds the system prompt from the sections, calls the model through
ainative_kit, runs the `lookup_owner` tool if the model asks for it, and parses
"team: <name>" from the reply.

`effort` is forwarded to the client (ainative_kit sends it as
`output_config.effort` on the real API). The simulated model (sim_model.py)
also honors it, through its own seeded behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ainative_kit import LLMClient, Response

from make_incidents import OWNERS, TEAMS

PROMPTS = Path(__file__).parent / "data" / "prompts"

LOOKUP_OWNER_TOOL = {
    "name": "lookup_owner",
    "description": ("Look up the owning team for an internal service codename such as 'svc-orion'. "
                    "Use it whenever the alert names a service whose owner is not obvious from the team list."),
    "input_schema": {"type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"]},
}
TOOLS = {"lookup_owner": LOOKUP_OWNER_TOOL}

DEFAULT_CONFIG: dict[str, Any] = {
    "name": "v0-baseline", "model": "claude-sonnet-5-5", "effort": "medium",
    "sections": ["base"], "tools": [], "extra_prompt": "", "max_tokens": 1024,
}


@dataclass
class RouteResult:
    team: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    truncated: bool = False
    tool_calls: list[str] = field(default_factory=list)


def build_system(config: dict[str, Any], prompts_dir: Path = PROMPTS) -> str:
    parts = [(prompts_dir / f"{s}.md").read_text().strip() for s in config.get("sections", ["base"])]
    if config.get("extra_prompt"):
        parts.append(config["extra_prompt"].strip())
    return "\n\n".join(parts)


def lookup_owner(service: str) -> str:
    key = service.lower().removeprefix("svc-").strip()
    return OWNERS.get(key, "unknown")


_TEAM_RE = re.compile(r"^\s*team:\s*([a-z\-]+)", re.IGNORECASE | re.MULTILINE)


def parse_team(text: str) -> str | None:
    m = _TEAM_RE.search(text or "")
    if not m:
        return None
    team = m.group(1).lower()
    return team if team in TEAMS else None


def route(client: LLMClient, config: dict[str, Any], alert_text: str, max_turns: int = 3) -> RouteResult:
    """Route one alert. Bounded tool loop: at most `max_turns` model calls."""
    system = build_system(config)
    tools = [TOOLS[t] for t in config.get("tools", [])] or None
    messages: list[dict[str, Any]] = [{"role": "user", "content": alert_text}]
    res = RouteResult(team=None)
    for _ in range(max_turns):
        resp: Response = client.complete(messages, system=system, tools=tools,
                                         model=config.get("model"), max_tokens=config.get("max_tokens", 1024),
                                         effort=config.get("effort"))
        res.calls += 1
        res.input_tokens += resp.usage.input_tokens
        res.output_tokens += resp.usage.output_tokens
        if resp.stop_reason == "max_tokens":
            res.truncated = True  # ran out of output budget before answering: scored as a miss
            return res
        if not resp.tool_calls:
            res.team = parse_team(resp.text)
            return res
        messages.append(resp.to_assistant_message())
        results = []
        for tc in resp.tool_calls:
            res.tool_calls.append(tc.name)
            out = lookup_owner(tc.input.get("service", "")) if tc.name == "lookup_owner" else "unknown tool"
            results.append({"type": "tool_result", "tool_use_id": tc.id, "content": out})
        messages.append({"role": "user", "content": results})
    return res


# USD per million tokens (input, output). Claude rows are list prices as cached by
# the claude-api skill on 2026-10-06 (Haiku 5.5 prompts under 100K tokens); check
# the pricing page before relying on them. candidate-model-x is a placeholder.
PRICES_ILLUSTRATIVE: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "candidate-model-x": (1.0, 5.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES_ILLUSTRATIVE.get(model, (2.0, 10.0))
    return (input_tokens * pin + output_tokens * pout) / 1e6


if __name__ == "__main__":
    from ainative_kit import get_client

    from sim_model import make_sim_client

    alert = "[alert 999.0] connection pool to ledger-db exhausted from payments-api; checkout errors 12%"
    cfg = dict(DEFAULT_CONFIG, sections=["base", "queue_definitions"])
    client = get_client(fake=make_sim_client(effort=cfg["effort"], seed=1))
    r = route(client, cfg, alert)
    print(f"team={r.team} calls={r.calls} tokens={r.input_tokens}/{r.output_tokens}")
