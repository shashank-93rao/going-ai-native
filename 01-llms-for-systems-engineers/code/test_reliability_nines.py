import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from reliability_nines import (
    chain_success,
    expected_failures,
    max_steps,
    nines,
    pass_at_k,
    pass_hat_k,
    required_step_reliability,
    simulate_chain,
    with_verified_retries,
)

probs = st.floats(0.01, 0.999)


def test_chain_success_examples():
    assert chain_success(0.99, 20) == pytest.approx(0.8179, abs=1e-4)
    assert chain_success(0.9, 0) == 1.0


def test_nines():
    assert nines(0.9) == pytest.approx(1)
    assert nines(0.999) == pytest.approx(3)
    assert nines(1.0) == math.inf


@given(st.floats(0.5, 0.9999), st.integers(1, 200))
def test_required_reliability_round_trips(target, steps):
    assert chain_success(required_step_reliability(target, steps), steps) == pytest.approx(target, rel=1e-9)


@given(probs, st.floats(0.01, 0.99))
def test_max_steps_is_tight(p, target):
    n = max_steps(p, target)
    assert chain_success(p, n) >= target - 1e-12
    assert chain_success(p, n + 1) < target + 1e-12


def test_monte_carlo_agrees_with_formula():
    assert simulate_chain(0.95, 10, trials=50_000, seed=1) == pytest.approx(chain_success(0.95, 10), abs=0.01)


def test_retries_with_perfect_verifier_equal_pass_at_k():
    assert with_verified_retries(0.8, 1.0, 3) == pytest.approx(pass_at_k(0.8, 3))


def test_retries_with_blind_verifier_do_nothing():
    assert with_verified_retries(0.8, 0.0, 5) == pytest.approx(0.8)


def test_retries_ceiling_is_set_by_undetected_failures():
    # Unlimited retries converge to p / (1 - (1-p)*detect): undetected failures cap it.
    ceiling = 0.95 / (1 - 0.05 * 0.8)
    assert with_verified_retries(0.95, 0.8, 50) == pytest.approx(ceiling, abs=1e-6)


@given(probs, st.integers(1, 20))
def test_pass_at_k_ge_p_ge_pass_hat_k(p, k):
    assert pass_at_k(p, k) >= p - 1e-12 >= pass_hat_k(p, k) - 2e-12


def test_expected_failures():
    assert expected_failures(0.999, 10_000) == pytest.approx(10)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_rejects_bad_probabilities(bad):
    with pytest.raises(ValueError):
        chain_success(bad, 3)
