"""Cost-aware model routing with a cascade, retries with backoff, fallback, deadline and budget guard.

    request -> budget admission -> pick tier (cheap | strong)
            -> call with retries (full-jitter backoff, honours retry-after, respects deadline)
            -> cheap answer fails `accept`?  escalate to strong (cascade)
            -> primary exhausted?            fall back to the fallback model
            -> reconcile actual cost against the reservation

Distributed-systems framing: the budget is admission control, retries are bounded
and jittered to avoid synchronized retry storms, and the deadline is propagated so a
retry never starts when it cannot finish.

If you use the real Anthropic SDK underneath, set its own `max_retries=0` (the SDK
retries twice by default) or the two retry layers multiply.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ainative_kit import LLMClient, Response, Tracer
from pricing import PRICES, cost_usd

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}
RETRYABLE_NAMES = {"APITimeoutError", "APIConnectionError", "TimeoutError", "ConnectionError"}


class APIStatus(Exception):
    """Stand-in for SDK status errors in fakes. Real anthropic errors expose `.status_code` too."""

    def __init__(self, status_code: int, message: str = "", retry_after: float | None = None):
        super().__init__(f"{status_code} {message}".strip())
        self.status_code, self.retry_after = status_code, retry_after


class BudgetExceeded(Exception):
    pass


class AllRoutesFailed(Exception):
    pass


def is_retryable(exc: BaseException) -> bool:
    code = getattr(exc, "status_code", None)
    if code is not None:
        return code in RETRYABLE_STATUS
    return type(exc).__name__ in RETRYABLE_NAMES


def retry_after_of(exc: BaseException) -> float | None:
    ra = getattr(exc, "retry_after", None)
    if ra is not None:
        return float(ra)
    resp = getattr(exc, "response", None)  # anthropic.APIStatusError carries the httpx response
    hdr = getattr(getattr(resp, "headers", None), "get", lambda *_: None)("retry-after")
    try:
        return float(hdr) if hdr is not None else None
    except ValueError:
        return None


def estimate_tokens(messages: list[dict[str, Any]], system: str | None) -> int:
    """~4 chars per token. Good enough for admission control; use the token-counting
    endpoint when the estimate matters (e.g. near a context limit)."""
    chars = len(system or "") + sum(len(str(m.get("content", ""))) for m in messages)
    return chars // 4 + 1


@dataclass
class Budget:
    """Spend guard over a window. Reserve the worst case before a call; reconcile after."""

    limit_usd: float
    spent_usd: float = 0.0
    reserved_usd: float = 0.0

    def remaining(self) -> float:
        return self.limit_usd - self.spent_usd - self.reserved_usd

    def reserve(self, usd: float) -> bool:
        if usd > self.remaining():
            return False
        self.reserved_usd += usd
        return True

    def settle(self, reserved: float, actual: float) -> None:
        self.reserved_usd -= reserved
        self.spent_usd += actual


@dataclass
class Backoff:
    base_s: float = 0.5
    cap_s: float = 20.0
    max_attempts: int = 4  # total attempts per model, including the first

    def delay(self, attempt: int, rng: random.Random, retry_after: float | None = None) -> float:
        """Full jitter (AWS Architecture Blog): uniform(0, min(cap, base * 2**attempt))."""
        d = rng.uniform(0, min(self.cap_s, self.base_s * (2 ** attempt)))
        return max(d, retry_after or 0.0)


@dataclass
class RouteResult:
    response: Response
    model: str
    cost_usd: float
    attempts: list[dict[str, Any]] = field(default_factory=list)
    escalated: bool = False
    fell_back: bool = False
    degraded: bool = False


class Router:
    def __init__(self, client: LLMClient, *, cheap: str = "claude-haiku-5-5", strong: str = "claude-sonnet-5-5",
                 fallback: str | None = "claude-opus-5-5", classify: Callable[[list[dict[str, Any]]], str] | None = None,
                 accept: Callable[[Response], bool] | None = None, budget: Budget | None = None,
                 backoff: Backoff | None = None, deadline_s: float = 30.0, tracer: Tracer | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 seed: int | None = None):
        self.client, self.cheap, self.strong, self.fallback = client, cheap, strong, fallback
        self.classify = classify or (lambda msgs: "cheap")
        self.accept = accept or (lambda r: r.stop_reason != "max_tokens" and bool(r.text.strip()))
        self.budget, self.backoff = budget, backoff or Backoff()
        self.deadline_s, self.tracer = deadline_s, tracer or Tracer()
        self.sleep, self.clock, self.rng = sleep, clock, random.Random(seed)

    def _worst_case(self, model: str, in_tokens: int, max_tokens: int) -> float:
        return cost_usd(model, input_tokens=in_tokens, output_tokens=max_tokens)

    def _call(self, model: str, messages, system, max_tokens, t0: float, log: list[dict[str, Any]]) -> Response:
        """Call one model with bounded, jittered retries. Raises the last error when exhausted."""
        last: BaseException | None = None
        for attempt in range(self.backoff.max_attempts):
            with self.tracer.span("llm_call", model=model, attempt=attempt) as sp:
                try:
                    resp = self.client.complete(messages, system=system, model=model, max_tokens=max_tokens)
                    sp.attrs.update(input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                                    stop_reason=resp.stop_reason)
                    log.append({"model": model, "attempt": attempt, "ok": True})
                    return resp
                except Exception as e:  # noqa: BLE001 - classified below
                    last = e
                    sp.attrs["retryable"] = retryable = is_retryable(e)
                    log.append({"model": model, "attempt": attempt, "ok": False, "error": str(e)})
                    if not retryable:
                        raise
            if attempt + 1 == self.backoff.max_attempts:
                break
            wait = self.backoff.delay(attempt, self.rng, retry_after_of(last))
            if self.clock() - t0 + wait >= self.deadline_s:
                log.append({"model": model, "gave_up": "deadline"})
                break
            self.sleep(wait)
        assert last is not None
        raise last

    def run(self, messages: list[dict[str, Any]], *, system: str | None = None, max_tokens: int = 1024) -> RouteResult:
        t0, log = self.clock(), []
        in_tok = estimate_tokens(messages, system)
        tier = self.classify(messages)
        model = self.strong if tier == "strong" else self.cheap
        degraded = False

        reserved = 0.0
        if self.budget is not None:
            # Reserve the worst case of the path we might take (cheap then strong on escalation).
            plan = [model] + ([self.strong] if model == self.cheap else [])
            reserved = sum(self._worst_case(m, in_tok, max_tokens) for m in plan)
            if not self.budget.reserve(reserved):
                # Degrade before refusing: try the cheap model alone.
                reserved = self._worst_case(self.cheap, in_tok, max_tokens)
                if model == self.cheap or not self.budget.reserve(reserved):
                    raise BudgetExceeded(f"remaining ${self.budget.remaining():.4f} < worst case ${reserved:.4f}")
                model, degraded = self.cheap, True

        result: RouteResult | None = None
        sunk = 0.0  # cost of attempts whose answer we threw away (a rejected cheap answer)
        with self.tracer.span("route", tier=tier, chosen=model, degraded=degraded) as root:
            try:
                resp = self._call(model, messages, system, max_tokens, t0, log)
                result = RouteResult(resp, model, 0.0, log, degraded=degraded)
                if model == self.cheap and not degraded and not self.accept(resp):
                    sunk += self._actual(model, resp)
                    resp2 = self._call(self.strong, messages, system, max_tokens, t0, log)
                    result = RouteResult(resp2, self.strong, 0.0, log, escalated=True)
            except Exception as e:  # noqa: BLE001
                # Fallback only for transient failures, within the deadline, and never in
                # degraded (over-budget) mode, since the fallback is usually the expensive model.
                if (self.fallback is None or degraded or not is_retryable(e)
                        or self.clock() - t0 >= self.deadline_s):
                    if self.budget is not None:
                        self.budget.settle(reserved, sunk)
                    raise AllRoutesFailed(str(e)) from e
                try:
                    fb = self._call(self.fallback, messages, system, max_tokens, t0, log)
                except Exception as e2:  # noqa: BLE001
                    if self.budget is not None:
                        self.budget.settle(reserved, sunk)
                    raise AllRoutesFailed(f"primary: {e}; fallback: {e2}") from e2
                result = RouteResult(fb, self.fallback, 0.0, log, fell_back=True)
            result.cost_usd = sunk + self._actual(result.model, result.response)
            root.attrs.update(final_model=result.model, escalated=result.escalated, fell_back=result.fell_back,
                              cost_usd=round(result.cost_usd, 6), attempts=len(log))
        if self.budget is not None:
            self.budget.settle(reserved, result.cost_usd)
        return result

    @staticmethod
    def _actual(model: str, r: Response) -> float:
        if model not in PRICES:
            return 0.0
        return cost_usd(model, input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens,
                        cache_read_tokens=getattr(r.usage, "cache_read_input_tokens", 0),
                        cache_write_tokens=getattr(r.usage, "cache_creation_input_tokens", 0))


def length_classifier(threshold_chars: int = 4000) -> Callable[[list[dict[str, Any]]], str]:
    """Toy difficulty classifier. In production, calibrate the routing rule against labels:
    route a held-out set both ways and check the cheap tier's pass rate per bucket."""
    def classify(messages: list[dict[str, Any]]) -> str:
        return "strong" if sum(len(str(m.get("content", ""))) for m in messages) > threshold_chars else "cheap"
    return classify


if __name__ == "__main__":
    from ainative_kit import FakeClient, Usage, get_client, text

    calls = {"n": 0}

    def flaky(messages, kw):  # Haiku answers badly once; Sonnet is overloaded once, then fine.
        calls["n"] += 1
        if kw["model"] == "claude-haiku-5-5":
            return text("", usage=Usage(900, 0), stop_reason="max_tokens")
        if calls["n"] == 2:
            raise APIStatus(529, "overloaded_error")
        return text('{"verdict": "retry storm from consumer group rebalance"}', usage=Usage(900, 140))

    router = Router(get_client(fake=FakeClient(flaky)), budget=Budget(limit_usd=0.50), sleep=lambda s: None, seed=1)
    res = router.run([{"role": "user", "content": "Why did consumer lag spike at 02:10?"}], max_tokens=400)
    print(res.model, f"${res.cost_usd:.5f}", "escalated" if res.escalated else "", res.attempts)
    print(f"budget spent ${router.budget.spent_usd:.5f}, reserved ${router.budget.reserved_usd:.5f}")
