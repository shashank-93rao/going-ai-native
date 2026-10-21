import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from token_cost_model import (
    EXAMPLE_PRICES,
    AgentLoopShape,
    LatencyModel,
    Pricing,
    TokenUsage,
    agent_loop_usage,
    break_even_hit_rate,
    cost,
    estimate_tokens,
    expected_request_cost,
    summarize,
    uncached_request_cost,
)

P = Pricing(input_per_mtok=2.0, output_per_mtok=10.0, cache_read_mult=0.1)


def test_cost_matches_hand_calculation():
    # 1M uncached in ($2) + 1M written ($2.50) + 1M read ($0.20) + 1M out ($10)
    u = TokenUsage(1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert cost(u, P) == pytest.approx(2 + 2.5 + 0.2 + 10)
    assert cost(u, P, ttl="1h") == pytest.approx(2 + 4.0 + 0.2 + 10)


def test_output_tokens_dominate_per_token():
    assert cost(TokenUsage(output=1000), P) == pytest.approx(5 * cost(TokenUsage(uncached_input=1000), P))


def test_bad_ttl_rejected():
    with pytest.raises(ValueError):
        cost(TokenUsage(cache_write=1), P, ttl="10m")


def test_zero_hit_rate_is_worse_than_not_caching():
    # Paying the write premium with no reads is a pure surcharge.
    assert expected_request_cost(P, 20_000, 500, 300, 0.0) > uncached_request_cost(P, 20_000, 500, 300)


def test_full_hit_rate_prices_prefix_at_read_rate():
    got = expected_request_cost(P, 20_000, 0, 0, 1.0)
    assert got == pytest.approx(20_000 * 2.0 / 1e6 * 0.1)


def test_break_even_hit_rate_formula():
    h = break_even_hit_rate(P)
    assert h == pytest.approx(0.25 / 1.15)
    # At break-even, cached and uncached cost the same.
    assert expected_request_cost(P, 10_000, 0, 0, h) == pytest.approx(uncached_request_cost(P, 10_000, 0, 0))


@given(st.floats(0, 1), st.floats(0, 1))
def test_expected_cost_monotone_in_hit_rate(a, b):
    lo, hi = sorted((a, b))
    assert expected_request_cost(P, 5_000, 100, 100, hi) <= expected_request_cost(P, 5_000, 100, 100, lo) + 1e-12


def test_invalid_hit_rate():
    with pytest.raises(ValueError):
        expected_request_cost(P, 1, 1, 1, 1.5)


def test_agent_loop_total_input_is_quadratic_and_mode_independent():
    shape = AgentLoopShape(system_and_tools=1000, first_user=0, per_turn_tool_result=100, per_turn_output=0, turns=10)
    totals = {m: summarize(agent_loop_usage(shape, m)).total_input for m in ("no_cache", "append_only", "mutated_prefix")}
    # Same tokens are *sent* in every mode; only how they are billed changes.
    assert len(set(totals.values())) == 1
    # sum_{t=0..9} (1000 + 100 t) = 10_000 + 4_500
    assert totals["no_cache"] == 14_500


def test_append_only_reads_prior_prefix_and_writes_delta():
    shape = AgentLoopShape(system_and_tools=1000, first_user=0, per_turn_tool_result=100, per_turn_output=50, turns=3)
    us = agent_loop_usage(shape, "append_only")
    assert (us[0].cache_read, us[0].cache_write) == (0, 1000)
    assert (us[1].cache_read, us[1].cache_write) == (1000, 150)
    assert (us[2].cache_read, us[2].cache_write) == (1150, 150)


def test_cache_discipline_ordering():
    shape = AgentLoopShape()
    p = EXAMPLE_PRICES["claude-sonnet-5-5"]
    c = {m: cost(summarize(agent_loop_usage(shape, m)), p) for m in ("no_cache", "append_only", "mutated_prefix")}
    assert c["append_only"] < c["no_cache"] < c["mutated_prefix"]


def test_unknown_mode():
    with pytest.raises(ValueError):
        agent_loop_usage(AgentLoopShape(), "sometimes")


def test_latency_model_cache_reduces_ttft_not_decode():
    lat = LatencyModel(overhead_s=0, prefill_tps=1000, cached_prefill_speedup=10, decode_tps=50)
    cold = TokenUsage(uncached_input=10_000, output=100)
    warm = TokenUsage(cache_read=10_000, output=100)
    assert lat.ttft(cold) == pytest.approx(10.0)
    assert lat.ttft(warm) == pytest.approx(1.0)
    assert lat.total(cold) - lat.ttft(cold) == pytest.approx(lat.total(warm) - lat.ttft(warm)) == pytest.approx(2.0)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("x" * 35) == 10
    assert math.isclose(estimate_tokens("x" * 400, chars_per_token=4), 100)
