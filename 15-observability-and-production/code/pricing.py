"""Per-model token prices and a cost function that understands prompt caching.

Prices are USD per million tokens, copied from
https://platform.claude.com/docs/en/about-claude/pricing on 2026-10-19
(5-minute cache writes; Haiku 5.5 row is for prompts up to 100k tokens).
Prices change: load them from config in real code, and re-check before quoting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float        # base (uncached) input, $/MTok
    cache_write: float  # 5-minute cache write, $/MTok
    cache_read: float   # cache hit / refresh, $/MTok
    output: float       # $/MTok


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, cache_write=5.00, cache_read=0.20, output=20.00),
    "claude-sonnet-5-5": Price(input=2.00, cache_write=2.50, cache_read=0.10, output=10.00),
    "claude-haiku-5-5": Price(input=0.10, cache_write=0.125, cache_read=0.01, output=0.50),
    "claude-fable-5-1": Price(input=10.00, cache_write=12.50, cache_read=0.25, output=50.00),
}


def cost_usd(model: str, *, input_tokens: int, output_tokens: int,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    """Cost of one call. `input_tokens` is Anthropic's field: tokens NOT read from or written to cache."""
    p = PRICES[model]
    return (
        input_tokens * p.input
        + cache_write_tokens * p.cache_write
        + cache_read_tokens * p.cache_read
        + output_tokens * p.output
    ) / 1_000_000


def cache_hit_rate(cache_read_tokens: int, cache_write_tokens: int) -> float:
    """Prefix cache hit rate: of the tokens that were *eligible* for caching (read or written),
    how many were reads. This is the number to put an SLO on; a drop means a prefix changed."""
    total = cache_read_tokens + cache_write_tokens
    return cache_read_tokens / total if total else 0.0


def cached_input_share(input_tokens: int, cache_read_tokens: int, cache_write_tokens: int) -> float:
    """Share of ALL prompt tokens served from cache. Bounded above by how much of the prompt
    is a stable prefix, so it is a design metric, not an alerting one."""
    total = input_tokens + cache_read_tokens + cache_write_tokens
    return cache_read_tokens / total if total else 0.0
