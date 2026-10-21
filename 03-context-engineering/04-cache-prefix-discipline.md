# 04: Cache-prefix discipline

## The idea

An agent loop resends the whole history on every call. Turn 40 carries turns 1 to 39 plus the system prompt and the tool definitions. Without caching, total input grows quadratically with the number of turns. **Prompt caching** lets the provider reuse the computed state of a prefix it has already seen, so you pay a fraction of the price, and wait a fraction of the time, for the part that hasn't changed.

The catch is in the word *prefix*. Anthropic's docs: "Prompt caching references the entire prompt: `tools`, `system`, and `messages` (in that order), up to and including the block designated with `cache_control`" ([Anthropic, "Prompt caching"](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). A hit needs the bytes up to the breakpoint to be identical to a previous request. Change one byte early and everything after it is a miss.

So caching is not a setting you switch on. It is a **layout discipline**: static content first, volatile content last, and history that is only ever appended to. If you have built an event-sourced system, you already have the right instinct. Treat the prompt as an append-only log and never rewrite history in place.

## Why it matters

The economics are large enough to drive architecture. As of October 2026 the Anthropic docs list:

| | Multiplier on base input price |
|---|---|
| Cache write, 5-minute TTL (default) | 1.25x |
| Cache write, 1-hour TTL | 2x |
| Cache read | 0.1x in general; 0.05x on Claude Opus 5.5 and Sonnet 5.5; 0.025x on Fable 5.1 and Mythos 5.1 |

The minimum cacheable prefix is 512 tokens on the current 5.x models and larger on some older ones. Shorter prefixes are simply not cached, and no error is returned. You can set up to 4 breakpoints, and the TTL refreshes each time the cache is read. Check the [pricing and caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) before relying on these numbers, because they change by model.

A worked calculation, using only those documented multipliers. Take a 30k-token stable prefix (system prompt, tools, context file) and a 40-turn session on Sonnet 5.5, ignoring the growing history:

- No caching: 40 x 30k = 1.2M base-price input tokens.
- Caching: one write at 30k x 1.25 = 37.5k, then 39 reads at 30k x 0.05 = 58.5k. About 96k base-price equivalents in total.

That is roughly 12x cheaper on the prefix, before counting the history, which caches too if you only append to it. Time to first token also drops on hits, though by how much depends on the deployment.

OpenAI's Codex team reports the same lessons from the other side. Caching needs exact prefix matches. Changing tools, model, sandbox or working directory mid-thread breaks the cache, so Codex *appends* a message describing a change instead of editing earlier content. An early bug that listed MCP tools in an inconsistent order caused cache misses. With caching, they write, "sampling the model is linear rather than quadratic" ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)).

## How it works / how to do it

### Layout rules

1. **Order by volatility.** Tools (rarely change), then the system prompt (changes per deploy), then the context file (changes per commit), then history (append-only), then the current turn.
2. **No volatile bytes in the prefix.** No timestamps, request ids, user names, "today is..." lines, or per-request feature flags in the system prompt. Put them in the latest user message.
3. **Deterministic serialization.** Sort tool definitions by name, serialize JSON with sorted keys, and normalize whitespace. This is the MCP tool-ordering bug, fixed in general.
4. **Append, don't edit.** To change the agent's instructions mid-session, append a message ("From now on, also run `make lint`"). Don't rewrite the system prompt.
5. **Don't change tools mid-session.** Under Anthropic's invalidation rules, a change to tool definitions invalidates the tools, system and messages caches. Toggling some features also invalidates later levels. Changing thinking or effort settings invalidates at least the message cache. Images added or removed anywhere affect the message cache.
6. **Place breakpoints at the boundaries of stable regions:** after tools and system, after the context file, and on the latest message for the growing history. The docs also describe an automatic mode and a 20-block lookback for finding earlier cache entries.

### Know which context techniques fight the cache

Every technique in [03](03-long-runs-compaction-reset-log.md) rewrites earlier bytes, so each one is a cache invalidation:

- **Tool-result clearing** invalidates the cached prefix from the cleared point onward. Anthropic's context-editing docs suggest `clear_at_least` so that each clear removes enough tokens to be worth the new cache write ([context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)).
- **Compaction** rewrites the history. After it, you pay one cache write on the new, shorter prefix.
- **A reset** starts a new prefix. The stable part (tools, system, context file) can still hit if it is byte-identical across sessions, which is one more reason to keep it stable.

> **Synthesis:** Clear or compact in big, infrequent steps rather than small, frequent ones. Each rewrite costs a cache write, so ten small clears cost ten writes for the savings of one big one. It is the same trade-off as batch size against write amplification in an LSM tree.

### Measure it

