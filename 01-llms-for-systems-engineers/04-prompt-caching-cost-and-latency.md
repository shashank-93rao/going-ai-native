# 04: Prompt caching, cost, and latency

## The idea

An LLM call has two phases. **Prefill** processes every input token in parallel and builds the attention key/value state. **Decode** then generates output tokens one at a time, each one attending over everything before it. Prefill determines **time to first token (TTFT)**. Decode determines everything after that, at a roughly fixed number of output tokens per second.

**Prompt caching** keeps the prefill state for a prompt *prefix* on the provider's side. A later request with a byte-identical prefix skips recomputing it. You pay less for those tokens and wait less for the first output token. It is a prefix cache, not a content cache: one changed byte invalidates the cache from that byte onward.

Put the two together and you get the cost and latency model for the remote dependency:

```text
cost    = uncached_in * p_in + cache_writes * p_in * w + cache_reads * p_in * r + out * p_out
latency = overhead + prefill(uncached_in + cache_writes) + prefill_fast(cache_reads) + out / decode_rate
```

Here `w` is the cache write multiplier and `r` the cache read multiplier. `code/token_cost_model.py` implements exactly this.

## Why it matters

Agent loops resend the entire history on every turn, so the tokens sent grow quadratically with turn count. OpenAI's write-up of the Codex agent loop says caching is what makes "sampling the model ... linear rather than quadratic". They designed the prompt around it: static content first, and changes *appended* as new messages instead of edited in place. They also describe an early bug in which MCP tools were listed in an inconsistent order, which caused cache misses ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)).

Anthropic's own April 2026 Claude Code postmortem includes a bug that cleared thinking history "on every turn for the rest of the session" instead of once. Among other effects it caused cache misses ([Anthropic, April 23 postmortem](https://www.anthropic.com/engineering/april-23-postmortem)). Cache failures are silent. Requests keep succeeding, and the only symptom is the bill.

On latency, Anthropic's 2024 launch post reported TTFT for a 100,000-token "chat with a book" prompt dropping from 11.5 s to 2.4 s with caching, alongside a 90% cost reduction ([Anthropic, "Prompt caching with Claude"](https://claude.com/blog/prompt-caching)). Those numbers are from older models. The mechanism is the same today.

## How it works

### Prefix caching mechanics (Claude API, checked 2026-10-19)

From the [prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching):

- **Order.** The prompt renders as `tools`, then `system`, then `messages`. "Changes at each level invalidate that level and all subsequent levels." A changed tool definition invalidates everything. A changed system prompt invalidates system and messages.
- **Exact match.** "Cache hits require 100% identical prompt segments ... up to and including the block marked with cache control."
- **Breakpoints.** Mark blocks with `cache_control: {"type": "ephemeral"}`, up to 4 per request. Or set top-level automatic caching, which places a breakpoint on the last cacheable block and moves it forward as the conversation grows. Writes happen only at breakpoints.
- **Lookback.** On a read, the system checks at most 20 block positions back from each breakpoint for an entry an earlier request wrote. A turn that appends more than 20 blocks can push the previous entry out of reach. A run of consecutive tool-result blocks counts as one position.
- **TTL.** Five minutes by default, refreshed for free on every hit. A one-hour TTL costs more to write. The lifetime is measured from the *start* of the request, so a 4-minute generation leaves about 1 minute for the next request.
- **Minimum size.** 512 tokens on Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.x, and more on some older models (1,024 to 4,096). Shorter prefixes silently don't cache, with no error.
- **Scope.** Caches are isolated per workspace on the Claude API, and never shared across organizations.
- **Concurrency.** An entry becomes readable only after the first response that writes it *begins streaming*. N parallel requests with the same new prefix all pay full price. Send one, wait for its first token, then fan out.
- **Ground truth.** `usage.cache_creation_input_tokens` (written), `usage.cache_read_input_tokens` (read), and `usage.input_tokens` (uncached remainder). Total input is the sum of the three.

### Prices (parameters, checked 2026-10-19)

