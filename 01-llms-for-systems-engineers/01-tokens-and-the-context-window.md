# 01: Tokens and the context window

## The idea

A model never sees characters. A tokenizer turns your request into a sequence of integer IDs from a fixed vocabulary of subword pieces. The model reads that sequence and emits one token at a time, and each emitted token is appended to the sequence before the next one is predicted. Three things you care about are counted in tokens: **cost** (you pay per input token and per output token), **latency** (output tokens are generated one at a time), and **capacity** (the context window is a token limit).

The **context window** is the maximum number of tokens in one request: system prompt, tool definitions, the whole message history, and the output. Current Claude models have a 1M-token window ([Anthropic, Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)). The window is the model's *only* working memory. The API is stateless, so every turn of a conversation resends the entire history. Whatever isn't in the window does not exist for the model.

Capacity is not the same as usable capacity. Recall and reasoning get worse as the window fills, gradually rather than at a cliff. Anthropic calls this **context rot** and describes context as a finite "attention budget" with diminishing returns ([Anthropic, "Effective context engineering for AI agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

## Why it matters

Chroma's July 2025 technical report tested 18 models from Anthropic, OpenAI, Google and Alibaba on deliberately simple tasks while varying only the input length. It found that "model performance varies significantly as input length changes, even on simple tasks" ([Hong, Troynikov, Huber, "Context Rot"](https://www.trychroma.com/research/context-rot)). Three findings matter for an engineer:

- **Similarity matters.** When the question and the relevant passage share fewer words (the realistic case, since you rarely phrase a question the way the answer is written), accuracy falls faster as the input grows.
- **One distractor hurts.** "Even a single distractor reduces performance relative to the baseline." Four are worse. A distractor here means a passage that looks relevant but isn't, such as the log line from the *other* consumer group or last week's stack trace.
- **Focused beats full.** On LongMemEval, every model did significantly better on a ~300-token focused prompt than on the same question embedded in ~113k tokens of full history.

An earlier result points the same way. In "Lost in the Middle" (Liu et al., 2023, [arXiv:2307.03172](https://arxiv.org/abs/2307.03172)), models used information at the start and end of a long context better than information in the middle.

So a 1M window works like a large heap in a garbage-collected runtime. You can allocate into it, but filling it up has costs you can't see until they bite.

## How it works

### Tokens: the units you're billed in

Subword tokenizers are trained on a corpus, so common English words are one token, and rare strings split into many. Rules of thumb that hold across modern tokenizers (measure your own payloads with the `count_tokens` endpoint, described below):

| Content | Tokenization behavior | Consequence |
|---|---|---|
| English prose | Roughly 3 to 4 characters per token | The cheapest content per byte |
| Source code | Worse than prose. Whitespace, symbols and identifiers fragment | A 2,000-line file is more tokens than you'd guess |
| JSON | Keys, quotes and braces all cost tokens, and they repeat in every record | Tool results in pretty-printed JSON can be several times the cost of a compact table |
| UUIDs, hashes, base64, long numbers | Fragment badly, several characters per token at best | A trace dump full of span IDs is expensive and hard for the model to compare |
| Non-English text | Usually more tokens per character than English | Budget separately for i18n workloads |

Token counts are **model-specific**. Anthropic notes that the tokenizer introduced with Opus 4.7 uses roughly 1x to 1.35x as many tokens as earlier models for the same text, so you have to re-baseline after a model upgrade even when per-token prices look similar. Count with the API, not with OpenAI's `tiktoken`, which is a different tokenizer:

```python
import anthropic

client = anthropic.Anthropic()
n = client.messages.count_tokens(
    model="claude-sonnet-5-5",
    messages=[{"role": "user", "content": open("consumer_lag_runbook.md").read()}],
).input_tokens
print(n)
```

Tools cost tokens before the conversation starts. Each tool's name, description and JSON schema are sent on every request. The API also adds its own tool-use system prompt, which is 286 tokens on Opus 5.5 and Sonnet 5.5 ([Anthropic, Pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Anthropic has reported tool definitions consuming 55k to 134k tokens in large MCP setups before the user said anything ([Anthropic, "Advanced tool use"](https://www.anthropic.com/engineering/advanced-tool-use)). See [Module 05](../05-tools-mcp-skills-hooks/README.md) for how to keep this down.

### Tokenization gotchas: why the model is bad at things a regex is good at

Because the model sees chunks, not characters, some trivial operations are hard for it. Karpathy's "Deep Dive into LLMs" covers the classic cases: spelling, counting letters, and comparing `9.11` with `9.9` ([Karpathy, YouTube](https://www.youtube.com/watch?v=7xTGNNLPyMI)). In your world the same failure shows up as:

- comparing two 40-character commit SHAs or two trace IDs that differ in one position;
- counting lines, rows or occurrences in a log excerpt;
- arithmetic on byte offsets, Kafka partition offsets, or epoch-millisecond timestamps;
- "is this version string newer?" (`1.10.0` vs `1.9.3`).

The fix is the one you'd use for any unreliable component: **don't ask it to do what a deterministic tool does perfectly.** Give it a tool (`grep -c`, `python -c`, `git merge-base`), or do the computation in code before the model sees it. Karpathy's advice is to say "use code" for counting and arithmetic. This is the first instance of the course thesis: move the checkable part out of the model and into something that can't be wrong.

### The context window: what's in it and how it fills

Every request renders in a fixed order: `tools`, then `system`, then `messages`. In an agent loop the messages grow every turn, because each tool call and tool result is appended. The total tokens *sent* across a session therefore grow quadratically with the number of turns, since turn *t* resends turns 1 to *t*−1. Prompt caching makes that affordable ([04-prompt-caching-cost-and-latency.md](04-prompt-caching-cost-and-latency.md)). Caching does nothing for context rot, though: a cached token still sits in the window and still competes for attention.

When the window approaches its limit, your options are:

1. **Don't put it in.** Retrieve just in time: pass a path or a query, and let the agent read the slice it needs.
2. **Clear it.** Drop old tool results that have been acted on. Anthropic's context-editing beta does this server-side.
3. **Compact it.** Summarize the history into a shorter state. Server-side compaction exists as a beta on current Claude models.
4. **Reset.** Start a fresh context from a durable state file (`progress.md`, `feature_list.json`). [Module 07](../07-loops/README.md) builds loops around this.

[Module 03](../03-context-engineering/README.md) covers choosing among them in depth.

## Worked example: triaging a consumer-lag incident

You're on call. `orders-consumer` lag has been climbing for 40 minutes. You have 6 hours of logs from 12 pods, about 1.4M lines.

**Bad version.** Dump the logs into the window and ask.

```text
<logs>
... 380,000 tokens of interleaved pod logs ...
</logs>
Which pod is causing the lag, and why?
```

Why it fails:

- It may not fit, and even when it does, every follow-up question resends 380k tokens.
- The needle (one pod logging `CommitFailedException` after a `rebalance in progress`) has low lexical overlap with "causing the lag". That is the low-similarity regime where Chroma saw the steepest drop.
- The haystack is full of distractors: normal rebalances from deploys, retries that succeeded, and a noisy `WARN` from an unrelated schema-registry client.
- Asking "which pod" means comparing pod names that differ by a hash suffix, which is a tokenization weak spot.

A typical answer (illustrative output) names a plausible pod, cites a `WARN` line from the schema-registry client, and is wrong.

**Good version.** Do the deterministic part deterministically, then give the model a small, high-signal context.

```bash
# 1. Deterministic reduction: count error signatures per pod (this is the part a tool does perfectly).
rg -c 'CommitFailedException|rebalance in progress|max.poll.interval' logs/ | sort -t: -k2 -nr | head
# logs/orders-consumer-7f9c4.log:412
# logs/orders-consumer-2b1d8.log:3
# ...

# 2. Pull a bounded window around the first occurrence on the top pod.
rg -n -B 20 -A 40 -m 1 'CommitFailedException' logs/orders-consumer-7f9c4.log > excerpt.txt
wc -l excerpt.txt   # 61 lines, ~3k tokens
```

```text
You are helping triage Kafka consumer lag. Facts already established by tooling:
- Pod orders-consumer-7f9c4 logged 412 CommitFailedException/rebalance lines in 6h; every other pod logged <= 3.
- Config: max.poll.interval.ms=300000, max.poll.records=500.

<excerpt source="orders-consumer-7f9c4.log" lines="18832-18892">
...61 lines...
</excerpt>

Using only the excerpt, explain the most likely mechanism for the repeated rebalances.
Quote the log lines you rely on. If the excerpt doesn't support a conclusion, say so.
```

Here the counting, which the model is bad at, was done by `rg`. The context is about 3k tokens instead of 380k. The question comes after the data. Anthropic's prompting guide says to put long inputs above the query, and reports that "queries at the end can improve response quality by up to 30 percent in tests" ([Anthropic, Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)). And the model is asked to quote the lines it relied on, which gives you something you can check. Every one of those choices makes the output more verifiable.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Estimating tokens as `len(text)/4` for code or JSON | Compare against `count_tokens` on a sample of real payloads. Expect the heuristic to undercount on code, JSON, IDs and non-English text. |
| Re-using token budgets across a model upgrade | Re-run `count_tokens` on your top 20 prompts with the new model ID. A 10 to 35% jump is plausible across tokenizer changes. |
| Treating "fits in the window" as "will be used" | Build a small needle eval: plant a fact at the start, middle and end of a realistic-length context and check recall at your production length. |
| Tool definitions silently eating the window | Log `input_tokens` on a request with an empty conversation. That number is your fixed tax per call. |
| Asking the model to count, compare IDs, or do offset arithmetic | Grep your prompts for "how many", "count", "compare", "which is newer". Replace each with a tool call or a precomputed fact. |
| Pretty-printed JSON tool results | Measure tokens per tool result. Switch to compact or tabular output, and paginate. |

## In your day job

- Before writing any prompt over a few thousand tokens, run `count_tokens` on it and record the number next to it, the way you'd note a payload size.
- Do the deterministic reduction first (grep, SQL, `jq`), then give the model the excerpt plus the established facts.
- When an agent session degrades after an hour, suspect context rot before you suspect the model. Check how many tokens are in the window and how much of it is stale tool output.
- Add a "tokens per request" histogram to whatever dashboards your LLM feature has. It is the leading indicator for both cost and quality drift.
