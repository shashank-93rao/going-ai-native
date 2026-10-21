# 04: Cost and latency engineering

## The idea
An LLM call is a paid RPC whose price and latency depend on what you send. The bill is set by four token counters (uncached input, cache writes, cache reads, output), each at a different price, multiplied by the model's rate card. Latency is time-to-first-token plus output length times per-token time, plus whatever retries and fallbacks you add. Every lever in this file moves one of those terms:

| Lever | Moves | Typical effect |
|---|---|---|
| **Model routing** (cheap vs strong, cascades) | price per token | Largest single lever, but costs quality unless calibrated |
| **Prompt caching** | cost and TTFT of the static prefix | Large on long, stable prefixes. Zero if the prefix keeps changing |
| **Batching** | price, at the cost of latency | 50% off for work that can wait |
| **Output length** (`max_tokens`, effort, verbosity) | the dominant cost on short-prompt features | Output tokens cost 5x input on current Claude models |
| **Budgets, rate limits, backoff, timeouts, fallbacks** | the tails | Protect p99 and the monthly bill from incidents |

## Why it matters
Current list prices, from [Anthropic's pricing page](https://platform.claude.com/docs/en/about-claude/pricing), checked 2026-10-19, in USD per million tokens:

| Model | Input | 5-min cache write | Cache read | Output | Batch in / out |
|---|---|---|---|---|---|
| `claude-opus-5-5` | 4.00 | 5.00 | 0.20 | 20.00 | 2 / 10 |
| `claude-sonnet-5-5` | 2.00 | 2.50 | 0.10 | 10.00 | 1 / 5 |
| `claude-haiku-5-5` (≤100k prompt) | 0.10 | 0.125 | 0.01 | 0.50 | 0.05 / 0.25 |

Cache writes cost 1.25x base input (2x for the 1-hour TTL). Cache reads cost 0.1x base on most models and **0.05x on Opus 5.5 and Sonnet 5.5**. Batch is 50% off, and these multipliers stack ([prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). On Sonnet 5.5, a 6,000-token prefix therefore costs $0.012 uncached and $0.0006 as a cache read: a factor of 20. Routing the same request from Sonnet 5.5 to Haiku 5.5 is another factor of 20.

Anthropic's own hill-climbing write-up shows what these levers do together. A support bot on Opus 4.8 at high effort scored 74.4% at 4.6¢ per ticket. A prompt audit, a cheaper model at low effort and added routing rules took it to 98.9% at about 1¢ on the 30 training tickets. On the 14 held-out tickets it reached 90.5%, against 78.6% originally, at about a fifth of the cost ([Anthropic, "Automating eval design and hillclimbing with Claude", 2026-09-28](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Note n = 14 on the held-out set. The direction is convincing. The exact figure has wide error bars.

## How it works

### Model routing and cascades
Routing comes in three forms, in increasing order of quality-safety:
1. **Static by feature**: classification goes to Haiku, drafting to Sonnet. Decide it offline with the cost frontier from [Module 12](../12-hill-climbing/README.md).
2. **Classifier routing**: a cheap rule or model predicts difficulty and picks the tier. You must **calibrate the router against labels**, meaning you run a held-out set through both tiers and measure the cheap tier's pass rate *per router bucket*. Without that step the router is an untested guess.
3. **Cascade**: try cheap, run an acceptance check (schema valid, a code oracle, a confidence field you verified correlates with correctness), and escalate to strong on rejection. You pay for the cheap try on every escalated request, so a cascade wins only when `p_accept · (strong − cheap) > cheap`. In practice that means the acceptance check must be strict *and* pass most traffic.

### Prompt caching as an engineered property
The cache is a **prefix** cache. The order is `tools → system → messages`, and a change at one level invalidates that level and everything after it. Changing tool definitions invalidates all of it. Adding images, or changing `tool_choice`, invalidates the system and message levels. Thinking and effort changes always invalidate message blocks. Below the per-model minimum (512 tokens on the 5.x models) nothing is cached, *and no error is returned*. The default TTL is 5 minutes, refreshed on each read. All of this is in the [prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

That gives you design rules:
- Put stable content first and volatile content last. Never interpolate timestamps, request IDs or user names into the system prompt. Pass them in the final user message.
- Serialize tool lists deterministically. OpenAI describes an early Codex bug in which MCP tools were listed in an inconsistent order, causing cache misses ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)).
- Make conversation history append-only. Editing earlier turns invalidates every later cache entry. Anthropic's April 2026 postmortem traced faster-than-expected usage-limit drain to a bug that dropped thinking blocks every turn and caused cache misses ([Anthropic, 2026-04-23](https://www.anthropic.com/engineering/april-23-postmortem)).
- **Put an SLO on the cache hit rate.** Define it as `cache_read / (cache_read + cache_write)` over the tokens that were eligible for caching. Do not use reads ÷ all input, because that ratio is capped by your prompt's shape. A drop means something changed the prefix. `pricing.cache_hit_rate()` implements the right one. *Course synthesis:* hit rate belongs beside latency and error rate as a first-class SLO, because it is the one cost metric that changes discontinuously after a deploy.

### Batching
The Message Batches API is 50% off and asynchronous. Use it for anything with a deadline in hours: nightly backfills, offline evals, re-judging the anchor set. It also stacks with caching. Anthropic's errors docs recommend batches or streaming for requests over about 10 minutes, because idle connections get dropped ([API errors docs](https://platform.claude.com/docs/en/api/errors)).

### Rate limits, retries, backoff
From the [API errors docs](https://platform.claude.com/docs/en/api/errors):
- `429 rate_limit_error` usually carries `retry-after`, which you should honour. **One exception: a usage-tier spend-cap 429 has no `retry-after` and keeps failing until access resumes.** Retrying it is pointless, so fall back or fail.
- `529 overloaded_error` means the API is overloaded across all users. A sharp increase in your own traffic can also trigger 429s from acceleration limits, so ramp up gradually.
- `500 api_error` and `504 timeout_error` can be retried with exponential backoff.
- `400`, `401`, `403`, `404` and `413` should never be retried.
- **The official SDK already retries twice by default** with exponential backoff, honouring `retry-after`. If you add your own retry layer, set `max_retries=0` on the SDK. Two stacked layers of 3 attempts each produce 9 attempts, which is a retry storm you built yourself.

Use full-jitter backoff, `sleep = uniform(0, min(cap, base · 2^attempt))`, from [Marc Brooker's AWS analysis](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/), and take `max(jitter, retry_after)`.

### Timeouts, deadlines and fallbacks
- **Propagate a deadline**, not a per-attempt timeout. Before each retry, check `elapsed + backoff < deadline`. Don't start an attempt that cannot finish.
- **Stream** anything user-facing. TTFT is what users feel, and streaming lets you enforce a time-to-first-token SLO separately from total duration.
- **Fallback** to a different model, or a different region or provider, only on *transient* errors. A 400 on the primary will be a 400 on the fallback too. Watch fallback cost: falling back from Sonnet to Opus doubles the price, which is fine during an incident and a budget problem if it becomes the steady state. Alert on `fell_back` rate.

### Budgets as admission control
A per-tenant or per-feature budget works like a token bucket denominated in dollars. **Reserve the worst case** (estimated input plus `max_tokens` at the output price) before the call, **settle** the actual cost after it, and when a reservation doesn't fit, **degrade** (cheap tier only, no escalation, no expensive fallback) before you **refuse**. This is the same idea as the budget-as-pause pattern in Anthropic's scheduled-agent guidance (["Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/)) and the loop governors in [Module 07](../07-loops/README.md).

## Worked example
**Bad version**, as found in the wild:

```python
for attempt in range(5):                       # on top of the SDK's own 2 retries
    try:
        return client.messages.create(model="claude-opus-5-5", max_tokens=8192,
            system=f"Now: {datetime.utcnow()}\n" + RULES,   # cache-busting prefix
            messages=msgs)
    except Exception:
        time.sleep(2 ** attempt)                # no jitter, retries 400s too, no deadline
```

Each request can make up to 15 HTTP attempts. Synchronized sleeps hammer the API in waves after an overload. The prefix is never cached. Every request is priced on Opus, and the worst case per call is 8,192 output tokens at $20/MTok.

**Good version.** `code/router.py` composes the pieces:

```python
router = Router(client, cheap="claude-haiku-5-5", strong="claude-sonnet-5-5", fallback="claude-opus-5-5",
                classify=length_classifier(4000),              # calibrate this against labels
                accept=lambda r: r.stop_reason != "max_tokens" and is_valid_json(r.text),
                budget=Budget(limit_usd=50.0), backoff=Backoff(base_s=0.5, cap_s=20, max_attempts=4),
                deadline_s=30.0)
res = router.run(messages, system=RULES, max_tokens=600)
```

Running `python router.py` drives it with a fake in which Haiku truncates and Sonnet is overloaded once. This is the real output:

```text
claude-sonnet-5-5 $0.00329 escalated [{'model': 'claude-haiku-5-5', 'attempt': 0, 'ok': True},
  {'model': 'claude-sonnet-5-5', 'attempt': 0, 'ok': False, 'error': '529 overloaded_error'},
  {'model': 'claude-sonnet-5-5', 'attempt': 1, 'ok': True}]
budget spent $0.00329, reserved $0.00000
```

The Haiku answer was rejected because it stopped on `max_tokens` with empty text. The router escalated, absorbed one 529 with a jittered retry, and charged both attempts to the budget, including the cheap one that was thrown away. The reservation then settled to zero. `test_router.py` covers the other branches: `retry-after` is honoured, fallback happens only after retries run out, a 400 fails fast with exactly one call, the deadline stops retries, and the budget degrades and then refuses.

## Pitfalls
- **Measuring cost from `input_tokens` alone.** Anthropic's `input_tokens` excludes cache reads and writes, so you will undercount badly on a well-cached feature. Sum all four counters, as `pricing.cost_usd()` does.
- **A cascade with a weak acceptance check.** If the check accepts bad cheap answers, you have quietly downgraded quality. *Detect:* judge a sample of *accepted* cheap answers and compare with the strong tier on the same inputs.
- **Cache-busting through "harmless" edits:** a date line, a shuffled few-shot order, a per-tenant greeting at the top. *Detect:* the hit-rate SLO, and the distinct-prefix-hash count from [01](01-tracing-for-llm-systems.md).
- **Prefixes below the cache minimum.** Nothing is cached and nothing errors. *Detect:* `cache_read + cache_write == 0` on every request.
- **Retrying spend-cap 429s.** They don't recover. *Detect:* a 429 with no `retry-after` header. Fail over or stop.
- **Fallback as steady state.** If the fallback rate stays above about 1% for a day, either the primary is unhealthy or your retry budget is too small, and you are paying the fallback's price all the time.
- **Unbounded `max_tokens`.** This is the worst-case reservation, and on short-prompt features it is most of the bill. Set it from the p99 of observed output length plus headroom.

## In your day job
- Pull a week of usage and compute cost per request from all four counters, split by feature. Most teams find one feature dominating.
- Add the cache hit-rate SLO with a ticket at 85% and a page on a sudden drop. Then hunt down every interpolated value in your system prompts.
- Set `max_retries=0` on the SDK wherever you have your own retry loop, and add jitter and a deadline.
- Move every offline or nightly LLM job to the Batch API.
