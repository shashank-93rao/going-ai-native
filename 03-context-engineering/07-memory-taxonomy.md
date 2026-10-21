# 07: Memory: semantic, episodic and procedural

## The idea

A model has no memory between calls. Everything that looks like memory is context that a harness chose to put back into the window. "Agent memory" is therefore a storage-system design problem: what gets written, by whom, where it lives, how it is read back, and when it expires.

A useful taxonomy, borrowed from cognitive science and used in LangChain's long-term memory course ([DeepLearning.AI, "Long-term agentic memory with LangGraph"](https://www.deeplearning.ai/short-courses/long-term-agentic-memory-with-langgraph/)), sorts memory by **what kind of thing is remembered**:

| Type | What it holds | Agent example | Natural home |
|---|---|---|---|
| **Semantic** | Facts about the world, the domain or the user | "invoice_id is unique per region"; "this user prefers Go" | A fact store, the context file, `docs/` |
| **Episodic** | What happened: specific past experiences | "INC-6120: duplicate charges, caused by `allkeys-lru`, fixed by ..."; a past successful trajectory | A log, postmortems, a searchable index of past runs |
| **Procedural** | How to do things | The release procedure; "run `make fmt lint test` before done"; the system prompt itself | Skills, context files, prompts, code |

There is also a time axis: **short-term** (working) memory is the context window, and **long-term** memory is everything persisted outside it. The earlier files in this module were about managing short-term memory. This one is about the long-term store and the paths in and out of it.

## Why it matters

Memory is where agent systems quietly accumulate wrong state. A distributed-systems engineer will recognize all three of these failure modes:

- **Unbounded growth.** A memory file that is appended to on every session and pre-loaded on every call becomes the 600-line CLAUDE.md problem from [05](05-context-files.md), except this time the agent wrote it. Claude Code's auto memory deals with this directly. Only the first 200 lines or 25KB of the `MEMORY.md` index load at session start, and when the index nears the limit Claude Code tells Claude to shorten it and move details into topic files ([Claude Code docs, memory](https://code.claude.com/docs/en/memory)).
- **Poisoning.** A hallucinated or one-off "fact" that gets written to memory is re-read as truth in every later session. This is Breunig's context poisoning ([01](01-context-as-a-budget.md)) made durable. It is also a security issue: memory and context poisoning is on the OWASP list for agentic applications, and anything an attacker can get written into memory gets replayed ([Module 16](../16-security-and-containment/README.md)).
- **Staleness.** A memory that was true last quarter ("the replica is never more than 1s behind") becomes a confident wrong premise.

Anthropic's scheduled-automation post shows the alternative discipline. Preferences live in a read-only store that the agent re-reads every run, and status claims are re-verified against the live source just before acting: "One stale "still waiting on you" costs more trust than ten missing items, so never hedge an item's status: assert it or drop it" ([Anthropic, "Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/)).

## How it works / how to do it

### Design each memory type as a store with a write path and a read path