Cache behaviour is visible in every response. Anthropic's `usage` has `cache_read_input_tokens`, `cache_creation_input_tokens` and `input_tokens` (the uncached tokens after the last breakpoint). Track the **cache hit ratio** = read / (read + creation + input) per session, and treat it as a cost SLO, as OpenAI's Codex post suggests. A sudden drop is a regression with a cause in a diff, just like a p99 latency jump.

## Worked example: a timestamp that cost 10x

**Bad version.** A team's triage agent built its system prompt like this:

```python
SYSTEM = f"""You are the billing on-call assistant.
Current time: {datetime.utcnow().isoformat()}
On-call engineer: {pager.current_oncall()}
{open("AGENTS.md").read()}
{TOOL_USAGE_GUIDE}"""

client.messages.create(
    model="claude-sonnet-5-5",
    system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
    tools=sorted_tools if random_feature_flag() else sorted_tools + [debug_tool],
    messages=history,
    max_tokens=2048,
)
```

There are two defects. The timestamp on line 2 changes every call, so the system block never matches and nothing after the tools is ever read from cache. The feature flag adds or removes a tool per request, which invalidates the tools level as well. (illustrative trace data) `cache_read_input_tokens` is 0 on nearly every call, and `cache_creation_input_tokens` is about 30k on every call, so the team pays the 1.25x *write* premium on every request. That is worse than not caching at all.

**Good version.**

```python
SYSTEM_STATIC = f"""You are the billing on-call assistant.
{open("AGENTS.md").read()}
{TOOL_USAGE_GUIDE}"""                      # changes only when the repo changes

TOOLS = sorted(all_tools(include_debug=settings.DEBUG_TOOLS), key=lambda t: t["name"])  # fixed per deploy

def turn(history, user_text):
    volatile = f"<now>{datetime.utcnow().isoformat()}</now><oncall>{pager.current_oncall()}</oncall>\n"
    history = history + [{"role": "user", "content": volatile + user_text}]   # append only
    return client.messages.create(
        model="claude-sonnet-5-5",
        tools=TOOLS,
        system=[{"type": "text", "text": SYSTEM_STATIC, "cache_control": {"type": "ephemeral"}}],
        messages=history,
        cache_control={"type": "ephemeral"},   # automatic breakpoint on the last cacheable block
        max_tokens=2048,
    )
```

The volatile facts moved into the newest user turn. The tool list is decided once per deploy and sorted. History is append-only. The top-level `cache_control` uses the automatic mode described in the docs; if you prefer explicit placement, put a breakpoint on the last message block instead. The SDK call shape is shown for illustration, so check the current docs for parameter names.

**Make it a test.** `code/context_budget.py` lays out stable sections first and exposes the prefix, so a test can assert prefix identity across two different requests:

```python
def test_stable_sections_form_identical_prefix_across_calls():
    a1 = assemble(triage_sections("alert A", LOGS, HISTORY), budget=2000)
    a2 = assemble(triage_sections("a totally different alert", LOGS, HISTORY), budget=2000)
    assert a1.prefix == a2.prefix
```

The budgeter also refuses a section that is both `stable` and optional, because an optional section can be dropped, and the day it is dropped every later byte shifts. Put the same kind of assertion in your own harness's CI: build two prompts for different inputs and assert that the bytes up to the breakpoint are equal.

## Pitfalls

- **Volatile data in the system prompt.** Detect it: a cache hit ratio near zero, and a diff of two consecutive requests' system prompts.
- **Non-deterministic tool ordering**, from dict iteration over MCP servers or plugin load order. Detect it: hash the serialized tools per request and alert if the hash changes within a session.
- **Prefixes under the minimum.** A 300-token system prompt is never cached, silently. Detect it: `cache_creation_input_tokens == 0` on the first call.
- **TTL expiry in slow loops.** A loop that waits 10 minutes between calls misses the 5-minute cache every time. Detect it: hit ratio falls with inter-call gap. Use the 1-hour TTL where the write premium pays off.
- **Frequent small clears or compactions.** Detect it: many `cache_creation_input_tokens` spikes per session. Batch your context edits.
- **Mid-session model or effort switches** for "routing". Each switch can invalidate caches. Route at session boundaries where you can ([Module 15](../15-observability-and-production/README.md)).

## In your day job

- Add `cache_read_input_tokens / total input` to your agent dashboards today, with an alert on drops.
- Grep your system prompts for `now()`, `utcnow`, `date`, `uuid` and user names, and move each match to the latest user turn.
- Add a prefix-stability test to CI for every agent that has a long stable prefix.
- When you review a PR that changes tools, prompts or compaction policy, ask "what does this do to the cache?" the same way you'd ask "what does this do to the index?"
