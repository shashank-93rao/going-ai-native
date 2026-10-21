"""Governor unit tests: every breaker trips, with the right typed exit code."""

import pytest

from governor import ExitCode, Governor, GovernorTripped, Limits, Prices, call_signature


def trips(gov, fn=None):
    with pytest.raises(GovernorTripped) as e:
        if fn:
            fn()
        gov.check()
    return e.value


def test_iteration_cap_is_fail_not_success():
    g = Governor(Limits(max_iterations=2))
    g.tick(); g.tick()
    with pytest.raises(GovernorTripped) as e:
        g.tick()
    assert e.value.code is ExitCode.FAIL


def test_identical_tool_calls_trip_repetition():
    g = Governor(Limits(max_repeats=3))
    for _ in range(2):
        g.record_tool_call("read_file", {"path": "a.py"})
    g.check()  # two is fine
    t = trips(g, lambda: g.record_tool_call("read_file", {"path": "a.py"}))
    assert t.code is ExitCode.STALLED and "repetition" in t.reason


def test_arg_order_does_not_hide_a_repeat():
    assert call_signature("t", {"a": 1, "b": 2}) == call_signature("t", {"b": 2, "a": 1})


def test_oscillation_inside_window_trips():
    g = Governor(Limits(max_repeats=3, repeat_window=6))
    seq = ["a", "b", "a", "b", "a"]
    for p in seq[:-1]:
        g.record_tool_call("read_file", {"path": p})
    g.check()
    t = trips(g, lambda: g.record_tool_call("read_file", {"path": seq[-1]}))
    assert t.code is ExitCode.STALLED


def test_spread_out_repeats_outside_window_are_allowed():
    g = Governor(Limits(max_repeats=3, repeat_window=4))
    for i in range(12):  # 'run_tests' every 4th call is a normal rhythm, not a loop
        g.record_tool_call("run_tests" if i % 4 == 0 else "edit", {"i": i} if i % 4 else {})
    g.check()


def test_consecutive_errors_break_and_success_resets():
    g = Governor(Limits(max_consecutive_errors=3))
    g.record_outcome(False); g.record_outcome(False); g.record_outcome(True)
    g.record_outcome(False); g.record_outcome(False)
    g.check()
    t = trips(g, lambda: g.record_outcome(False))
    assert t.code is ExitCode.STALLED and "consecutive errors" in t.reason


def test_no_progress_on_metric_trips_after_patience():
    g = Governor(Limits(stall_patience=3))
    for v in [0.2, 0.4, 0.4, 0.3]:  # improved twice, then flat, then worse
        g.record_metric(v)
    g.check()
    t = trips(g, lambda: g.record_metric(0.4))  # equal to best is not progress
    assert t.code is ExitCode.STALLED and "no progress" in t.reason


def test_metric_none_is_ignored():
    g = Governor(Limits(stall_patience=1))
    for _ in range(5):
        g.record_metric(None)
    g.check()


def test_dollar_budget():
    g = Governor(Limits(max_input_tokens=None, max_output_tokens=None, max_cost_usd=1.0),
                 prices=Prices(input_per_mtok=3.0, output_per_mtok=15.0))
    g.record_usage(200_000, 20_000)  # $0.60 + $0.30 = $0.90
    g.check()
    t = trips(g, lambda: g.record_usage(30_000, 1_000))  # +$0.105 => $1.005
    assert t.code is ExitCode.BUDGET and "cost" in t.reason


def test_token_budget():
    g = Governor(Limits(max_input_tokens=1000, max_cost_usd=None))
    t = trips(g, lambda: g.record_usage(1001, 0))
    assert t.code is ExitCode.BUDGET and "input tokens" in t.reason


def test_wall_clock_with_injected_clock():
    now = [0.0]
    g = Governor(Limits(max_wall_seconds=60), clock=lambda: now[0])
    now[0] = 59
    g.check()
    now[0] = 61
    assert trips(g).code is ExitCode.BUDGET


def test_stop_file_wins(tmp_path):
    stop = tmp_path / "STOP"
    g = Governor(Limits(stop_file=stop))
    g.check()
    stop.write_text("")
    assert trips(g).code is ExitCode.STOPPED


def test_tripped_governor_never_ticks_again():
    g = Governor(Limits(max_consecutive_errors=1))
    g.record_outcome(False)
    with pytest.raises(GovernorTripped):
        g.tick()
    assert g.iterations == 0
