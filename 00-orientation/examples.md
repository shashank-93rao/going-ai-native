# Examples: orientation in practice

Five Monday-morning scenarios. Each follows *Situation → Naive approach → AI-native approach → What to check*. Model outputs are `(illustrative output)` unless stated otherwise.

---

## 1. The schema migration that wanted to be a loop

**Situation.** `orders-service` stores `shipping_address` as a JSON blob. Product wants it normalized into an `addresses` table. There are 2.1M rows and 37 call sites across 6 services that read the blob.

**Naive approach.** "Claude, migrate shipping_address to a normalized table and update all callers." The agent writes a migration that backfills and drops the column in one step, and updates 31 of the 37 call sites (it missed 6 that build the JSON path dynamically). Staging breaks. The column is already gone in staging, and QA's data with it.

**AI-native approach.**
1. **Score it.** Backfill: resettable (a disposable DB from a snapshot), efficient (minutes on a 50k-row sample), rewardable and faithful if you write a checksum oracle. Call-site updates: rewardable via contract tests, but only for the call sites those tests cover. Drop: irreversible.
2. **Build the oracles first.**
   ```sql
   -- oracle/backfill_check.sql : must return 0 rows
   SELECT o.id FROM orders o
   LEFT JOIN addresses a ON a.order_id = o.id
   WHERE o.shipping_address IS NOT NULL
     AND (a.id IS NULL OR md5(a.canonical_json) <> md5(o.shipping_address::text));
   ```
   ```bash
   # oracle/no_blob_reads.sh : must print nothing. Catches dynamic access the agent might miss
   rg -n --type-add 'src:*.{go,java,kt,py}' -tsrc 'shipping_address' services/ | grep -v '_test\.' | grep -v 'migrations/'
   ```
   Run both against `main` and confirm they fail (2.1M mismatches; 37 hits).
3. **Dial per sub-task** (from [03](03-autonomy-dial.md)):
   - Backfill script: strong oracle, sandboxed, large and mechanical → **loop** against `backfill_check.sql` on a snapshot, with a 20-iteration cap.
   - Call-site updates: strong oracle (`no_blob_reads.sh` plus contract tests), 6 repos → **loop** per repo, with a separate PR each.
   - `DROP COLUMN`: irreversible → **supervised**, run by a human after a week of dual-read in production.
4. Loop prompt (excerpt):
   ```text
   Goal: oracle/no_blob_reads.sh prints nothing for services/billing/ AND `make test` passes.
   Do not edit oracle/ or any *_test file. Read via AddressRepo only.
   If the same test fails 3 iterations in a row with the same error, stop and write BLOCKED.md.
   ```

**What to check.** Did the oracles fail on `main` before the work started? Does the drop sit behind a human approval? Did any loop edit `oracle/`? (`git diff --stat origin/main -- oracle/` should be empty.)

---

## 2. "AI makes us 2x faster" lands in the planning doc

**Situation.** Your director forwards a vendor case study claiming a 2x productivity gain, and asks whether the team should plan Q1 with 2x throughput.

**Naive approach.** Either accept it ("plan for 1.8x to be safe") or dismiss it ("METR showed AI makes you slower"). Both are one-study reasoning.

**AI-native approach.**
1. Run the five-question audit from [04](04-honest-evidence.md): which tasks, which oracle, which outcome variable, who chose, which model generation.
2. Write a one-paragraph reply:
   ```text
   The case study measures PR count on tasks the engineers chose to delegate, with no comparison arm
   and no revert/rework data. That's evidence agents work well on some task class, not a 2x multiplier.
   METR's controlled data shows the effect has moved since early 2025 but is still too uncertain to size
   (2026 CI: -38% to +9% time). Proposal: I run a randomized personal A/B for 6 weeks on our actual
   tickets (00-orientation/05) and we size Q1 from that, with the interval.
   ```
3. Start the log the same day.

**What to check.** Does your reply state what the claim *is* evidence for, not just what it isn't? Did you commit to producing a number with an interval?

---

## 3. The flaky test the agent "fixed"

**Situation.** `TestSettlementIdempotent` in `ledger-service` fails about 1 run in 40. You hand it to an agent.

**Naive approach** (illustrative output):
```text
Agent: The test is flaky due to timing. I added `require.Eventually(..., 5*time.Second, 50*time.Millisecond)`
around the assertion. 50/50 local runs pass.
```
The test is now green, and the race is still in production code. The oracle ("the test passes") was gameable. On the dial, this was a `partial` oracle treated as `strong`.

**AI-native approach.**
1. **Strengthen the oracle first.**
   ```text
   Prompt: Do not modify TestSettlementIdempotent or src/. Write a stress target
   `make stress-settle` that runs it with -race -count=400 -cpu=1,4,8 and exits non-zero on any failure.
   Run it on main and show me it fails.
   ```
   (illustrative output) `--- FAIL: TestSettlementIdempotent (count 173, cpu=8) DATA RACE ... settle.go:88`
2. Now the oracle is faithful: it reproduces the race. The fix becomes a **supervised agent** task. Done-when is `make stress-settle` exiting 0 and no edits under `*_test.go`.
3. Add a Stop hook gate ([02](02-the-leash-moved.md)) that rejects diffs touching the test file.

**What to check.** `git diff origin/main --stat -- '*_test.go'` is empty. The race detector output from step 1 points at the line the fix changed.

---

## 4. Choosing modes for a sprint

**Situation.** Sprint planning, eight tickets. You want to use agents "more", without knowing where.

**Naive approach.** Assign agents to the boring-sounding tickets. Boring is not the same as verifiable: "update the runbook wording" is boring and has no oracle.

**AI-native approach.**
1. Add `oracle:` and `mode:` lines to each ticket, filled in using the [03](03-autonomy-dial.md) table.
2. For each ticket the dial puts at chat or pair, add a sub-ticket: "build the check that would move this right." Those are often the best agent tasks of the sprint.
3. Register all eight in the self-measurement log *before* deciding anything else, then run `assign`. Tasks assigned `no_ai` are done without AI, whatever the dial says. The dial governs *how* you use AI on the `ai` tasks.

**What to check.** Every ticket has an oracle label you could defend. Every loop or scheduled ticket lists its governors. The log has eight `register` events with timestamps before any `start`.

---

## 5. A nightly dependency-bump agent

**Situation.** Thirty services, with Renovate PRs piling up unmerged because each needs someone to run the integration suite and read the changelog.

**Naive approach.** A cron job that runs an agent with your credentials to "merge Renovate PRs that look safe". It merges a minor bump of a JSON library that changed number parsing. Nothing checked `amount` round-tripping.

**AI-native approach.**
1. **Oracle:** each service's contract suite, plus a new golden-file test for money serialization (`testdata/amounts.golden`), confirmed to fail when the parser is swapped.
2. **Dial:** strong oracle, recurring, sandboxed CI runner with no prod credentials → **scheduled**.
3. **Guards:** idempotent runs (the PR number is the bookmark), at most 2 CI rounds per PR (the Stripe cap), and an inbox output rather than auto-merge for anything touching `money/` or `auth/` (medium risk tier). Alert if a run can't fetch the PR list, because a silent run is not a clean run.
4. Output to the inbox:
   ```text
   nightly-bumps 2026-10-19: 11 PRs verified and merged (low tier), 2 awaiting review (medium: money/),
   1 blocked (contract suite red after 2 rounds: PR #4471 jackson 2.19 -> 2.20). (illustrative output)
   ```

**What to check.** Can the job reach anything a mistake would harm? Does each run record what it read? Does the medium tier ever auto-merge? Grep the merge logs for `money/`.
