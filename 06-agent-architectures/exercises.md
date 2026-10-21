# Exercises

Run everything from the course root. Offline exercises use `FakeClient` and need no key. Exercises marked **[API]** need `ANTHROPIC_API_KEY`. Exercises marked **[agent]** need a coding agent such as Claude Code.

```bash
.venv/bin/python -m pytest -q 06-agent-architectures/code      # baseline: all green
```

---

## 1. Extract the workflow hiding in an agent (45 min, offline)

**Goal:** Practise the "agent-washing" diagnosis from [01](01-augmented-llm-and-workflows-vs-agents.md).

**Steps**
1. Write a `FakeClient` responder that makes `patterns.agent_loop` triage DLQ messages. Tools are `read_dlq`, `classify`, `replay` and `discard`, and the fake always calls them in the same order for each message.
2. Run it over 20 synthetic messages, and record the tool-call sequence per run from `AgentResult.messages`.
3. Rewrite it as a workflow: a deterministic pre-filter, one `Augmented.ask` per message for classification, and a code table mapping category to action.
4. Write a test that counts model calls for both versions over the same 20 messages.

**Done when**
- A test asserts that the workflow makes at most one model call per message that passes the pre-filter, and zero for the rest.
- A test asserts that `replay` is never called on a message whose classifier evidence is not a substring of the error text.

**Stretch:** Add a `GateFailed` path that escalates to a human queue, and assert the escalation count.

---

## 2. Add a groundedness gate and prove it can fail (30 min, offline)

**Goal:** Gates that only check format are a pitfall from [02](02-five-workflow-patterns.md). Write one that checks content.

**Steps**
1. In `incident_summary.py`, `summary_gate` checks timestamps and services. Add a check that every *version string* in the summary (regex `v?\d+\.\d+\.\d+`) appears in the timeline.
2. Write a failing test first: a scripted summary for INC-4480 that says "rolled back to v2.30.3", when the log says v2.30.4.
3. Make it pass.

**Done when**
- The new test fails on the old gate and passes on the new one. Show both runs.
- The gate's reason string names the offending version, so the retry prompt can fix it.

---

## 3. Measure what voting buys (60 min, [API])

**Goal:** Find out whether `vote()` improves accuracy on a binary decision or just costs 5x.

**Steps**
1. Write 30 migration snippets labelled `safe_online: yes/no`. Include `CREATE INDEX` with and without `CONCURRENTLY`, `ADD COLUMN ... DEFAULT` with volatile and non-volatile defaults, `ALTER TYPE`, and `SET NOT NULL`.
2. Score a single call against `vote(n=5)` at temperature 1.0, and against `vote(n=5)` where each voter gets a *different* prompt phrasing.
3. Record accuracy, abstain rate (`winner is None`), and tokens.

**Done when**
- A table with three rows (single, same-prompt vote, varied-prompt vote) and columns for accuracy, abstain rate and tokens, run on at least 30 items.
- One sentence stating whether the varied-prompt panel beat the same-prompt panel, with the counts. Don't claim significance at n=30. See [12-hill-climbing](../12-hill-climbing/README.md) for why.

---

## 4. Break the SQL checker, then harden it (45 min, offline)

**Goal:** Learn to think like a reward-hacking generator.

**Steps**
1. Write three SQL candidates that try to pass `SqlChecker` without being correct. Ideas: hard-coded rows (already blocked), a query that is correct only for seed 7's date distribution, and one that reads `sqlite_master`.
2. For any that pass, add a check that stops them: a third fixture, a schema allowlist, or a different seed range.
3. Replace the reference-query check with two **invariants** that need no reference: total revenue over regions equals a direct sum over completed September orders, and `order_count` never exceeds the number of completed September orders.

**Done when**
- Every cheating candidate has a test asserting `ok is False`.
- The invariant-only checker still rejects `ATTEMPT_FANOUT` and `ATTEMPT_BOUNDARY` and accepts `ATTEMPT_FIXED`.

**Stretch:** Run `optimize_sql` against the real API with the invariant-only checker on five new questions, and record rounds-to-pass.

---

## 5. Single-writer review of a real design (30 min, offline, written)

**Goal:** Apply the R/W labelling from [03](03-multi-agent-and-the-single-writer-rule.md) to something real.

**Steps**
1. Take a multi-agent design from your team, or the rate-limiter "three writers" design in 03.
2. Label every agent R or W, and list each W's write set *and its read set*: what it assumes about other agents' outputs.
3. Find one write-skew pair, meaning two W-agents with disjoint write sets where one's read set overlaps the other's write set.
4. Redesign it with one writer, or justify partitioned writers by naming the per-partition oracle and the merge gate.

**Done when**
- A one-page write-up containing the R/W table, the write-skew pair, and the redesign.
- Every remaining W-agent has a named check that runs after its writes.

---

## 6. Crash-test the durable run (45 min, offline)

**Goal:** Own the crash matrix from [05](05-durable-runs-event-sourcing-idempotency.md).

**Steps**
1. Add a crash point `"mid_log_write"` to `run_log.py` that writes half a JSON line and then raises.
2. Add a second side-effecting tool, `page_oncall`, whose remote does **not** honour keys. Wrap it in a local dedup table (`dict[key, result]`) that is persisted *before* the remote call returns. Think about why that ordering still leaves a window.
3. Write a hypothesis test: for a random crash point and a random number of resumes (1-3), the final ticket count is exactly 1 and model calls are exactly 3.

**Done when**
- The hypothesis test passes with `max_examples=100`.
- A comment in your `page_oncall` wrapper explains the remaining window in two sentences, and says which tool you'd mark `idempotent=False` as a result.

---

## 7. Choose and defend a double-texting policy (30 min, offline)

**Goal:** Turn [06](06-double-texting-and-concurrency.md) into a decision for a real product surface.

**Steps**
1. Write a planner for your own agent: real step names, and the steps that have side effects.
2. Run `simulate()` for every policy with arrivals at every tick from 0 to the run length.
3. Tabulate, per policy, how many arrival times lead to (a) a stale side effect, (b) a lost correction, or (c) a compensation warning.

**Done when**
- A table of policy × {stale effect, lost correction, compensation} counts.
- A one-paragraph recommendation that names the failure mode you accept and the product flow (confirm, compensate or escalate) that handles it.

**Stretch:** Implement "interrupt only at tool boundaries", where a correction that arrives mid-tool is deferred to the next boundary, and show that `executed-result-not-observed` disappears.

---

## 8. Ablate the subagents (60-90 min, [agent])

**Goal:** Measure harness decay on your own codebase.

**Steps**
1. Pick five real tasks from your backlog that a coding agent can finish in under 30 minutes each, and that have a check (tests or a build).
2. Run each twice: once with default delegation, and once with `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=1` plus the Opus 5 damping prompt from [03](03-multi-agent-and-the-single-writer-rule.md) in CLAUDE.md. These env vars need Claude Code 2.1.217 or later, per Anthropic's Opus 5 guide; check `claude --version`.
3. Record pass/fail by your check, wall time, and cost (from `/cost` or the SDK's usage).

**Done when**
- A 5x2 table with pass, time and cost for each cell.
- A decision recorded in CLAUDE.md, either keeping the cap or not, with the date and model version. Re-run this on the next model upgrade.
