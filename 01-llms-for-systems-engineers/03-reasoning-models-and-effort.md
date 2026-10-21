# 03: Reasoning models and the effort knob

## The idea

A reasoning model generates a stretch of "thinking" tokens before its visible answer. Those tokens are ordinary sampled output. They cost output-token prices, they take decode time, and they count against `max_tokens`. They exist because, as Karpathy puts it in his "Deep Dive into LLMs", models need tokens to think: each token gets a fixed amount of computation, so a hard problem needs more tokens of intermediate work ([Karpathy, YouTube](https://www.youtube.com/watch?v=7xTGNNLPyMI)). Reinforcement learning from verifiable rewards trained models to use that space productively, and Karpathy notes this added a new dial, test-time compute ([Karpathy, "2025 LLM Year in Review"](https://karpathy.bearblog.dev/year-in-review-2025/)).

On current Claude models you no longer set a thinking budget in tokens. You set **effort**, and the model decides how much to think on each step (adaptive thinking). Effort is a quality, cost and latency dial within one model. Treat it like any other capacity setting: choose it per route, measure it, and re-tune it when the model changes.

## Why it matters

Effort settings have caused real regressions. Anthropic's April 2026 postmortem on Claude Code quality traces a diffuse drop in quality to three combined changes. One of them was lowering the default effort from high to medium. The change passed code review, unit and end-to-end tests, and dogfooding ([Anthropic, "An update on recent Claude Code quality reports"](https://www.anthropic.com/engineering/april-23-postmortem)).

More effort is not always better either. LangChain reports that running its coding agent at the highest reasoning setting throughout scored *worse* than a "reasoning sandwich" (highest effort to plan, high to implement, highest to verify), 53.9% versus 63.6%, because the always-max runs hit timeouts ([LangChain, "Improving Deep Agents with harness engineering"](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)). OpenAI recommends medium as the daily driver for its Codex models even after adding a higher setting ([OpenAI, GPT-5.1-Codex-Max](https://openai.com/index/gpt-5-1-codex-max/)).

## How it works

### The Claude API surface (October 2026)

Effort lives in `output_config`:

```python
resp = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    output_config={"effort": "high"},          # low | medium | high | xhigh | max
    thinking={"type": "adaptive", "display": "summarized"},  # optional: show a reasoning summary
    messages=[{"role": "user", "content": PROMPT}],
)
```

Facts that matter, from the Claude API reference as of 2026-10-19:

| Model | Thinking | Default effort | Notes |
|---|---|---|---|
| Opus 5.5 | Always on. `{"type": "disabled"}` and `budget_tokens` return 400 | **medium** | Lower effort is the only way to think less |
| Sonnet 5.5 | Adaptive by default. `{"type": "between_tools"}` turns off thinking, at effort `high` or below | high (levels recalibrated) | Re-run the sweep if you came from Sonnet 5 |
| Haiku 5.5 | Adaptive, on by default | **medium** | |
| Fable 5.1 | Always on | high | Thinking is never shown raw |

Some consequences:

- **Defaults differ across models.** An unset effort means medium on Opus 5.5 and high on Sonnet 5.5, so set it explicitly in every request. Otherwise a model swap silently changes your effort.
- **Thinking is billed even when you can't see it.** On current models the default `display` is `"omitted"`, so thinking blocks come back with empty text, but you pay for every thinking token as output. If you stream to a user, the default looks like a long pause before the first visible token. Set `display: "summarized"` if you need progress visible.
- **`max_tokens` bounds thinking plus answer.** If thinking eats the budget, you get `stop_reason: "max_tokens"` and a truncated or empty answer. Check `stop_reason` before you parse.
- **Changing effort mid-conversation can break the cache** (see [04](04-prompt-caching-cost-and-latency.md)). Anthropic documents a beta per-message effort setting that avoids this on recent models.

### What effort actually changes

Lower effort means less thinking. In agent loops it also means fewer and more consolidated tool calls, less preamble, and terser confirmations. Higher effort means more exploration and more self-checking, and on long tasks, more wall-clock time. That last part matters: a higher effort can *lower* the success rate when a harness has timeouts, which is what the LangChain result above shows.

OpenAI exposes the same idea as `reasoning_effort`, and adds a separate `verbosity` parameter for answer length. Claude has no verbosity parameter, so answer length comes from effort and from the prompt (an explicit length or format instruction). See [Module 02](../02-prompting-as-specification/README.md).

### Choosing effort: a decision rule

*Course synthesis*, built from the Anthropic and OpenAI guidance above:

1. **Start from the workload.** Chat, classification, extraction and high-volume routes usually do well at `low`. Agentic coding and long-horizon multi-step work respond strongly to effort. Start them at `medium` or `high`.
2. **Sweep before you set.** Run your eval at two or three effort levels and record pass rate, cost per completed task, and p95 latency.
3. **Pick the cheapest level within your error bar of the best.** If medium and high differ by less than the noise, take medium ([Module 12](../12-hill-climbing/README.md) covers the statistics).
4. **Tune per route, not globally.** A planning step and a lint-fix step in the same agent can want different settings.
5. **Re-sweep on every model change.** Effort levels are recalibrated between models. A cheaper model at high effort is not automatically better than a stronger model at low effort, or the other way round. Measure it.

Judge cost **per completed task**, not per request. A cheaper setting that needs two more turns or a retry is not cheaper.

## Worked example: an effort sweep for a PR-review bot

Your team runs a bot that reviews diffs for concurrency bugs in a Go service: data races, missing `ctx` cancellation, unbounded goroutine fan-out. You have 60 historical PRs with labelled findings.

**Bad version.** Somebody sets it once and forgets it.

```python
# review_bot.py
resp = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=4000,                      # too small for high effort on big diffs
    output_config={"effort": "max"},      # "correctness matters"
    messages=[{"role": "user", "content": review_prompt(diff)}],
)
findings = parse(resp.content[-1].text)   # ignores stop_reason
```

What goes wrong:

- At `max`, thinking on a 3,000-line diff can exceed 4,000 tokens. The response stops with `stop_reason: "max_tokens"`, the last block isn't a text block, and `parse` either crashes or returns "no findings". A bot that silently says "no findings" is worse than no bot.
- Review latency is minutes, so engineers merge before it reports.
- Nobody knows whether `max` beats `medium` on this workload, because nobody measured it.

**Good version.** Sweep on the labelled set, then set the value deliberately and guard the response.

```python
# effort_sweep.py (sketch; uses ainative_kit-style client and your eval from Module 10)
LEVELS = ["low", "medium", "high", "xhigh"]
for level in LEVELS:
    results = [run_review(pr, effort=level) for pr in LABELLED_PRS]   # 60 PRs
    report(level,
           recall=mean(r.found_labelled_bug for r in results),
           false_pos=mean(r.false_positives for r in results),
           cost_per_pr=mean(r.cost for r in results),
           p95_latency=p95(r.latency for r in results),
           truncated=sum(r.stop_reason == "max_tokens" for r in results))
```

A sweep table looks like this (illustrative output; the shape is typical, but the numbers are invented for the example):

| effort | recall | false positives / PR | cost / PR | p95 latency | truncated |
|---|---|---|---|---|---|
| low | 0.52 | 0.4 | $0.03 | 14 s | 0 |
| medium | 0.71 | 0.6 | $0.07 | 31 s | 0 |
| high | 0.75 | 0.6 | $0.14 | 62 s | 1 |
| xhigh | 0.76 | 0.7 | $0.26 | 140 s | 4 |

With 60 PRs, the standard error on a recall near 0.73 is about 0.06. So medium, high and xhigh are statistically indistinguishable on recall, while cost and latency roughly double at each step. You pick `medium`, raise `max_tokens` so truncation can't happen, and fail closed on truncation:

```python
resp = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=32000,
    output_config={"effort": "medium"},
    messages=[{"role": "user", "content": review_prompt(diff)}],
)
if resp.stop_reason != "end_turn":
    raise ReviewIncomplete(resp.stop_reason)       # surface it; never report "no findings"
findings = parse("".join(b.text for b in resp.content if b.type == "text"))
```

The effort level is now a measured, recorded configuration value with a reason attached. When the model changes, you rerun the sweep.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Relying on the default effort | Grep request code for `output_config`. Any call without an explicit effort changes behavior when the model ID changes. |
| `max_tokens` too small for the effort level | Count `stop_reason == "max_tokens"` in your logs per route. It should be near zero. |
| Parsing `content[-1].text` | Thinking blocks come before text, and a truncated response may contain no text block. Always filter by `type == "text"` and check `stop_reason`. |
| Sending `budget_tokens` or `thinking: {"type": "disabled"}` to Opus 5.5 | 400 errors. Use effort instead. |
| Judging effort by cost per request | Track cost per *completed* task, including retries and extra turns. |
| Assuming max effort is safest | Check timeouts and wall-clock in the sweep. Longer thinking can fail more under a deadline. |
| A stale effort sweep | Store the sweep date and model ID next to the configured value, and alert when the model ID changes without a new sweep. |

## In your day job

- Put `effort` and `max_tokens` in config, per route, with the date and model of the sweep that justified them.
- Add `stop_reason` and output-token counts to your LLM call metrics. A rise in `max_tokens` stops is an incident precursor.
- When a cost spike appears, check output tokens first. Thinking tokens are output tokens, and they usually dominate the bill on reasoning-heavy routes.
- On a model upgrade, run the effort sweep before anything else ([Module 12](../12-hill-climbing/README.md), the model-upgrade drill).
