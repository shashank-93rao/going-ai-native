# 02: Research, plan, implement (fresh context per phase)

## The idea

Research-plan-implement (RPI) is explore-plan-implement with one structural change: **each phase runs in its own fresh session, and the only thing that crosses the boundary is a markdown artifact you've reviewed.** Dex Horthy (HumanLayer) describes it as "frequent intentional compaction". You design the whole workflow around keeping the context window small and relevant, rather than letting one session accumulate everything ([HumanLayer, "Advanced Context Engineering for Coding Agents"](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)).

| Phase | Session input | Session output | Your review |
|---|---|---|---|
| Research | The question, plus the repo | `research.md`: how the system works *today*, with file:line evidence | Hard. Is this true? |
| Plan | `research.md` + the ticket/spec | `plan.md`: phases, files, tests and a check per phase | Hard. Is this the right change? |
| Implement | `plan.md` | Commits, with the plan file updated as phases complete | Lighter. Read the tests closely, skim the rest. |

The argument rests on a leverage hierarchy, quoted from the post: "A bad line of code is… a bad line of code." "A bad line of a plan could lead to hundreds of bad lines of code." A bad line of research, "a misunderstanding of how the codebase works or where certain functionality is located, could land you with thousands of bad lines of code." So: "When you review the research and the plans, you get more leverage than you do when you review the code."

## Why it matters

Context is the constraint everything else follows from. The Claude Code docs: "LLM performance degrades as context fills." Horthy's operating rule is "keeping utilization in the 40%-60% range", which he says "depends on complexity of the problem" (same post). Explore-plan-implement in one session routinely breaks that rule: by the time you start implementing, the window holds 40 file reads, three dead-end hypotheses and a plan. RPI resets to near zero at each boundary, then loads only the artifact.

The post also includes the failure case worth remembering. Horthy and Blake Smith spent 7 hours trying to remove Hadoop dependencies from parquet-java, and "it did not go well". The research "didn't go deep enough through the dependency tree": it assumed classes could move upstream without bringing nested Hadoop dependencies along. His lesson: "you probably need at least one person who is an expert in the codebase." **RPI amplifies research quality in both directions.** Shallow research gives you a confident, wrong plan.

The success case is in the same post, as reported by the author. On a 300k-line Rust codebase (BAML) that he hadn't worked in, a bug-fix PR came together "within an hour or so". Two draft feature PRs were ready in about 7 hours: roughly 3 hours of research and planning and 4 of implementation. He adds that he had to "let go of reading every line of PR code" but "I still read the tests pretty carefully." These are one practitioner's reported numbers, not a controlled study.

## How to do it

### Research session

Start fresh (`/clear` or a new terminal), in plan mode or with read-only tools. The prompt asks for a description of the present, never a proposal:

```text
Research question: why can a consumer in group `ledger-writer` reprocess messages
after a rebalance?

Produce research.md using templates/research.md. Rules:
- describe how the code works today; no fixes, no opinions
- every claim gets file:line evidence or a test name
- trace the path from poll() to commit, including rebalance callbacks and threads
- list what you could NOT determine under "Unknowns" instead of guessing
- use subagents for broad searches so this session stays small
```

Then review it like a postmortem timeline. Spot-check three file:line citations yourself. If the research is wrong, **throw it away and rerun with more steering**, as the post advises. Don't patch it in a long conversation. Code is cheap. Reasoning built on a false premise is expensive.

### Plan session

Fresh session again. Input: `research.md` plus the ticket or SPEC ([03](03-spec-driven-development.md)). Output: `plan.md` from [templates/plan.md](code/templates/plan.md). The post's description: exact steps and files to change, "with testing and verification steps for each phase." Your review questions:

- Does every phase end in a check that can fail?
- Is there a phase 0 that reproduces the bug or pins current behaviour before anything changes?
- Does the file list match what the research says is involved? Anything missing is a smell.
- Are there "stop and ask" conditions?

### Implement session

Fresh session: "Implement phase 1 of plan.md. After the phase's verification passes, tick its boxes and append a line to the Progress log with the evidence." The post says to "compact the current status back into the original plan file" after each verified phase. That makes the plan file the durable state: if the session dies or drifts, a new session resumes from the file alone.

> **Synthesis:** the plan file works like a write-ahead log. The session's context is volatile memory. The plan with its progress log is what survives a crash, and recovery means "read the log, continue from the last committed step". Design the file so that recovery needs nothing else.

### Codex and other agents

