# 03: Long runs: compaction, a fresh reset, or a queryable log

## The idea

When a task outlives one context window, you have three ways to carry state forward:

1. **Compaction.** Summarize the older part of the conversation into a shorter block and keep going in the same session. It preserves continuity. It is also lossy, and the loss is decided by a model.
2. **A fresh-context reset.** End the session at a clean boundary, write the state to durable files (a progress note, a structured task list, git commits), and start a new session that reads them. Lossless for whatever you wrote down, and lossy for everything you didn't.
3. **A queryable log.** Keep the full history outside the window as an append-only event log, and let the agent read slices of it on demand. Nothing is thrown away. You pay in retrieval: the agent has to know what to look up.

If you have built consensus systems, you have seen these before. Compaction is a **snapshot**. The reset is **checkpoint and restart**. The queryable log is the **replicated log** itself. The difference from Raft is that Raft's snapshots are exact, so it can truncate the log afterward. A model-written summary is not exact, so truncating the log after compaction is a decision you may regret.

## Why it matters: Anthropic's own material disagrees

This is a real tension, and you should know each position in its own words.

**Position A: prefer a fresh window.** Anthropic's prompting guide, in its section on workflows across multiple context windows: "When a context window is cleared, consider starting with a brand new context window rather than using compaction. Claude's latest models are extremely effective at discovering state from the local filesystem." It then gives startup instructions: "Call pwd; you can only read and write files in this directory." "Review progress.txt, tests.json, and the git logs." ([Anthropic, "Prompting best practices"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)). The long-running harness post builds on the same idea: an initializer session writes `init.sh`, a progress file and a JSON feature list, and every later session starts by reading them. It also says compaction alone was not enough ([Anthropic, "Effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)).

**Position B: compaction is enough on newer models.** In the application-harness post, context resets with a handoff artifact were essential on Sonnet 4.5, which showed "context anxiety" and wrapped up early as the window filled. On Opus 4.5 the team dropped resets and relied on automatic compaction ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)). The Managed Agents post tells the same story: "when we used the same harness on Claude Opus 4.5, we found that the behavior was gone... The resets had become dead weight." The context-engineering post calls compaction "the first lever in context engineering to drive better long-term coherence."

**Position C: both make irreversible choices, so keep the log.** The Managed Agents post argues that compaction, trimming and similar techniques "all involve irreversible decisions about what to keep," and that such decisions "can lead to failures," because you can't predict what future turns will need. Its design keeps the session as "the append-only log of everything that happened," a context object that lives outside the window. A `getEvents()` interface lets the agent "interrogate context by selecting positional slices of the event stream" ([Anthropic, "Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents)).

Practitioners mostly side with A. Dex Horthy's research-plan-implement workflow starts each phase fresh from a Markdown artifact, and he argues that Ralph's value is "fresh context per unit of work" ([HumanLayer, "A brief history of Ralph"](https://humanlayer.dev/blog/brief-history-of-ralph)). OpenAI's long-horizon Codex write-up keeps durable memory in `Prompt.md`, `Plans.md`, `Implement.md` and `Documentation.md` ([OpenAI, "Run long horizon tasks with Codex"](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)). OpenAI also trains models for native compaction across windows, which is evidence for B ([OpenAI, GPT-5.1-Codex-Max](https://openai.com/index/gpt-5-1-codex-max/)).

**Course stance.** Fresh context plus durable state files is the default at **unit-of-work boundaries** (from [01-gap-analysis](../research/01-gap-analysis.md)). The positions are compatible once you see them as layers rather than alternatives:

> **Synthesis:** The log is the durability layer: always keep it, because storage is cheap and irreversibility is expensive. State files are the checkpoint, written at every unit-of-work boundary, and they make a reset possible. Compaction is the continuity mechanism *within* a unit of work, used when stopping would throw away valuable working state. Which one carries the most weight depends on the model, so re-measure it on every upgrade ([Module 12](../12-hill-climbing/README.md)).

## How it works / how to do it

### Decision rule

| Situation | Primary mechanism |
|---|---|
| A unit of work just finished (feature passes, migration step committed) | **Reset.** Write state, commit, start fresh. |
| Mid-investigation, with lots of hypotheses and partial evidence that are hard to write down | **Compact**, with pinned facts. |
| Interactive pairing session that is going well but getting long | **Compact**, or clear old tool results first. |
| You have corrected the agent twice on the same thing | **Reset** with a better prompt. "A clean session with a better prompt almost always outperforms a long session with accumulated corrections" ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)). |
| Compliance or debugging needs "what exactly did it see and do?" | **Log**, always on, regardless of the other two. |
| A loop that runs for hours unattended | **Reset** each iteration plus state files plus log ([Module 07](../07-loops/README.md)). |

### Make compaction checkable

Anthropic's advice for writing a compaction prompt is to keep architectural decisions, unresolved bugs and implementation details and to drop redundant tool output, and to tune the prompt for recall first (keep everything that matters) and precision second (cut the rest). That is an eval statement. You can only tune for recall if you measure it.

`code/compaction.py` turns the contract into code:

1. **Split safely.** The verbatim tail must start with a plain user turn. It must never start with an assistant turn, or with a `tool_result` whose `tool_use` was summarized away, because the API rejects orphaned tool results.
2. **Extract pinned facts** from the head with deterministic patterns: incident ids, `CONSTRAINT:` and `DECISION:` lines, commit SHAs, file paths.
3. **Summarize** with a prompt that lists what to keep.
4. **Check** that every pinned fact appears in the summary. Re-attach any that don't, and report them as a recall failure of the summarizer.
5. **Log** the evicted turns to an `EventLog` and tell the agent where they are.

