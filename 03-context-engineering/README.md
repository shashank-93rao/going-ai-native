# 03: Context engineering, retrieval and memory
> After this module you can decide, and defend with measurements, what goes into a model's context window, what stays outside it, how it gets fetched, and how it survives a long run.

## Why this matters

The model sees exactly one thing: the tokens in its window on this call. It has no other view of your repo, your incident, or what it decided an hour ago. Dex Horthy puts it bluntly: "the contents of your context window are the ONLY lever you have to affect the quality of your output" ([HumanLayer, "Advanced context engineering for coding agents"](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)). Model choice and sampling settings matter too, but inside a session the window is the thing you control.

The window is also a degrading resource, not a fixed-size buffer. Anthropic describes an "attention budget" and **context rot**: as the token count grows, "the model's ability to accurately recall information from that context decreases" ([Anthropic, "Effective context engineering for AI agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)). Chroma measured 18 models and found that performance becomes "increasingly unreliable as input length grows", even on simple tasks, and that a single topically related distractor lowers accuracy ([Chroma, "Context Rot"](https://www.trychroma.com/research/context-rot)). The 200k or 1M on the spec sheet is the capacity. The usable amount at the quality you want is smaller, and you only find out how much smaller by measuring.

What goes wrong without this skill looks like ordinary flakiness. The agent "forgets" a constraint you gave it 80 turns ago because compaction dropped it. A 600-line CLAUDE.md gets half-followed. An on-call assistant cites a runbook command that doesn't exist, because retrieval returned the wrong chunk and the model filled the gap. The prompt-cache hit rate collapses because someone put a timestamp at the top of the system prompt. None of these is a model bug. Each one is a context bug, and each has a check you can write.

The course thesis applies directly: **autonomy should scale with verifiability.** In this module, verifiable means three things. Retrieval has recall@k against labelled questions. Compaction has a list of pinned facts that must survive it. Context files are tested by running the same tasks with and without them.

## The distributed-systems anchor

You already know this problem as the **memory hierarchy and the working set**.

| Memory hierarchy | Agent context |
|---|---|
| Registers / L1 | The current turn: the user message and the latest tool result |
| RAM (working set) | The context window |
| Disk / object store | Repo files, runbooks, logs, the session event log |
| Page fault, demand paging | Just-in-time retrieval: `grep`, `read_file`, `search_runbooks` |
| Prefetching | Pre-loading CLAUDE.md, pinned facts |
| Eviction policy (LRU and so on) | Compaction, tool-result clearing |
| Thrashing | The agent re-reading the same files because its summaries lost them |
| CPU cache line reuse | Prompt-prefix caching |
| Write-ahead log | An append-only session log the agent can query after compaction |

Where the analogy breaks matters more than where it holds:

- **RAM does not get worse as it fills. Context does.** A page that is resident is read perfectly. A fact sitting at token 140k is recalled less reliably than the same fact at token 2k, and a near-duplicate distractor makes it worse. So "it fits" is not the same as "it works". Keep the working set small even when there is room.
- **Eviction is lossy and semantic.** LRU evicts whole pages and you can page them back in byte-for-byte. Compaction rewrites history into a summary written by a model, which can drop or distort a constraint. Treat it like a lossy codec, and test what survives it.
- **Cache keys are prefixes, not addresses.** A prompt cache hit needs an *identical prefix*. One changed byte early in the prompt invalidates everything after it. That makes prompt layout an ordering problem, like append-only event logs, not a placement problem.

## Learning goals
- [ ] Estimate the token cost of each part of a real agent's context (system prompt, tool definitions, context files, history, tool results) and name what to cut first.
- [ ] Decide between pre-loading and just-in-time retrieval for a given piece of information, using a written rule.
- [ ] Choose compaction, a fresh-context reset, or a queryable log for a long task, and explain the tension in Anthropic's own guidance.
- [ ] Lay out a prompt so the cacheable prefix is byte-identical across calls, and detect when it is not.
- [ ] Rewrite a bloated CLAUDE.md/AGENTS.md into a ~100-line map, and A/B test it against the old version and against no file at all.
- [ ] Use subagents to keep exploratory tokens out of the main context, and write the delegation prompt.
- [ ] Choose between agentic search and vector RAG for a corpus, and evaluate retrieval with recall@k and answers with a grounding check.
- [ ] Classify an agent's memory as semantic, episodic or procedural, and choose where each lives and how it is updated.

## Reading order
1. [01-context-as-a-budget.md](01-context-as-a-budget.md): the window as a finite, degrading budget; context rot; what belongs in it and what doesn't.
2. [02-just-in-time-and-isolation.md](02-just-in-time-and-isolation.md): pre-loading vs just-in-time retrieval, tool-output hygiene, and subagents as a context firewall.
3. [03-long-runs-compaction-reset-log.md](03-long-runs-compaction-reset-log.md): compaction vs a fresh reset vs a queryable log, and the disagreement inside Anthropic's material.
4. [04-cache-prefix-discipline.md](04-cache-prefix-discipline.md): prompt caching as an append-only-log problem.
5. [05-context-files.md](05-context-files.md): CLAUDE.md/AGENTS.md as a map, not a manual. Worked example: 600 lines down to 90.
6. [06-retrieval-agentic-search-vs-rag.md](06-retrieval-agentic-search-vs-rag.md): grep vs embeddings, contextual retrieval, and retrieval and grounding evals. Worked example: an on-call runbook assistant. For RAG as a production system (indexes, ingestion, freshness, ACLs), go on to [Module 18](../18-rag-systems/README.md).
7. [07-memory-taxonomy.md](07-memory-taxonomy.md): semantic, episodic and procedural memory, and where each one lives.
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/)

## Prerequisites
- [01: LLMs for systems engineers](../01-llms-for-systems-engineers/README.md): tokens, context windows, sampling, and the basics of prompt caching.
- [02: Prompting as specification](../02-prompting-as-specification/README.md): writing prompts as versioned specs, and the instruction hierarchy that context files plug into.
- Helpful but not required: [07: Loops](../07-loops/README.md), which uses fresh-context-plus-state-files heavily; and [10: Evals fundamentals](../10-evals-fundamentals/README.md) for the eval vocabulary used in file 06.

## Key takeaways
- Context is a budget that degrades as you spend it. Aim for the smallest set of high-signal tokens, not the largest set that fits.
- Pre-load only what every turn needs. Give the agent references (paths, queries, ids) and tools to fetch everything else just in time.
- Compaction is a lossy codec. Pin the facts that must survive, check them in code after every compaction, and write evicted turns to a log the agent can query.
- Default to a fresh context plus durable state files at unit-of-work boundaries. Use compaction for continuity within a unit. Re-test both on every model upgrade.
- Cache hits need byte-identical prefixes: static content first, append-only history, no mid-session tool changes, no timestamps at the top. Track the hit rate as a cost SLO.
- A context file is a map, not a manual: roughly 100 lines of commands, layout, invariants and pointers. Procedures go to skills, path-specific rules to scoped files, and style to linters.
- Agentic search (grep, glob, read) wins for code and other corpora with precise identifiers. Vector or hybrid RAG wins for prose with vocabulary mismatch. Either way, measure recall@k before you judge answers.
- Every context artifact is code: version it, test with and without it, and prune it when the model changes.
