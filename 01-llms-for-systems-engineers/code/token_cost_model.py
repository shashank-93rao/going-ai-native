"""Token, cost and latency model for LLM calls, including prompt caching.

Treat this like a capacity-planning spreadsheet for a metered remote dependency.
Every price and throughput number is a *parameter*. `EXAMPLE_PRICES` holds the
Anthropic list prices checked on 2026-10-19 (platform.claude.com/docs/en/about-claude/pricing)
so the demo has realistic inputs; re-check them before you rely on them.

Billing model (Anthropic Messages API, per the prompt-caching docs):
    total_input = input_tokens (uncached) + cache_creation_input_tokens + cache_read_input_tokens
    cost = uncached*base + writes*base*write_mult + reads*base*read_mult + output*output_price

Run:  python token_cost_model.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

MTOK = 1_000_000


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens, plus cache multipliers relative to base input."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_mult: float = 0.1
    cache_write_5m_mult: float = 1.25
    cache_write_1h_mult: float = 2.0

    def write_mult(self, ttl: str = "5m") -> float:
        if ttl not in ("5m", "1h"):
            raise ValueError(f"ttl must be '5m' or '1h', got {ttl!r}")
        return self.cache_write_5m_mult if ttl == "5m" else self.cache_write_1h_mult


# List prices checked 2026-10-19. Parameters, not facts: verify before use.
EXAMPLE_PRICES: dict[str, Pricing] = {
    "claude-opus-5-5": Pricing(4.00, 20.00, cache_read_mult=0.05),
    "claude-sonnet-5-5": Pricing(2.00, 10.00, cache_read_mult=0.05),
    "claude-haiku-5-5": Pricing(0.10, 0.50, cache_read_mult=0.1),  # prompts <= 100k tokens
    "claude-fable-5-1": Pricing(10.00, 50.00, cache_read_mult=0.025),
}


@dataclass
class TokenUsage:
    """Mirrors the API's usage fields. `uncached_input` is the API's `input_tokens`."""

    uncached_input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0

    @property
    def total_input(self) -> int:
        return self.uncached_input + self.cache_write + self.cache_read

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.uncached_input + other.uncached_input,
            self.cache_write + other.cache_write,
            self.cache_read + other.cache_read,
            self.output + other.output,
        )


def cost(usage: TokenUsage, p: Pricing, ttl: str = "5m") -> float:
    """Dollar cost of one request (or a summed set of requests)."""
    base = p.input_per_mtok / MTOK
    return (
        usage.uncached_input * base
        + usage.cache_write * base * p.write_mult(ttl)
        + usage.cache_read * base * p.cache_read_mult
        + usage.output * p.output_per_mtok / MTOK
    )


def expected_request_cost(
    p: Pricing,
    prefix_tokens: int,
    suffix_tokens: int,
    output_tokens: int,
    hit_rate: float,
    ttl: str = "5m",
) -> float:
    """Expected cost of a request whose cacheable prefix hits with probability `hit_rate`.

    On a hit the prefix is billed as a cache read; on a miss it is re-written.
    `hit_rate=None`-style "caching off" is modelled by `uncached_request_cost`.
    """
    if not 0.0 <= hit_rate <= 1.0:
        raise ValueError("hit_rate must be in [0, 1]")
    hit = cost(TokenUsage(suffix_tokens, 0, prefix_tokens, output_tokens), p, ttl)
    miss = cost(TokenUsage(suffix_tokens, prefix_tokens, 0, output_tokens), p, ttl)
    return hit_rate * hit + (1 - hit_rate) * miss


def uncached_request_cost(p: Pricing, prefix_tokens: int, suffix_tokens: int, output_tokens: int) -> float:
    return cost(TokenUsage(prefix_tokens + suffix_tokens, 0, 0, output_tokens), p)


def break_even_hit_rate(p: Pricing, ttl: str = "5m") -> float:
    """Hit rate above which marking the prefix cacheable beats not caching it.

    Solve h*r + (1-h)*w = 1 for h, with r = read mult, w = write mult.
    """
    w, r = p.write_mult(ttl), p.cache_read_mult
    return (w - 1) / (w - r)


@dataclass
class AgentLoopShape:
    """An append-only agent loop: every turn resends the whole history."""

    system_and_tools: int = 8_000  # static prefix
    first_user: int = 1_000
    per_turn_tool_result: int = 2_500  # appended each turn
    per_turn_output: int = 400  # model's tool call / reasoning text, also appended
    turns: int = 30


def agent_loop_usage(shape: AgentLoopShape, mode: str = "append_only") -> list[TokenUsage]:
    """Per-turn usage for three prompt disciplines.

    - "no_cache": no cache_control at all; everything is uncached input.
    - "append_only": breakpoint on the newest block; each turn reads the prior
      prefix and writes only the delta (the healthy-loop signature).
    - "mutated_prefix": something near the top changes every turn (a timestamp in
      the system prompt, a re-sorted tool list), so every turn re-writes it all.
    """
    if mode not in ("no_cache", "append_only", "mutated_prefix"):
        raise ValueError(mode)
    out: list[TokenUsage] = []
    prior = 0  # tokens already in the prefix the previous request cached
    for t in range(shape.turns):
        new = shape.system_and_tools + shape.first_user if t == 0 else shape.per_turn_tool_result + shape.per_turn_output
        total = prior + new
        if mode == "no_cache":
            u = TokenUsage(total, 0, 0, shape.per_turn_output)
        elif mode == "append_only":
            u = TokenUsage(0, new, prior, shape.per_turn_output)
        else:
            u = TokenUsage(0, total, 0, shape.per_turn_output)
        out.append(u)
        prior = total
    return out


def summarize(usages: list[TokenUsage]) -> TokenUsage:
    total = TokenUsage()
    for u in usages:
        total = total + u
    return total


@dataclass(frozen=True)
class LatencyModel:
    """Latency = overhead + prefill(uncached) + prefill(cached) + decode(output).

    Defaults are illustrative placeholders, not measured numbers. Measure your
    own p50/p95 TTFT and output tokens/sec and plug them in.
    """

    overhead_s: float = 0.4  # network, queueing, auth, routing
    prefill_tps: float = 10_000.0  # uncached input tokens processed per second
    cached_prefill_speedup: float = 10.0  # cached tokens are this much cheaper to "prefill"
    decode_tps: float = 60.0  # output tokens per second (includes thinking tokens)

    def ttft(self, usage: TokenUsage) -> float:
        uncached = usage.uncached_input + usage.cache_write
        return (
            self.overhead_s
            + uncached / self.prefill_tps
            + usage.cache_read / (self.prefill_tps * self.cached_prefill_speedup)
        )

    def total(self, usage: TokenUsage) -> float:
        return self.ttft(usage) + usage.output / self.decode_tps


def estimate_tokens(text: str, chars_per_token: float = 3.5) -> int:
    """Crude offline estimate. Use the API's count_tokens endpoint for real numbers.

    Code, JSON, non-English text and long digit strings tokenize worse than prose,
    so treat this as a lower bound for those inputs.
    """
    return max(1, round(len(text) / chars_per_token)) if text else 0


def _fmt(x: float) -> str:
    return f"${x:,.4f}" if x < 1 else f"${x:,.2f}"


def main() -> None:
    p = EXAMPLE_PRICES["claude-sonnet-5-5"]
    print("Model: claude-sonnet-5-5 (example list prices, verify before use)\n")

    print("1) Single request, 20k-token shared prefix, 500-token question, 300-token answer")
    print(f"   uncached:                 {_fmt(uncached_request_cost(p, 20_000, 500, 300))}")
    for h in (0.0, 0.5, 0.9, 0.99):
        print(f"   cached, hit rate {h:>4.0%}:    {_fmt(expected_request_cost(p, 20_000, 500, 300, h))}")
    print(f"   break-even hit rate (5m): {break_even_hit_rate(p):.1%}   (1h): {break_even_hit_rate(p, '1h'):.1%}\n")

    shape = AgentLoopShape()
    lat = LatencyModel()
    print(f"2) {shape.turns}-turn append-only agent loop")
    for mode in ("no_cache", "append_only", "mutated_prefix"):
        us = agent_loop_usage(shape, mode)
        s = summarize(us)
        print(
            f"   {mode:<15} input={s.total_input:>9,} tok  cost={_fmt(cost(s, p)):>8}  "
            f"last-turn TTFT={lat.ttft(us[-1]):.2f}s (illustrative latency model)"
        )


if __name__ == "__main__":
    main()
