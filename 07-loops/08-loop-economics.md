# 08: Loop economics

## The idea

A loop's cost is **iterations × cost per iteration**, and neither factor is constant. Cost per iteration rises within a session because the API is stateless and the full history is resent every turn. Success per iteration falls, because the easy fixes land first and later rounds work on the hard residue. You budget a loop the same way you budget retries against a paid dependency: estimate the expected cost per *success*, look at the marginal cost of one more round, and stop where the next round isn't worth it.

## Why it matters

The public numbers span four orders of magnitude, and the difference is mostly loop design rather than model choice:

| Run | What | Cost | Unit cost (derived) | Source |
|---|---|---|---|---|
| Mitchell Hashimoto, Ghostty feature | 16 sessions, about 8 hours | $15.98 | about $1 per session | [Hashimoto](https://mitchellh.com/writing/non-trivial-vibing) |
| Anthropic solo agent (app build) | 20 min, core feature broken | $9 | n/a: it didn't work | [harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps) |
| Anthropic full harness (same app) | 6 hours, planner/generator/evaluator | $200 | more than 20x the solo run | same |
| Anthropic Opus 4.6 DAW build | 3 h 50 min, 3 build/QA rounds | $124.70 | about $42 per round | same |
| repomirror, 6 repos overnight | about 1,100 commits | under $800 | about $0.73/commit; about $10.50/hour per Sonnet agent | [repomirror](https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md) |
| Carlini C compiler | 16 agents, about 2,000 sessions, 2 weeks, about 2B input + 140M output tokens | just under $20k | about $10 and about 1M input tokens per session | [Carlini](https://www.anthropic.com/engineering/building-c-compiler) |
| Bun Zig to Rust port | about 11 days, more than 1M lines added; 5.9B uncached input, 690M output, 72B cached reads | about $165k at API pricing | about $15k/day; about $0.17 per line added | [Sumner via Willison](https://simonwillison.net/2026/Jul/8/rewriting-bun-in-rust/) |
| OpenAI long-horizon Codex | about 25 hours, about 30k lines | about 13M tokens (no $ given) | about 430 tokens per line | [OpenAI](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) |

The derived unit costs are this course's arithmetic on the published totals. Two lessons from the table:
- **The cheap run is often the expensive one.** Anthropic's $9 solo run produced a broken core feature, so its cost per *working* app was effectively infinite. The $200 harness was cheaper per unit of working software.
- **Caching dominates long runs.** Bun's 72B cached reads were about 12x its uncached input. Cached reads are billed at a small fraction of the base input price (check current pricing for the exact multiplier). Without caching, the input bill would have been several times larger.

## How it works

### Cost per iteration inside one session

Let `S` be the fixed prefix (system prompt, tools, AGENTS.md) and `d` the tokens each turn adds (assistant output plus tool results). Turn *k* sends about `S + k·d` input tokens. Over *n* turns:

```text
total_input ≈ n·S + d·n²/2          (quadratic in turns)
```

With prompt caching, everything except the newest `d` tokens on each turn is a cache read, so the uncached part grows only linearly. That's the effect OpenAI describes in the Codex loop: caching makes sampling "linear rather than quadratic", but only with an exact prefix match, so you must never reorder tools or edit history mid-thread ([Bolin](https://openai.com/index/unrolling-the-codex-agent-loop/)).

Worked numbers (course arithmetic, `S = 8,000`, `d = 3,000`, a placeholder price of $3 per million input tokens and $0.30 per million for cache reads, ignoring output tokens and cache-write premiums):

| Turns | Input tokens sent | No caching | With caching |
|---|---|---|---|
| 10 | 215,000 | $0.65 | $0.16 |
| 30 | 1,545,000 | $4.63 | $0.72 |
| 60 | 5,790,000 | $17.37 | $2.24 |

Doubling turns from 30 to 60 nearly quadruples the uncached bill. That's the economic argument for **fresh-context iterations** (Ralph, [05](05-ralph-loops.md)): each new session resets `k` to zero and pays `S` again, which is cheap because `S` is cached. It's also why the governor's token cap ([03](03-governors.md)) is set on input tokens, not just on turns.

### Diminishing returns across rounds

Model each fix round as a fraction of the remaining failures getting fixed. A worked example (course arithmetic): round 1 succeeds 60% of the time, each later round fixes 35% of what's left, and round cost rises from $0.40 to $1.00 as context grows.

| Cap (rounds) | Cumulative success | Expected cost per task | Cost per success | Marginal cost per *extra* success |
|---|---|---|---|---|
| 1 | 60.0% | $0.40 | $0.67 | $0.67 |
| 2 | 74.0% | $0.62 | $0.84 | $1.57 |
| 3 | 83.1% | $0.80 | $0.97 | $2.00 |
| 4 | 89.0% | $0.95 | $1.06 | $2.43 |
| 5 | 92.9% | $1.06 | $1.14 | $2.86 |

The last column is the one to decide on. If a failed task costs you a 30-minute human look, almost any of these rounds is worth paying for. If a failure is cheap (the item just goes back in the queue for tomorrow's run), stop at 2. Stripe's minions stop at two CI rounds because each round costs "tokens, compute, and time", with diminishing returns, and because they push local, fast checks before any CI round ([Stripe](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)).

Estimate the real curve from your own traces: for each task, record the round in which the oracle first passed and the tokens spent per round. `self_correct.measure()` ([04](04-self-correcting-loops.md)) produces exactly this curve.

### Levers, cheapest first

| Lever | Typical effect | Evidence |
|---|---|---|
| Faster, local, deterministic checks before expensive ones | Fewer expensive rounds | Stripe: lint subset in under 5 s on push, then at most 2 CI rounds |
| Smaller context per iteration (fresh sessions, filtered tool output) | Cheaper turns, better quality | Huntley: "The more you allocate to a context window, the worse the performance"; Carlini printed few lines, logged the rest |
| Shorter prompts | Faster and better | repomirror cut a 1,500-word prompt to 103 words |
| Prompt-cache discipline | Large input savings on long runs | Bun's cached-to-uncached ratio; Codex append-only design |
| Effort / model routing | Often the main cost lever | Anthropic's Opus 5 guide recommends effort as the primary cost lever; LangChain found xhigh everywhere scored *worse* (53.9% vs 63.6%) because of timeouts |
| Hard per-run caps | Bounded worst case | `--max-budget-usd` in `claude -p`; Willison suggests a dedicated org with a hard budget such as $5 for any credential that can spend money ([Willison](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/)) |
| Fewer, better iterations (one item per loop) | Fewer reverted iterations | Huntley; Anthropic one-feature-per-session |

### Budgeting a loop before you run it

*Course synthesis*, as a pre-flight checklist:
1. Run 3–5 iterations by hand and read the traces: tokens per iteration (input, cached, output), wall time, and how often an iteration was kept.
2. Expected iterations = items ÷ keep-rate. Cost = expected iterations × cost per iteration × 1.5 (for variance).
3. Set the dollar cap at 3–5x a normal run ([Anthropic automations](https://claude.dev/blog/building-effective-agent-automations/)), make it **pause** (exit `BUDGET`), and alert. Don't make it fail silently.
4. Decide the value of a success in the same units: engineer-hours saved, incidents avoided. If expected cost per success exceeds it, fix the oracle or the task decomposition before you fix the prompt.

## Worked example: pricing an overnight migration

Situation: migrate 300 Java services from a deprecated metrics client to OpenTelemetry. Each service is one Ralph item, and the oracle is `./gradlew compileJava test` plus a grep for the old import.

**Bad version.** "It's about $10/hour per agent according to repomirror, so 8 agents for 10 hours is $840." This borrows someone else's per-hour rate for a different task and says nothing about whether the run will finish.

**Good version.** A pilot of 5 services, read from the traces (illustrative numbers for this exercise):

```text
per iteration: 210k input (180k cached), 9k output, 6.5 min wall clock
keep rate: 4 of 5 iterations kept (one reverted on a Gradle plugin conflict)
```

Estimate (placeholder prices: $3/M input, $0.30/M cached, $15/M output):
- Cost per iteration ≈ 30k × $3/M + 180k × $0.30/M + 9k × $15/M = $0.09 + $0.054 + $0.135 ≈ **$0.28**
- Expected iterations ≈ 300 ÷ 0.8 = 375; × 1.5 variance ≈ 560 iterations
- Expected cost ≈ 560 × $0.28 ≈ **$157**. Wall clock at 8 parallel agents ≈ 560 × 6.5 min ÷ 8 ≈ 7.6 h
- Governor settings: `--max-budget-usd 1` per iteration (about 3.5x normal), `--max-iterations 600`, `--max-hours 10`, `stall_patience 3` per agent, total spend alarm at $250

The morning check: compare actual cost per kept iteration to the $0.35 estimate ($0.28 ÷ 0.8). If it's twice that, open the traces before running the next night. Something is looping, and the governor log should tell you what.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Budgeting from someone else's $/hour | No pilot traces behind the estimate |
| Long sessions with growing history | Input tokens per turn rising linearly in traces; switch to fresh-context iterations |
| Cache misses from mutating the prefix | Cached-read share dropping mid-run; diff request prefixes |
| Counting cost per run instead of per success | Cheap runs with low keep-rate; report $/kept-iteration and $/merged-PR |
| Max effort everywhere | Timeouts or wall-clock trips rising; run an effort sweep ([12-hill-climbing](../12-hill-climbing/README.md)) |
| Budget cap that fails silently | Runs ending with no report; make `BUDGET` an inbox item |
| Ignoring human review cost | PRs/day exceeding review capacity; [17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md) |

## In your day job
- Add `input_tokens`, `cached_tokens`, `output_tokens` and `$` per iteration to every loop's log line, and report $/kept-iteration, not $/run.
- Before any overnight run, do a 5-item pilot and write the estimate down. Compare it to actuals in the morning.
- Cap fix rounds at 2 unless your own pass-by-round curve says otherwise.
- Treat cache hit rate as a cost SLO for long-running agents, and alert when it drops.
