"""Reproduce the "prompt-cache misses blew the budget" incident offline.

A fake client emulates Anthropic-style prefix caching: the cacheable prefix is
tools + system prompt; an exact-match entry lives 5 minutes from its last use.
We run the same traffic twice:

  v14: static system prompt                        -> high hit rate
  v15: system prompt starts with the current time  -> every request writes the cache

and report hit rate and cost per request, the two numbers that should have paged.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

from ainative_kit import Response, Usage
from pricing import cache_hit_rate, cost_usd

STATIC_RULES = ("You are the on-call alert summarizer for the payments platform.\n"
                "Return JSON with keys service, severity, summary, runbook.\n") + ("Rule: ...\n" * 1500)
TOOLS = [{"name": "get_runbook", "description": "Fetch a runbook by id", "input_schema": {"type": "object"}}]


def tokens(s: str) -> int:
    return len(s) // 4


class CachingFakeClient:
    """Answers every request with a fixed note and reports cache usage like the real API."""

    def __init__(self, clock: Callable[[], float], ttl_s: float = 300.0, min_cacheable: int = 512):
        self.clock, self.ttl_s, self.min_cacheable = clock, ttl_s, min_cacheable
        self._cache: dict[str, float] = {}

    def complete(self, messages, *, system=None, tools=None, model=None, max_tokens=2048, temperature=None) -> Response:
        prefix = json.dumps(tools or [], sort_keys=True) + (system or "")
        key, now = hashlib.sha256(prefix.encode()).hexdigest(), self.clock()
        p_tok = tokens(prefix)
        tail = sum(tokens(str(m["content"])) for m in messages)
        u = Usage(input_tokens=tail, output_tokens=180)
        u.cache_read_input_tokens = u.cache_creation_input_tokens = 0
        if p_tok < self.min_cacheable:
            u.input_tokens += p_tok  # below the minimum: silently not cached
        elif key in self._cache and now - self._cache[key] < self.ttl_s:
            u.cache_read_input_tokens = p_tok
        else:
            u.cache_creation_input_tokens = p_tok
        if p_tok >= self.min_cacheable:
            self._cache[key] = now  # a write or a read refreshes the TTL
        return Response(text='{"service": "payments-worker", "severity": "sev2"}', usage=u, model=model or "")


def system_prompt(version: str, now: float) -> str:
    if version == "v15":  # the regression: a "helpful" timestamp at the top of the prompt
        stamp = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return f"Current time: {stamp} UTC\n" + STATIC_RULES
    return STATIC_RULES


def simulate(version: str, n: int = 2000, spacing_s: float = 3.0, model: str = "claude-sonnet-5-5") -> dict[str, Any]:
    t = {"now": 1_790_000_000.0}
    client = CachingFakeClient(lambda: t["now"])
    reads = writes = 0
    total = 0.0
    for i in range(n):
        t["now"] += spacing_s
        msg = [{"role": "user", "content": f"ALERT {i}: consumer lag on ledger topic partition {i % 12} " * 20}]
        r = client.complete(msg, system=system_prompt(version, t["now"]), tools=TOOLS, model=model)
        reads += r.usage.cache_read_input_tokens
        writes += r.usage.cache_creation_input_tokens
        total += cost_usd(model, input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens,
                          cache_read_tokens=r.usage.cache_read_input_tokens,
                          cache_write_tokens=r.usage.cache_creation_input_tokens)
    return {"version": version, "requests": n, "cache_hit_rate": cache_hit_rate(reads, writes),
            "cost_per_request_usd": total / n, "cost_per_day_usd_at_1M_req": total / n * 1_000_000}


if __name__ == "__main__":
    for v in ("v14", "v15"):
        r = simulate(v)
        print(f"{r['version']}: hit rate {r['cache_hit_rate']:.3f}, ${r['cost_per_request_usd']:.5f}/req, "
              f"${r['cost_per_day_usd_at_1M_req']:,.0f}/day at 1M req/day")
