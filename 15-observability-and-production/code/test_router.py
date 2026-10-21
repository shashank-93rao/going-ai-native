import pytest
from ainative_kit import FakeClient, Usage, text
from router import (AllRoutesFailed, APIStatus, Backoff, Budget, BudgetExceeded, Router, is_retryable,
                    length_classifier)

MSG = [{"role": "user", "content": "summarize this alert"}]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make(script, **kw):
    clock = Clock()
    r = Router(FakeClient(script), sleep=clock.sleep, clock=clock, seed=0, **kw)
    return r, clock


def ok(t="fine", n_in=500, n_out=100):
    return text(t, usage=Usage(n_in, n_out))


def test_cheap_path_when_accepted():
    r, _ = make([ok()])
    res = r.run(MSG)
    assert res.model == "claude-haiku-5-5" and not res.escalated and res.cost_usd > 0


def test_cascade_escalates_on_reject_and_counts_both_costs():
    r, _ = make([text("", usage=Usage(500, 0), stop_reason="max_tokens"), ok("good", 500, 100)])
    res = r.run(MSG)
    assert res.escalated and res.model == "claude-sonnet-5-5"
    expected = (500 * 0.10 + 0) / 1e6 + (500 * 2.0 + 100 * 10.0) / 1e6
    assert res.cost_usd == pytest.approx(expected)


def test_retries_transient_then_succeeds_and_honours_retry_after():
    def script(msgs, kw, it=iter([APIStatus(429, "rate_limit_error", retry_after=7.0), ok()])):
        nxt = next(it)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    r, clock = make(script, classify=lambda m: "strong")
    res = r.run(MSG)
    assert res.model == "claude-sonnet-5-5" and len(res.attempts) == 2
    assert clock.t >= 7.0


def _raiser(errors_by_model):
    def script(msgs, kw):
        e = errors_by_model.get(kw["model"])
        if e:
            raise e
        return ok()
    return script


def test_falls_back_after_retries_exhausted():
    r, _ = make(_raiser({"claude-sonnet-5-5": APIStatus(529, "overloaded_error")}), classify=lambda m: "strong",
                backoff=Backoff(base_s=0.1, max_attempts=3))
    res = r.run(MSG)
    assert res.fell_back and res.model == "claude-opus-5-5"
    assert sum(1 for a in res.attempts if a["model"] == "claude-sonnet-5-5") == 3


def test_non_retryable_fails_fast_without_fallback():
    r, _ = make(_raiser({"claude-haiku-5-5": APIStatus(400, "invalid_request_error")}))
    with pytest.raises(AllRoutesFailed):
        r.run(MSG)
    assert len(r.client.calls) == 1


def test_deadline_stops_retries():
    r, clock = make(_raiser({"claude-haiku-5-5": APIStatus(503), "claude-opus-5-5": APIStatus(503)}),
                    deadline_s=2.0, backoff=Backoff(base_s=5.0, max_attempts=5))
    with pytest.raises(AllRoutesFailed):
        r.run(MSG)
    assert clock.t < 2.0


def test_budget_degrades_then_refuses():
    big = [{"role": "user", "content": "x" * 40_000}]  # ~10k tokens
    r, _ = make([ok(n_in=10_000)], classify=lambda m: "strong", budget=Budget(limit_usd=0.01))
    res = r.run(big, max_tokens=1000)
    assert res.degraded and res.model == "claude-haiku-5-5"
    assert r.budget.reserved_usd == pytest.approx(0) and r.budget.spent_usd > 0
    r2, _ = make([ok()], budget=Budget(limit_usd=0.000001))
    with pytest.raises(BudgetExceeded):
        r2.run(big, max_tokens=1000)


def test_classification_helpers():
    assert is_retryable(APIStatus(529)) and is_retryable(TimeoutError()) and not is_retryable(APIStatus(401))
    c = length_classifier(10)
    assert c([{"content": "short"}]) == "cheap" and c([{"content": "x" * 50}]) == "strong"


def test_full_jitter_bounds():
    import random
    b, rng = Backoff(base_s=1, cap_s=8), random.Random(1)
    ds = [b.delay(5, rng) for _ in range(200)]
    assert max(ds) <= 8 and min(ds) >= 0 and len({round(d, 3) for d in ds}) > 100
    assert b.delay(0, rng, retry_after=3.0) >= 3.0
