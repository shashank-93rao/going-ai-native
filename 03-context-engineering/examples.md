# Examples: context engineering on a Monday morning

Each scenario: *Situation, then the naive approach and what happens, then the AI-native approach with artifacts, then what to check.* Model outputs that were not actually run are marked (illustrative output).

---

## 1. The kitchen-sink session on a rate limiter bug

**Situation.** A Go token-bucket rate limiter in `ledger-api` lets bursts through after a pod restart. You've been in one Claude Code session for two hours: you asked about the bug, then about an unrelated flaky test, then a refactor, and back to the limiter.

**Naive approach.** Keep correcting in the same session: "No, the bucket should start empty." "No, I said start *empty*." (illustrative) The agent's third fix re-introduces the first bug. The window is full of three tasks' worth of dead ends. That is context distraction and clash, and Anthropic's best practices name it as two failure patterns: the kitchen-sink session and correcting over and over.

**AI-native approach.**
1. Stop after the second failed correction. The rule, from [Claude Code best practices](https://code.claude.com/docs/en/best-practices): "A clean session with a better prompt almost always outperforms a long session with accumulated corrections."
2. Ask the current session to write a handoff before you `/clear`:
   ```text
   Write HANDOFF.md: the bug, the reproduction, what we tried and why each failed,
   the constraint that the bucket starts empty after restart, and the files involved
   with line numbers. No more than 25 lines. Do not propose a fix.
   ```
3. `/clear`, then start fresh:
   ```text
   Read HANDOFF.md. Write a failing test in internal/ratelimit/bucket_test.go that
   restarts the limiter and asserts the first request after restart is rejected when
   capacity is 0. Show it failing. Then fix bucket.go so it passes. Run `make test`.
   ```

**What to check.** The new session's first action should be reading `HANDOFF.md`, and its first code should be the failing test. Compare tokens-to-fix with the old session in your traces. The fresh one should be a fraction of the size.

---

## 2. Cache hit rate drops from 85% to 3% after a harmless deploy

**Situation.** Your incident agent's dashboard shows `cache_read_input_tokens / total_input` falling from about 0.85 to about 0.03 overnight. Cost per session triples. The deploy diff "only added a Grafana MCP server".

**Naive approach.** Assume the provider changed something, and file a support ticket.

**AI-native approach.**
1. Pull two consecutive requests from the same session out of your traces and diff the serialized prefix: tools, then system, then the first message.
2. You find that the tool list order differs between requests. The new MCP server registers tools asynchronously, so iteration order depends on startup timing. This is the same class of bug OpenAI described for Codex, where inconsistent MCP tool ordering caused cache misses ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)).
3. Fix: sort tools by name at serialization and freeze the list per session.
4. Add a CI test that builds the prompt twice, with tools registered in different orders, and asserts byte-identical prefixes. That is the same shape as `test_stable_sections_form_identical_prefix_across_calls` in `code/test_context_budget.py`.
5. Add an alert on hit ratio below 0.5 over 30 minutes.

**What to check.** Hit ratio recovers on the next deploy, and the CI test fails if you deliberately shuffle the tools. "Prove it can fail" applies to this check too.

---

## 3. A 40-table migration that outlives every context window

**Situation.** You're moving 40 Postgres tables from `numeric` money columns to `bigint` minor units with an expand/contract migration. Each table needs a migration, a backfill job, a dual-write change and a test. It's far too much for one window.

**Naive approach.** One long session with auto-compaction. (illustrative) By table 15 the summary has lost which tables already have dual-writes, and the agent writes a second backfill for `refunds`.

**AI-native approach.**
1. **Initializer session.** It writes `migration_plan.json` with one entry per table: `{"table": "refunds", "steps": {"expand": false, "dual_write": false, "backfill": false, "contract": false}, "notes": ""}`. Agents may only flip booleans and append notes, the same JSON-not-Markdown choice as Anthropic's long-running harness ([Anthropic, "Effective harnesses"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)). It also writes `init.sh`, which brings up the local Postgres and runs `make migrate-check`.
2. **Per-table sessions, fresh context each time.**
   ```text
   Run ./init.sh. Read migration_plan.json and `git log --oneline -20`.
   Pick the first table with any step false. Do exactly one step for that table.
   Run `make migrate-check test`. Commit with message "money-migration: <table> <step>".
   Set that step to true in migration_plan.json. Stop.
   ```
3. **Read-only subagent for analysis.** Before the dual-write step, a subagent finds every write path to the table (`rg "INSERT INTO refunds|UPDATE refunds"` plus sqlc queries) and returns the list with `file:line`.
4. **Log everything.** Each session's transcript is kept, so "why does `refunds` have two backfills?" has an answer.

**What to check.** `migration_plan.json` matches the git log: every `true` has a commit. A script can check that. No session touches two tables. See [Module 07](../07-loops/README.md) to run this as an unattended loop.

---

## 4. Rolling out the on-call runbook assistant

**Situation.** You built the assistant in `code/` and want it in the `#billing-oncall` Slack channel.

**Naive approach.** Demo it on five questions you wrote yourself, see good answers, and ship.

**AI-native approach.**
1. Collect 50 real questions from the last quarter's pages and Slack threads. Label the chunks that answer each one. Include questions phrased as symptoms ("box out of space") and questions the runbooks don't cover.
2. Run `python retrieval_eval.py` and record recall@5. Look at every miss. The course corpus shows the typical pattern: identifier questions hit, and symptom-phrased questions miss.
3. If symptom misses dominate, add a hybrid leg (embeddings plus rank fusion), or write a "Symptoms" line into each runbook in the words on-callers actually use. Re-measure.
4. Turn on `grounding_check` in production. Any answer with an ungrounded command is replaced by the raw chunks and a note.
5. Track three rates weekly: grounding failures, "Not covered" answers, and thumbs-down. Feed every thumbs-down into the labelled set.

**What to check.** recall@5 on the held-out half of the set (don't tune on all 50). The grounding-failure rate should be near zero and stay there. A rise means the model or the prompt changed. Also, at least some "Not covered" answers: zero means the model is guessing.

---

## 5. "Have we seen this before?" as an episodic memory query

**Situation.** `IdempotencyCacheEvictions` fires at 02:40. The on-caller is new.

**Naive approach.** Paste the alert into a general chatbot. (illustrative) It suggests raising Redis `maxmemory` and switching to `allkeys-lru` "for better cache efficiency". That is exactly the setting that caused INC-6120's duplicate charges.

**AI-native approach.**
1. The assistant's first tool call searches episodic memory, the structured incident records from [07](07-memory-taxonomy.md), by alert name, and finds INC-6120.
2. It retrieves the `redis-evictions` runbook chunks (semantic and procedural memory). The diagnosis chunk says `allkeys-lru` is wrong for this cache.
3. The answer cites both: "Seen before as INC-6120 [episode]. Check the policy: `redis-cli -h idempotency-cache info memory | grep -E "used_memory_human|maxmemory_policy"` [redis-evictions#diagnosis]. After stabilizing, reconcile duplicates [redis-evictions#mitigation]."
4. After the incident, the session writes a new episode record, including `rejected: ["allkeys-lru"]` if anyone proposed it.

**What to check.** The episode search is evaluated like any retriever: recall@k over "past alert to matching incident" pairs. The grounding check passes on the cited commands.