On the API side, as of October 2026 Anthropic offers server-side compaction (on demand, or at a token threshold) with an option to supply your own summarization prompt, plus context editing to clear tool results or thinking blocks by rule ([compaction docs](https://platform.claude.com/docs/en/build-with-claude/compaction), [context editing docs](https://platform.claude.com/docs/en/build-with-claude/context-editing)). These features are in beta and their parameters change, so check the current docs before you depend on a parameter name. The pinned-fact check works the same way whoever writes the summary.

### Make resets cheap

A reset is only as good as the handoff. The handoff should be:

- **Structured where it can be.** Anthropic recommends JSON for test or task status and freeform text for progress notes, and says to use git for state ([prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).
- **Verifiable on startup.** The new session runs `init.sh` and a smoke test before new work, so it checks the handoff's claims instead of trusting them.
- **Append-mostly.** The long-running harness post lets agents only flip `passes` in the feature list, because models are less likely to rewrite JSON inappropriately.

## Worked example: an incident session that outlives its window

The session: `invoice-consumer` lag on `invoices.v2`. The user stated two constraints at the start, the agent found a rebalance storm, a fix was committed, and now lag remains on partition 7 only.

**Bad version: a summary trusted blindly.** The summarizer writes a fluent summary and drops the constraints. Here is the real output of the course's lossy fake summarizer, which drops `CONSTRAINT` lines the way a careless model might:

```text
- ASSISTANT: [tool_use get_logs {"service": "invoice-consumer"}]
- WARN Revoking previously assigned partitions
- ASSISTANT: Rebalance storm. Batch takes ~45s; max.poll.interval.ms is 30000 in deploy/invoice-consumer/values.yaml.
- USER: DECISION: raise max.poll.interval.ms to 300000, keep batch size. Commit it.
- ASSISTANT: Committed in commit 3f9c2ab: deploy/invoice-consumer/values.yaml.
```

The incident id is gone, and so are "do not reset offsets" and "no deploys before 09:00 UTC". Twenty turns later the agent, now looking at a poison message on partition 7, is one step away from `--reset-offsets --to-latest`. That is the exact action the first constraint forbade, and the one the Kafka runbook says "silently drops invoices".

**Good version: pinned facts plus a log.** The same lossy summarizer, run through `compact()`:

```text
$ python code/compaction.py
evicted 6 messages; pinned 6 facts
summarizer dropped: ['INC-7731', 'CONSTRAINT: do not reset offsets.', 'CONSTRAINT: no deploys before 09:00 UTC.']
<compacted_history>
- ASSISTANT: [tool_use get_logs {"service": "invoice-consumer"}]
...
Pinned facts (restored by harness):
- INC-7731
- CONSTRAINT: do not reset offsets.
- CONSTRAINT: no deploys before 09:00 UTC.

Full earlier history: event log entries 0..5 (query with grep/slice).
</compacted_history>

Lag is still 60k on partition 7 only. Why?
```

Three things happened that a blind summary would not give you:

- The facts the harness declared critical survived, *regardless* of summarizer quality.
- The harness **measured** the summarizer's recall: it dropped 3 of 6 pinned facts. Log that number. If it is consistently above zero, fix the summarization prompt. The check keeps you safe in the meantime.
- The raw `Revoking previously assigned partitions` logs are not in the window, but they are not gone either. `log.grep("Revoking")` finds them.

The test that guards this is `test_critical_facts_survive_a_lossy_summarizer` in `code/test_compaction.py`.

**At the unit-of-work boundary**, once partition 7 is fixed, reset instead of compacting again. The handoff file:

```markdown
# progress/INC-7731.md
Status: mitigated 04:12 UTC; monitoring.
Constraints: do not reset offsets; no deploys before 09:00 UTC.
Done: max.poll.interval.ms 30000 -> 300000 (commit 3f9c2ab). Poison message p7/o99120 routed to DLQ via `billing-ctl dlq skip`.
Open: why did a malformed invoice pass schema validation? (ticket BILL-2291)
Verify on start: `kafka-consumer-groups --describe --group invoice-consumer` shows lag < 1k on all partitions.
```

The next session starts with "Read progress/INC-7731.md, run the verify command, then work on BILL-2291". It has a clean window and loses nothing that mattered.

## Pitfalls

- **Trusting summaries.** Detect it: pin facts and count how often the summarizer drops them. A nonzero rate with no check in place means you are relying on luck.
- **Compacting across a unit-of-work boundary.** Detect it: a summary that mixes two tasks' decisions. Reset instead.
- **A handoff nobody verifies.** Detect it: a new session that starts by building on "tests pass" without running them. Put a verify command in the handoff.
- **Splitting a tool_use/tool_result pair.** Detect it: API 400 errors right after compaction. Use a safe split point.
- **Deleting the log after compaction.** Detect it: you can't answer "why did it do that?" in a post-incident review. Keep the log. Storage is cheap.
- **Keeping harness scaffolding the model no longer needs.** The resets that helped Sonnet 4.5 "had become dead weight" on Opus 4.5. Detect it: ablate the reset or compaction policy on every model upgrade and compare pass rate and cost.

## In your day job

- Add a `CONSTRAINT:` / `DECISION:` convention to your agent prompts and pin those lines through compaction.
- For any agent task longer than an hour, write a handoff template (status, constraints, done, open, verify-on-start) and reset at each boundary.
- Turn on full transcript logging for your agents, and make it queryable by the agent itself, not just by you.
- Put "re-test the reset/compaction policy" on the checklist for model upgrades.
