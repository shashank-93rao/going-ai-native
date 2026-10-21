import pytest
from hypothesis import given, settings, strategies as st

from context_budget import (
    BudgetError, Section, assemble, common_prefix_tokens, estimate_tokens, triage_sections,
)

LOGS = "\n".join(f"03:{i:02d} WARN Revoking previously assigned partitions" for i in range(80))
HISTORY = "INC-4412: max.poll.interval.ms too low for batch size.\n" * 6


def test_everything_fits_with_large_budget():
    a = assemble(triage_sections("alert", LOGS, HISTORY), budget=10_000)
    assert a.dropped == [] and a.truncated == []
    assert a.tokens <= 10_000


def test_required_sections_always_included_and_low_priority_dropped_first():
    a = assemble(triage_sections("alert", LOGS, HISTORY), budget=900, reserve_output=200)
    assert {"role", "tool_contract", "alert"} <= set(a.included)
    # style_guide (priority 90) must go before prior_incidents (30) or logs (10).
    assert "style_guide" in a.dropped
    assert a.tokens <= 900 - 200


def test_required_overflow_fails_loudly():
    with pytest.raises(BudgetError):
        assemble([Section("spec", "x" * 4000, required=True)], budget=500)


def test_truncation_keeps_the_tail_of_logs():
    logs = "\n".join(f"line {i}" for i in range(500))
    secs = [Section("q", "why?", required=True), Section("logs", logs, truncatable=True, keep="tail")]
    a = assemble(secs, budget=200)
    assert a.truncated == ["logs"]
    assert "line 499" in a.prompt and "line 0\n" not in a.prompt
    assert a.tokens <= 200


def test_stable_sections_form_identical_prefix_across_calls():
    a1 = assemble(triage_sections("alert A", LOGS, HISTORY), budget=2000)
    a2 = assemble(triage_sections("a totally different alert", LOGS, HISTORY), budget=2000)
    assert a1.prefix == a2.prefix
    assert a1.prompt.startswith(a1.prefix)
    assert common_prefix_tokens(a1.prompt, a2.prompt) >= estimate_tokens(a1.prefix) - 1


def test_layout_is_stable_first_even_if_declared_later():
    secs = [Section("volatile", "now=03:14", required=True), Section("system", "rules", required=True, stable=True)]
    a = assemble(secs, budget=1000)
    assert a.prompt.index('name="system"') < a.prompt.index('name="volatile"')


def test_optional_stable_section_is_rejected():
    with pytest.raises(ValueError, match="stable but optional"):
        assemble([Section("tools", "defs", stable=True)], budget=1000)


@settings(max_examples=60, deadline=None)
@given(
    sizes=st.lists(st.integers(min_value=0, max_value=3000), min_size=1, max_size=8),
    prios=st.lists(st.integers(min_value=0, max_value=100), min_size=8, max_size=8),
    budget=st.integers(min_value=100, max_value=4000),
)
def test_never_exceeds_budget(sizes, prios, budget):
    secs = [Section("q", "question", required=True)]
    secs += [Section(f"s{i}", "y" * n, priority=prios[i], truncatable=i % 2 == 0) for i, n in enumerate(sizes)]
    a = assemble(secs, budget=budget)
    assert a.tokens <= budget
    assert set(a.included) | set(a.dropped) == {s.name for s in secs}