Nothing here is Claude-specific. The phases are prompts plus files. OpenAI's long-horizon Codex write-up uses the same idea with four files: `Prompt.md` (frozen spec), `Plans.md` (milestones with validation commands), `Implement.md` (runbook) and `Documentation.md` (status log) ([OpenAI developers blog, "Run long horizon tasks with Codex"](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)). Run research in a read-only `codex exec`, and implementation with `--sandbox workspace-write`.

## Worked example: offsets regress after rebalance

**The bad version.** One long session:

```text
consumers in ledger-writer sometimes reprocess messages after a rebalance. fix it.
```

*(Illustrative output.)* The agent reads `LedgerConsumer.java` and sees `enable.auto.commit=false` and a `commitAsync()` in the poll loop. It concludes "offsets are committed asynchronously and may be lost", switches the loop to `commitSync()`, and reports success. Latency per batch rises by a broker round trip, and the bug is still there. The real issue is in the `ConsumerRebalanceListener`, which the agent never opened, and nothing was reproduced, so nothing could show the fix was wrong.

**The good version.** Research session output *(illustrative, abridged)*:

```markdown
# RESEARCH: reprocessing after rebalance in ledger-writer
Commit researched: 4be1c09

## Summary
Offsets are committed in two places: commitAsync() every batch (LedgerConsumer.java:142)
and commitAsync() in onPartitionsRevoked (RebalanceHandler.java:31). The revoke-time commit
is async, so it can still be in flight when the partition is assigned to another member,
which then starts from the last *completed* commit.

## Relevant code
| Location | What it does | Evidence |
|---|---|---|
| RebalanceHandler.java:28-35 | onPartitionsRevoked -> consumer.commitAsync(currentOffsets, cb) | callback only logs errors |
| LedgerConsumer.java:118-150 | poll loop, processes then commitAsync per batch | max.poll.records=500 |
| LedgerConsumerIT.java:77 | rebalance test, asserts processedCount == 1000 | uses Thread.sleep(3000) |

## Unknowns
- Whether the ledger write itself is idempotent (dedupe by message key?). Not visible in this repo;
  LedgerClient is a generated stub. Ask the ledger team.
```

You check `RebalanceHandler.java:31` yourself, and it's there. You notice the Unknowns item and answer it from your own knowledge: the ledger write is *not* idempotent. That raises the priority, so you add it to the ticket.

Plan session output *(abridged)*:

```markdown
### Phase 0: make it fail on demand (covers: reproduce)
- [ ] Add LedgerConsumerIT.revokeDuringInflightCommit: force a rebalance with a second
      member right after a batch, assert no offset is processed twice
- [ ] Run 50x: `for i in $(seq 50); do mvn -q -Dtest=LedgerConsumerIT#revokeDuringInflightCommit verify || echo FAIL; done | grep -c FAIL`
      -> expect > 0 failures before the fix
### Phase 1: commitSync on revoke
- [ ] RebalanceHandler.onPartitionsRevoked -> consumer.commitSync(currentOffsets)
- [ ] Same 50x loop -> expect 0 failures
### Stop and ask if
- the fix seems to need changes to the per-batch commit path
```

Implement session: phases 0 and 1, with evidence pasted into the progress log. (The full scenario, including the flaky-test side of it, is [examples.md](examples.md) scenario 2.)

**Why the second version works.** The research session was told to trace rebalance callbacks, so it found the second commit site. Its Unknowns section surfaced a business-critical fact (non-idempotent writes) that no amount of code reading would have produced. The plan forced a reproduction before the fix, so the fix has an oracle.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Research that proposes fixes | Look for "should", "we could" or "I recommend" in research.md. Send it back. Proposals anchor the plan before the facts are checked. |
| Uncited claims | Count claims without file:line or test evidence. Each one is a guess. |
| Shallow dependency tracing (the parquet-java failure) | The research names a module but not what it imports. Ask: "for each class you propose to move, list its transitive imports." |
| Carrying chat history across phases | The implement session can "remember" a rejected idea. Start it fresh, from the file only. |
| Plan without phase 0 | No step makes the bug or behaviour observable before the change. Add one. |
| Using RPI for one-line fixes | The ceremony costs more than the change. The one-sentence-diff rule from [01](01-explore-plan-implement-verify.md) still applies. |

## In your day job

- Keep `research.md` and `plan.md` in the branch (or under `docs/plans/`). They're the review artifact, and the next on-call engineer will thank you.
- In PR review, read the plan and the tests closely and skim the implementation. That matches where the leverage is, and Horthy's own practice.
- When research comes back wrong, delete it and rerun with sharper questions. Don't repair it in conversation.
- For codebases you don't know well, pair the research review with someone who does. That is the parquet-java lesson.