From [Anthropic's pricing page](https://platform.claude.com/docs/en/about-claude/pricing), USD per million tokens:

| Model | Input | 5-min write (1.25x) | 1-h write (2x) | Cache read | Output |
|---|---|---|---|---|---|
| Opus 5.5 | 4.00 | 5.00 | 8.00 | 0.20 (0.05x) | 20.00 |
| Sonnet 5.5 | 2.00 | 2.50 | 4.00 | 0.10 (0.05x) | 10.00 |
| Haiku 5.5 (prompts up to 100k) | 0.10 | 0.125 | 0.20 | 0.01 (0.1x) | 0.50 |
| Fable 5.1 | 10.00 | 12.50 | 20.00 | 0.25 (0.025x) | 50.00 |

The Batch API halves input and output prices, and the cache multipliers stack on top. On every model here, an output token costs **5x** an input token, and a cache read costs between 2.5% and 10% of an input token. Prices move, so `code/token_cost_model.py` takes them as parameters.

### Cost math you can do in your head

**Break-even hit rate.** If a fraction *h* of requests hit the cache, caching a prefix beats not caching it when *h·r + (1−h)·w < 1*, so *h > (w−1)/(w−r)*. For Sonnet 5.5 with the 5-minute TTL that is 0.25 / 1.20 ≈ **21%**. With the 1-hour TTL it is 1.0 / 1.95 ≈ **51%**. Below the break-even, caching is a surcharge. That happens when every request has a unique prefix, or when traffic gaps exceed the TTL.

**Output dominates per token, input dominates in agents.** A chat turn with 2k in and 1k out spends most of its money on output. A 30-turn agent loop that resends 50k to 90k tokens of history each turn spends most of its money on input, and that input is exactly what caching discounts.

**TTFT scales with uncached input. Total latency scales with output.** Caching shortens prefill. It does nothing for decode. If your p95 is dominated by a 2,000-token answer at 60 tokens per second (33 s of decode), the levers are shorter output, lower effort ([03](03-reasoning-models-and-effort.md)), streaming to the user, or a faster tier. Caching won't help.

### Append-only discipline

*Synthesis:* treat the prompt as an **append-only log**, as in event sourcing. The prefix is the committed log, and you only ever append. Anything that mutates history, reorders tools, or injects per-request bytes near the top rewrites the log and forces a full re-write of the cache.

| Silent invalidator | Fix |
|---|---|
| `datetime.now()`, request IDs or hostnames in the system prompt | Put volatile facts in the newest message, or in a mid-conversation `{"role": "system"}` message on models that support it |
| Tools built from a `set` or dict with unstable order | Sort tool definitions deterministically and freeze them for the session |
| Adding or removing a tool mid-session | Load all tools up front, or use tool search with deferred loading ([Module 05](../05-tools-mcp-skills-hooks/README.md)) |
| `json.dumps` without `sort_keys=True` in rendered context | Canonicalize serialization |
| Editing or summarizing earlier turns every turn | Compact rarely and deliberately, then append ([Module 03](../03-context-engineering/README.md)) |
| Switching model, effort, or speed mid-session | Caches are model-scoped, and effort and thinking settings are rendered into the prompt. Hold them fixed per session |

## Worked example: the agent loop that cost 8x what it should

A triage agent for your on-call rotation runs about 30 tool-calling turns per incident. The finance dashboard shows LLM spend 8x the estimate. Here is the prompt assembly:

**Bad version.**

```python
def build_request(history, tools_by_name):
    system = (
        f"You are the on-call triage agent for {CLUSTER}.\n"
        f"Current time: {datetime.now().isoformat()}\n"      # changes every request
        + RUNBOOK_TEXT                                        # 6k tokens, static
    )
    tools = [tools_by_name[n] for n in set(ENABLED_TOOLS)]    # set iteration order varies across processes
    return dict(system=system, tools=tools, messages=history,
                cache_control={"type": "ephemeral"})          # caching "on"
```

Caching is "on", but the timestamp sits in the system prompt, so every request invalidates system and messages. The tool list's order changes between worker processes, which invalidates everything. Every turn re-writes the whole conversation at 1.25x and reads nothing.

The calculator in `code/` models this as `mutated_prefix`. Here is its real output for the default 30-turn shape (8k static prefix, 2.5k tool result and 400 output tokens per turn), at Sonnet 5.5 example prices:

```text
$ python token_cost_model.py
...
2) 30-turn append-only agent loop
   no_cache        input=1,531,500 tok  cost=   $3.18  last-turn TTFT=9.71s (illustrative latency model)
   append_only     input=1,531,500 tok  cost= $0.4966  last-turn TTFT=1.59s (illustrative latency model)
   mutated_prefix  input=1,531,500 tok  cost=   $3.95  last-turn TTFT=9.71s (illustrative latency model)
```

All three modes send the same 1.53M input tokens. Only the billing differs. A broken cache (`mutated_prefix`) is **worse than no caching at all** ($3.95 versus $3.18), because you pay the write premium on every token. Fixed, the same loop costs $0.50, eight times less. The TTFT column comes from a placeholder latency model (`LatencyModel` defaults). Measure your own route before quoting latency numbers.

**Good version.**

```python
STATIC_SYSTEM = f"You are the on-call triage agent for {CLUSTER}.\n" + RUNBOOK_TEXT
TOOLS = sorted((tools_by_name[n] for n in ENABLED_TOOLS), key=lambda t: t["name"])  # frozen at startup

def build_request(history):
    return dict(
        system=[{"type": "text", "text": STATIC_SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],   # guaranteed read point on the static prefix
        tools=TOOLS,
        messages=history,                                    # append-only; time goes in the newest user turn
        cache_control={"type": "ephemeral"},                 # automatic breakpoint follows the growing tail
    )
```

Then make it checkable, because a later refactor will break it again:

```python
def test_second_turn_reads_cache(real_client):
    r1 = real_client.messages.create(**build_request(HISTORY_T1), model=MODEL, max_tokens=256)
    r2 = real_client.messages.create(**build_request(HISTORY_T1 + TURN_2), model=MODEL, max_tokens=256)
    assert r2.usage.cache_read_input_tokens >= r1.usage.cache_creation_input_tokens * 0.9
```

In production, monitor **cache read share** = `cache_read / (cache_read + cache_write + input)` per route as an SLI. A healthy agent loop sits close to 1 after the first turn. Alert on a step change, which is how you catch the next timestamp someone adds to the system prompt.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Caching "enabled" but never hitting | `cache_read_input_tokens == 0` on the second identical-prefix request. Diff the rendered request bytes of two consecutive turns. |
| Prefix below the minimum | `cache_creation_input_tokens == 0` with a marker present. Check the model's minimum (512 on current models). |
| Parallel fan-out over a cold prefix | N simultaneous requests each show `cache_creation_input_tokens` around the full prefix. Warm with one request first. |
| Traffic gaps longer than the TTL | Read share drops overnight or between bursts. Use the 1-hour TTL only if the gap is 5 to 60 minutes and the break-even holds. |
| Breakpoint after unique per-request content | Every request writes and none read the full shared part. Put an explicit marker at the end of the *shared* portion. |
| Reporting `input_tokens` as total input | It is only the uncached remainder. Sum all three usage fields. |
| Optimizing latency with caching when decode dominates | Split latency into TTFT and decode time in your traces. If decode dominates, cut output, not input. |

## In your day job

- Add `cache_read_input_tokens`, `cache_creation_input_tokens`, `input_tokens` and `output_tokens` to every LLM span ([Module 15](../15-observability-and-production/README.md)). Chart cache read share per route.
- Review prompt-assembly code the way you review a schema migration: anything that changes bytes near the top of the prompt is a breaking change for the cache.
- Before estimating a feature's cost, run `token_cost_model.py` with your real prefix size, output size and expected hit rate. Write the break-even hit rate in the design doc.
- Record TTFT and decode time separately in traces. They have different fixes.