**Semantic memory.**
- *Write path:* explicit and reviewed. Facts that matter to everyone go into the repo (`docs/glossary.md`, the context file's invariants) through a PR. Per-user preferences can be written by the agent, but with provenance attached.
- *Read path:* the few facts with no natural trigger go in the pre-loaded map. The rest are fetched just in time.
- *Consistency:* each fact lives in one place. Eugene Yan's advice is to prune rules so each lives in one place ([Yan, "How to work and compound with AI"](https://eugeneyan.com/writing/working-with-ai/)). Duplicates drift apart and become contradictions.

**Episodic memory.**
- *Write path:* append-only and automatic. Session logs, postmortems, the progress files from [03](03-long-runs-compaction-reset-log.md). Don't edit episodes; append corrections.
- *Read path:* almost always just in time, by search. "Have we seen this alert before?" is a retrieval query over postmortems, scored with the same recall@k eval as [06](06-retrieval-agentic-search-vs-rag.md).
- *Use:* past successful trajectories make good few-shot examples. Past failures make good eval cases ([Module 10](../10-evals-fundamentals/README.md)).

**Procedural memory.**
- *Write path:* the most dangerous one, because a change here changes behaviour on every future run. The LangChain course's version is a system prompt refined from feedback. That is a self-editing prompt, a mild form of hill-climbing ([Module 12](../12-hill-climbing/README.md)). Anthropic's skills post suggests having Claude write its successes and mistakes back into a skill ([Anthropic, "Agent Skills"](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)).
- *Gate:* treat every procedural-memory write as a **prompt deploy**: proposed as a diff, run against the eval suite, and reviewed ([Module 02](../02-prompting-as-specification/README.md)).

### Map the tools you already have onto the taxonomy

| Mechanism | Type | Who writes | Loaded |
|---|---|---|---|
| CLAUDE.md / AGENTS.md | Procedural plus key semantic facts | Humans, via PR | Every session |
| `.claude/rules/`, nested context files | Procedural, scoped | Humans | On matching path |
| Skills | Procedural | Humans, or agent-proposed via PR | Description always, body on use |
| Claude Code auto memory (`user`, `feedback`, `project`, `reference` notes) | Mostly semantic; `feedback` is procedural | The agent | `MEMORY.md` index at start, topics on demand |
| Anthropic memory tool (`memory_20250818`) | Whatever you design | The agent, through file operations | Through tool calls |
| Progress files, `feature_list.json`, git log | Episodic, plus the current task's state | The agent | At session start (reset) |
| Session event log | Episodic | The harness | Queried on demand |
| Postmortems, runbooks | Episodic and procedural | Humans | Retrieved |

Claude Code's auto memory deliberately skips "anything it can derive from the codebase, such as architecture, file paths, or debugging fixes", and anything the CLAUDE.md files already say (memory docs, October 2026). That is a good rule for any memory system: don't store what you can recompute, because the copy will drift from the source.

Karpathy has described a related pattern, reported in secondary coverage: instead of RAG over raw documents, an agent maintains an interlinked Markdown wiki, with entity pages, per-source summaries and flagged contradictions, and runs periodic health checks over it. That is compiled semantic memory that the agent garbage-collects. Treat it as an idea to try, not a measured result.

## Worked example: an on-call assistant that "learns"

**Situation.** After a month, the billing team wants the runbook assistant from [06](06-retrieval-agentic-search-vs-rag.md) to remember what it learned in past incidents.

**Bad version.** After each session, append "what we learned" to `memory.md` and pre-load it:

```python
notes = client.complete([{"role": "user", "content": f"What should you remember from this incident?\n{transcript}"}]).text
with open("memory.md", "a") as f:
    f.write(f"\n## {date.today()}\n{notes}\n")
SYSTEM = BASE_SYSTEM + open("memory.md").read()      # pre-loaded every call
```

(illustrative) Six weeks later `memory.md` is 1,400 lines. On 2026-09-14 it recorded "Fix for consumer lag: reset offsets to latest". That came from a session where an engineer *considered* it and rejected it, and the summarizer got the polarity wrong. The line now sits in every prompt, it contradicts the runbook, and nothing flags it. Semantic, episodic and procedural content is mixed in one pre-loaded blob with no provenance and no expiry.

**Good version.** Split by type, and give each type its own write gate.

*Episodic*: every incident session writes a structured, append-only record, which is retrieved by search and never pre-loaded:

```json
{"episode_id": "INC-7731", "date": "2026-10-19", "alert": "InvoiceConsumerLagHigh",
 "root_cause": "max.poll.interval.ms 30000 < batch time ~45s -> rebalance storm; poison message p7/o99120",
 "actions": ["commit 3f9c2ab raise max.poll.interval.ms to 300000", "billing-ctl dlq skip p7/o99120"],
 "rejected": ["reset offsets to latest (drops invoices)"],
 "evidence": ["log:events/INC-7731#0-5"], "runbook_chunks_used": ["kafka-consumer-lag#diagnosis", "kafka-consumer-lag#mitigation"]}
```

The `rejected` field is the fix for the polarity bug: considered-and-rejected actions get their own field, not a sentence a summarizer can flip.

*Semantic*: facts the assistant proposes are written as **candidates** with provenance, and nothing is loaded until a human accepts it:

```json
{"fact": "invoice-consumer batch processing takes ~45s at batch size 2000",
 "source": "INC-7731", "proposed_by": "oncall-assistant", "status": "candidate",
 "expires": "2027-01-19", "verify_with": "billing-ctl metrics query 'histogram_quantile(0.9, invoice_batch_seconds_bucket)'"}
```

Accepted facts go into `docs/` or the context file's invariants through a normal PR. The `verify_with` field makes the fact checkable later, and the expiry makes it get checked.

*Procedural*: when two or more episodes show the runbook was missing a step, the assistant opens a PR against the runbook or skill. CI runs the retrieval eval and the grounding tests from `code/` on the PR. Merging the PR is the memory write.

**What changed:** each memory type got the write path its risk calls for. Episodic writes are automatic and append-only. Semantic writes are proposed with provenance and accepted by a human. Procedural writes are eval-gated deploys. The pre-loaded prompt did not grow.

## Pitfalls

- **One blob for all memory types.** Detect it: a single memory file mixing preferences, incident stories and instructions. Split by type.
- **Pre-loading episodic memory.** Detect it: the prompt contains dated incident narratives. Episodes should be retrieved, not pre-loaded.
- **No provenance.** Detect it: you can't answer "where did this memory come from?" for a random entry. Require `source` on every write.
- **No expiry or re-verification.** Detect it: memories older than the last major refactor still load. Add `expires` and `verify_with`.
- **Ungated procedural writes.** Detect it: the agent edits its own prompt or skills without an eval run. Route those writes through PRs plus evals.
- **Memory as an injection vector.** Detect it: memory content that came from untrusted input (tickets, emails, web pages) loads with the same trust as human-written rules. Tag memories by trust level and never promote untrusted content to procedural memory ([Module 16](../16-security-and-containment/README.md)).

## In your day job

- List every place your agents persist state across sessions, and label each one semantic, episodic or procedural.
- Add `source` and `expires` fields to whatever memory store you already have.
- Make "rejected options" a first-class field in your incident and decision records.
- Treat a change to a prompt, skill or context file proposed by the agent itself exactly like one proposed by a human: diff, eval, review.
