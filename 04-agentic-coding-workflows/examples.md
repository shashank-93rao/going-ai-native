# Examples: three full sessions and one you shouldn't delegate

Each scenario follows *Situation → Naive approach and what happens → AI-native approach (step by step, with artifacts) → What to check*. Model outputs are marked *(illustrative output)* unless they come from running this module's code. Commands and flags were checked against the Claude Code and Codex docs on 2026-10-19.

---

## Scenario 1: Adding idempotency keys to a payments API (spec-driven)

### Situation

`payments-api` is a Go service on Postgres, 6 replicas, multi-tenant. It exposes `POST /v1/charges`, which calls an external payment service provider (PSP). Last month a mobile client retried on a timeout and two customers were charged twice. That's an incident ticket, a refund and an angry merchant. You need idempotency keys on that endpoint. It touches money, concurrency and a remote side effect, which makes it exactly the kind of change where the agent's plausible defaults are dangerous.

### Naive approach and what happens

```text
add idempotency keys to POST /v1/charges so client retries don't double charge
```

*(Illustrative output.)* About 200 lines: a `Idempotency-Key` header, a `idempotency_keys(key PK, response jsonb)` table, and "look up, else process and store". There's one test that sends the same request twice and checks the second gets the stored response. CI is green. In production it's still wrong. Keys are global, so tenants collide and one tenant can read another's response. Same key with a different amount returns the old response. Two concurrent retries both miss the lookup and both charge. A crash between the PSP call and the store write leads to a second PSP charge on retry. None of this shows up in the single test, because the agent wrote the test for the design it chose.

### AI-native approach

**Step 1: Interview, in a fresh session.**

```text
I want to add idempotency keys to POST /v1/charges in payments-api (Go 1.23, Postgres 16,
pgx, calls the PSP over HTTP via internal/psp). Constraints I already know: multi-tenant
(tenant from JWT `tid`), 6 replicas, endpoint p99 budget 250ms, the PSP accepts its own
Idempotency-Key header and dedupes for 24h.
Interview me in detail using the AskUserQuestion tool. Dig into concurrency, crash
mid-request, retention, what counts as "the same request", and the client contract.
Don't ask obvious questions. Keep interviewing until we've covered everything, then
write SPEC.md using templates/SPEC.md as the structure.
```

The interview transcript is in [03](03-spec-driven-development.md). These are the answers that changed the design: per-tenant keys; 422 on a fingerprint mismatch and 409 while in progress (following the IETF httpapi draft, which is expired at -07, so it's convention, not a standard); a PSP key derived from ours; only terminal outcomes stored; 24 h retention.

**Step 2: The SPEC.md you approve** (after hand edits):

```markdown
# SPEC: Idempotency keys for POST /v1/charges

Status: approved (by S. Rao, 2026-10-19)
Related: INC-2291 (double charge on client retry)

## 1. Problem
Clients retry POST /v1/charges on timeouts. Retries are processed as new charges, so a
timeout followed by a retry can charge twice (INC-2291: 2 customers, EUR 418.00 refunded).

## 2. Goals
- R1: A request with header Idempotency-Key (1-255 chars, printable ASCII) whose (tenant_id, key)
      was completed within 24h returns the stored status and body, byte-identical, without calling the PSP.
- R2: Same (tenant_id, key) with a different fingerprint returns 422 (problem+json, type
      ".../idempotency-key-mismatch") and does not call the PSP.
- R3: Same (tenant_id, key) while the original is in_progress returns 409 with Retry-After: 1.
- R4: Missing header returns 400 for clients with `require_idempotency=true`; otherwise behaves as today.
- R5: The PSP call carries Idempotency-Key = hex(HMAC-SHA256(server_secret, tenant_id || ":" || key)).
- R6: If an in_progress record's lock has expired (process crashed), the next request with that key
      takes over the record (compare-and-set on locked_until) and re-calls the PSP with the same PSP key.
- R7: Records older than 24h are deleted by a batched job (<= 5k rows per batch).

## 3. Non-goals / out of scope
- Idempotency for any endpoint other than POST /v1/charges.
- Changing the PSP client's retry policy or timeouts (internal/psp is read-only for this change).
- Client SDK changes.

## 4. Invariants that must keep holding
- I1: At most one PSP charge per (tenant_id, key) is initiated by us at a time.
- I2: A tenant can never read another tenant's stored response.
- I3: p99 of POST /v1/charges stays under 250ms (one extra indexed write, one read on replay).

## 5. Design
### Interfaces
- Header: `Idempotency-Key: <1-255 printable ASCII>`
- Fingerprint: sha256(method || "\n" || path || "\n" || canonical_json(body))  (keys sorted, no whitespace)
### Data and state
    CREATE TABLE idempotency_keys (
      tenant_id       text        NOT NULL,
      idem_key        text        NOT NULL,
      fingerprint     bytea       NOT NULL,
      state           text        NOT NULL CHECK (state IN ('in_progress','completed')),
      locked_until    timestamptz NOT NULL,
      response_status int,
      response_body   jsonb,
      created_at      timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (tenant_id, idem_key)
    );
    CREATE INDEX idempotency_keys_created_at ON idempotency_keys (created_at);
### Failure and concurrency behaviour
- Claim: INSERT ... ON CONFLICT (tenant_id, idem_key) DO NOTHING RETURNING. Inserted -> we own it.
- Not inserted: SELECT the row. completed -> R1/R2. in_progress and locked_until > now() -> R3.
  in_progress and expired -> UPDATE ... SET locked_until = now() + 30s
  WHERE tenant_id=$1 AND idem_key=$2 AND state='in_progress' AND locked_until < now() RETURNING (R6).
- PSP 5xx or timeout: DELETE the in_progress row (key released), return 502. Terminal outcomes
  (2xx, 4xx validation, PSP decline) are stored as completed.
### Files and modules involved
- migrations/0042_idempotency_keys.sql
- internal/idempotency/ (new): store.go, fingerprint.go, middleware.go
- internal/charges/handler.go (wire the middleware)
- cmd/janitor/ (R7 job)

## 6. Decisions and rejected alternatives
- Postgres over Redis: the charge record is already in Postgres, and we want the claim to be durable.
- Lock lease (locked_until) over advisory locks: survives connection loss, observable in SQL.

## 7. Verification
### Tests that must exist (and fail before the change)
- TestIdem_ReplayReturnsStoredResponse (R1)
- TestIdem_MismatchedBody_422_NoPSPCall (R2)
- TestIdem_ConcurrentSameKey_OnePSPCall: 50 goroutines, same key -> fakePSP.Calls()==1, others 409 (R3, I1)
- TestIdem_CrossTenantSameKey_Independent (I2)
- TestIdem_CrashAfterPSP_TakeoverReusesPSPKey: kill between PSP call and store (R5, R6)
- TestJanitor_DeletesOlderThan24h_InBatches (R7)
### Commands
    make check                                  # vet, lint, unit, ~20s
    go test ./internal/idempotency/... -race -count=1
    make test-integration                       # real Postgres via testcontainers
### Done when
- [ ] all commands above exit 0
- [ ] mutation check: replacing ON CONFLICT DO NOTHING with an upsert makes TestIdem_ConcurrentSameKey fail
- [ ] no files outside the list in 5 changed (git diff --stat main)

## 8. Rollout and rollback
Flag `idempotency.enabled` per tenant. Migration is additive. Rollback = flag off.
Watch: idempotency_replays_total, idempotency_conflicts_total{code="409|422"}, charges p99.

## 9. Open questions
None blocking.
```

**Step 3: Plan, in a fresh session, in plan mode.**

```bash
claude -w idem-keys --permission-mode plan
```

```text
Read SPEC.md and the files it lists. Write plan.md using templates/plan.md. Each phase
covers specific requirement IDs and ends with a command that can fail. Phase 0 adds the
fake PSP with a call counter and the migration. Don't write code yet.
```

The plan.md you approve *(illustrative output, edited)*:

```markdown
# PLAN: Idempotency keys for POST /v1/charges
Spec: ./SPEC.md (R1-R7, I1-I3)     Base commit: 9c41e2a

## Approach
A middleware on POST /v1/charges claims (tenant_id, key) with an INSERT ... ON CONFLICT DO NOTHING,
replays completed records, rejects mismatches and in-progress duplicates, and takes over expired leases
with a compare-and-set UPDATE. The handler passes a derived PSP key. A janitor deletes old rows.

## Phases
### Phase 0: scaffolding (no behaviour change)
- [ ] migrations/0042_idempotency_keys.sql; fakePSP with atomic call counter in internal/psp/psptest
- [ ] Verify: make check && make test-integration
### Phase 1: claim + replay + mismatch (R1, R2, R4)
- [ ] Write TestIdem_ReplayReturnsStoredResponse, TestIdem_MismatchedBody_422_NoPSPCall -> run, confirm FAIL (404/200 vs 422)
- [ ] fingerprint.go, store.go (Claim, Complete), middleware.go
- [ ] Verify: go test ./internal/idempotency/... -race -count=1
### Phase 2: concurrency (R3, I1, I2)
- [ ] Write TestIdem_ConcurrentSameKey_OnePSPCall, TestIdem_CrossTenantSameKey_Independent -> confirm FAIL
- [ ] 409 + Retry-After path
- [ ] Verify: go test ./internal/idempotency/... -race -count=20
### Phase 3: PSP key + crash takeover (R5, R6)
- [ ] Write TestIdem_CrashAfterPSP_TakeoverReusesPSPKey -> confirm FAIL
- [ ] HMAC derivation; lease takeover UPDATE
### Phase 4: janitor (R7)   ### Phase 5: mutation check + diff --stat (Done when)

## Stop and ask a human if
- internal/psp needs any change beyond psptest
- a test outside internal/idempotency or internal/charges must change
- the same verification fails twice after a fix attempt
```

**Step 4: Implement, phase by phase, in a fresh session, with a Stop-hook gate.** To keep the session from declaring victory early, add a Stop hook that runs the fast check. It uses the documented `{"decision": "block", "reason": ...}` output and gives up after 3 blocks, so it can't loop forever (Claude Code's own cap is 8 consecutive blocks):

```json
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command",
    "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/gate.sh" } ] } ] } }
```

```bash
#!/usr/bin/env bash
# .claude/hooks/gate.sh: block "done" until the fast checks pass; at most 3 blocks per session.
INPUT=$(cat)
sid=$(echo "$INPUT" | jq -r '.session_id')
n_file="/tmp/gate-$sid"; n=$(cat "$n_file" 2>/dev/null || echo 0)
[ "$n" -ge 3 ] && exit 0                     # budget spent: let it stop, a human takes over
if out=$(cd "$CLAUDE_PROJECT_DIR" && go test ./internal/idempotency/... -race -count=1 2>&1); then
  rm -f "$n_file"; exit 0
fi
echo $((n+1)) > "$n_file"
jq -n --arg r "Tests failing, fix before stopping:
$(echo "$out" | tail -30)" '{decision: "block", reason: $r}'
```

```bash
claude -w idem-keys
```

```text
Implement Phase 1 of plan.md. Follow red/green: write the phase's tests first, run them,
show me they fail for the reasons stated, then stop and wait for "go".
```

You read the red output, then:

```text
go. Implement only enough to pass Phase 1's tests. Then run the phase's Verify command,
tick the boxes in plan.md and append the evidence to the Progress log. Don't touch internal/psp.
```

Repeat for each phase. `/clear` between phases is fine, because plan.md carries the state.

**Step 5: Validate against the SPEC, in a clean context.**

```text
Use a subagent to review `git diff main` against SPEC.md. For each requirement R1-R7 and
invariant I1-I3, say implemented / not implemented / untested, citing file:line. Check that
nothing outside SPEC section 5's file list changed. Report gaps that affect correctness or a
requirement only, not style.
```

Then do the mutation check from "Done when" by hand, and the review steps in [07](07-reviewing-ai-code-and-when-not-to-delegate.md).

### What to check

- `git diff --stat main` matches SPEC section 5. Here the classic surprise is a "helpful" retry added to `internal/psp`.
- `TestIdem_ConcurrentSameKey_OnePSPCall` fails when you swap `ON CONFLICT DO NOTHING` for an upsert. If it doesn't, the concurrency guarantee is untested.
- `tautology_lint.py` (or your Go equivalent) has no unexplained hits on the new tests.
- The 422 and 409 paths don't call the PSP (fake PSP counter == 0).
- p99 under 250 ms in the integration benchmark, per I3.

---

## Scenario 2: Fixing a flaky Kafka consumer integration test (research-plan-implement + TDD)

### Situation

`LedgerConsumerIT.rebalancePreservesOffsets` (Java 21, Spring Kafka, Testcontainers) fails about 1 in 30 CI runs with `expected: <1000> but was: <1012>`. It's been retried-until-green for three weeks. The team suspects "Testcontainers being slow". You suspect a real duplicate-processing bug that the test is occasionally lucky enough to catch, which would matter, because the ledger write isn't idempotent.

### Naive approach and what happens

```text
LedgerConsumerIT.rebalancePreservesOffsets is flaky, fix it
```

*(Illustrative output.)* The agent sees `Thread.sleep(3000)` and replaces it with Awaitility polling (fine). It then sees the count is sometimes higher than expected and "fixes" the assertion to `assertThat(processed).isGreaterThanOrEqualTo(1000)`. It adds `@RetryingTest(3)` for good measure and reports the test is now stable over 20 runs. All three of Beck's warning signs apply: it looped on symptoms, added things nobody asked for, and weakened the test. The duplicate-processing bug in production is now invisible.

### AI-native approach

**Step 1: Prove it can fail. Measure the flake before anyone touches anything.**

```bash
claude -w ledger-it-flake --permission-mode plan
```

```text
Don't change any code. Run this and report the failure count and the distinct failure messages:
for i in $(seq 60); do mvn -q -Dtest=LedgerConsumerIT#rebalancePreservesOffsets -Dsurefire.rerunFailingTestsCount=0 verify > /tmp/it-$i.log 2>&1 || echo "FAIL $i"; done
```

*(Illustrative output:)* `3 / 60 failed; all: expected <1000> but was <1006..1012>`. The failures are always *over*-counts and never under-counts. That's the first real clue: duplicates, not loss.

**Step 2: Research, in plan mode, using subagents.** Produce `research.md` from [templates/research.md](code/templates/research.md) with the prompt from [02](02-research-plan-implement.md): describe today's behaviour, trace `poll()` to commit including rebalance callbacks, cite file:line, and list unknowns. The key finding *(illustrative output)*:

```markdown
## Summary
Two commit sites: per-batch commitAsync (LedgerConsumer.java:142) and commitAsync inside
onPartitionsRevoked (RebalanceHandler.java:31). The revoke-time commit is asynchronous, so the
partition can be reassigned before it completes; the new owner resumes from the last completed
commit and re-processes up to one batch (max.poll.records=500 -> observed +6..+12 at test volume).
## Test mechanics
LedgerConsumerIT.java:77 starts consumer B after Thread.sleep(3000) to force a rebalance; whether the
in-flight async commit finishes before reassignment depends on timing, hence ~5% failure.
## Unknowns
- Whether LedgerClient.write is idempotent. Not determinable from this repo.
```

You answer the unknown from domain knowledge: it is not idempotent. That makes this a production bug, so you file it as such, with the measured rate.

**Step 3: Plan.** Fresh session, from `research.md`:

```markdown
# PLAN: duplicate processing on rebalance (LedgerConsumer)
### Phase 0: deterministic reproduction
- [ ] New test LedgerConsumerIT#revokeWithInflightCommit_noDuplicates:
      pause the broker-side commit path with a ToxiProxy latency toxic (500ms) on the consumer's
      connection, trigger rebalance by starting consumer B, assert every offset processed exactly once
      (collect (partition, offset) pairs; assert no duplicates). Expect FAIL 10/10.
- [ ] Replace Thread.sleep in the old test with Awaitility (await().atMost(30s).until(...)); no assertion changes.
### Phase 1: fix
- [ ] RebalanceHandler.onPartitionsRevoked: commitSync(currentOffsets, Duration.ofSeconds(5))
- [ ] Verify: new test 10/10 pass; old test 60/60 pass with the loop from Step 1
### Stop and ask if
- the fix seems to require changing the per-batch commit or max.poll.records
- any existing assertion must change
```

**Step 4: Implement with TDD, and lock the tests.** Phase 0 is the red step:

```text
Implement Phase 0 only. Run the new test 10 times and show the result. It must fail
for the stated reason (duplicate (partition, offset) pairs), not for setup errors.
```

*(Illustrative output:)* `10/10 FAIL: duplicate offsets [p0:500..p0:511]`. Now the oracle is deterministic. Turn on the test lock from [04](04-tdd-with-agents.md) (`echo green > .claude/tdd-phase`), then:

```text
go: Phase 1. Change only RebalanceHandler. Then run the new test 10x and the Step 1 loop (60x)
on the old test. Append both counts to the Progress log.
```

**Step 5: Review.** `git diff --stat main` should show `RebalanceHandler.java`, the new test, and the sleep-to-Awaitility change. Then:

```bash
git diff main -- '*IT.java' '*Test.java' | python 04-agentic-coding-workflows/code/tautology_lint.py --diff -
```

That diff has no removed assertions and no new skips. Your remaining question is design: does `commitSync` in the revoke callback risk exceeding `max.poll.interval.ms` under broker slowness? It's bounded by the 5 s timeout you set, which is well under the 300 s default. Note this in the PR.

### What to check

- The failure rate was measured before the change (3/60) and after it (0/60 on the old test, 10/10 → 0/10 on the deterministic one). "Stable over 20 runs" is not evidence for a 1-in-30 flake: at a 3.3% failure rate, 20 clean runs happen about half the time by luck ((1 − 1/30)^20 ≈ 0.51).
- No assertion was weakened and no retry annotation was added (`--diff` lint, plus your eyes).
- The deterministic repro test is kept. It's the regression test for a production bug.

---

## Scenario 3: Migrating 40 call sites with a fan-out script

### Situation

The events platform is retiring `emit_event(topic, entity)`, a fire-and-forget wrapper with no partition key. Its replacement, `publisher.publish(topic, entity, key=...)`, requires a key so that all events for one entity land on one partition, in order. `rg` finds 40 call sites across 40 service modules owned by six teams. Each site needs the right key: the entity's id, not, say, the tenant id. Picking it is a small judgment per site, which is why sed won't do and an agent will.

### Naive approach and what happens

The `xargs -P 8 claude -p ...` one-liner from [06](06-headless-fan-out.md): parallel agents racing on `git commit`, unquoted paths, success taken from the agent's "OK", no canary. If the prompt has a systematic flaw, you find out after 40 runs.

### AI-native approach

**Step 1: Build and test the oracle first.** [`code/check_callsite.py`](code/check_callsite.py) passes only if the file parses, has no `emit_event(`, and every `publish()` has `key=`. Prove it can fail:

```bash
$ python check_callsite.py services/svc_00_order.py; echo $?     # before migration
services/svc_00_order.py: line 8: legacy emit_event() call remains
1
```

In a real repo, add the module's own unit tests to the verify command, e.g. `python check_callsite.py {target} && pytest -q tests/ -k {stem}`. One gotcha: pytest exits 5 when `-k` selects no tests. A module with no tests then shows up as `verify_failed`. That's arguably correct (no test, no verification), but decide it on purpose.

**Step 2: The target list and the prompt.**

```bash
rg -l 'emit_event\(' services/ | sort > targets.txt     # 40 lines
```

`prompt.md`:

```markdown
Migrate exactly one file: the target below. Replace each `emit_event(TOPIC, x)` with
`publisher.publish(TOPIC, x, key=<entity id>)` where <entity id> is the id of the entity the
event is about (usually x["id"]; for *_line_item entities use the parent order's id).
Rules:
- change only the target file; no other edits, no new imports beyond `from events import publisher`
- do not modify tests
- if the right key is unclear, make no change and end your reply with the word FAIL
- otherwise end your reply with OK
If verifier feedback is included below, fix exactly what it reports.
```

**Step 3: Canary, then the full run, with the driver.**

```bash
python fanout.py --targets targets.txt --concurrency 8 --retries 1 --canary 3 --max-failures 5 \
  --agent 'claude --bare -p "$(cat prompt.md)
Target: $FANOUT_TARGET
Verifier feedback (may be empty): $(cat "$FANOUT_FEEDBACK")" \
    --allowedTools "Read,Edit" --permission-mode dontAsk --output-format json --max-budget-usd 0.50' \
  --verify 'python check_callsite.py {target} && pytest -q tests/ -k {stem}' \
  --on-success 'git add {target} && git commit -qm "events: migrate {name} to publisher.publish"' \
  --results results.jsonl
```

Each part of that command maps to a control:

- `--canary 3`: the first three run first. Read their diffs (`git show HEAD~2..HEAD`). If any canary fails, the batch stops, and you fix `prompt.md`, not the files.
- `--on-success ... git commit` runs under one lock, so there's never an `index.lock` race.
- The agents can only `Read` and `Edit`. They can't commit, push or run arbitrary shell.
- `--max-budget-usd 0.50` caps each invocation, and `total_cost_usd` lands in `results.jsonl`.

To see the same mechanics offline, with four planted failures, run `python migrate_demo.py`. Actual output (fake agent):

```text
agent_failed   attempts=1 claimed_ok=False svc_05_shipment.py  <- agent exited non-zero / is_error
verify_failed  attempts=2 claimed_ok=True svc_12_customer.py  <- services/svc_12_customer.py: syntax error at line 8: '(' was never closed
ok             attempts=2 claimed_ok=True svc_20_customer.py  <- recovered after verifier feedback
verify_failed  attempts=2 claimed_ok=True svc_33_payment.py  <- services/svc_33_payment.py: line 8: legacy emit_event() call remains
{
  "targets": 40,
  "by_status": {"ok": 37, "agent_failed": 1, "verify_failed": 2},
  "claimed_ok_but_not_ok": 2,
  "needed_retry": 1,
  "cost_usd": 0.43,
  ...
}
```

**Step 4: Handle the residue.** Three targets need a human:

```bash
jq -r 'select(.status != "ok") | [.status, .target] | @tsv' results.jsonl
```

For each one, read `verify_tail`. If the cause is shared (e.g. all three are `*_line_item` modules), fix `prompt.md` and rerun only those with `--resume`. The 37 passing targets are skipped, because their last record is `ok`:

```bash
python fanout.py --targets targets.txt --resume --results results.jsonl ... (same flags)
```

Otherwise, fix them by hand. Three files is not worth another prompt iteration.

**Step 5: Review at batch scale.** You won't read 40 diffs closely. Sample instead, and check the aggregate:

- Read the 3 canary diffs and 3 random others in full.
- `git diff main --stat` shows 40 files changed and nothing outside `services/`.
- `git diff main | grep '^+.*key=' | sed 's/.*key=//' | sort | uniq -c` shows the distribution of chosen keys. Any `key=x["tenant_id"]` is a wrong key that the verifier can't see.

### What to check

- The verifier failed on an unmigrated file before the run (oracle can fail).
- `claimed_ok_but_not_ok` is reported and every one of those targets is explained.
- Commits came only from `--on-success`. `git log --format=%s main..` gives 40 uniform messages.
- The key distribution check shows no tenant or constant keys. This is the semantic error the AST verifier can't catch, so it's yours.

---

## Scenario 4 (short): The change you shouldn't delegate

### Situation

It's 02:10. `ledger-writer` consumer lag is climbing at 50k messages/minute after a deploy, and the runbook says roll back.

### Naive approach and what happens

```text
consumer lag is spiking after the deploy, investigate and fix
```

The agent starts reading the diff, forms a hypothesis about `max.poll.records`, and proposes a config change. Twenty minutes pass. The lag is now 1M messages, and the rollback you knew how to do in 90 seconds still hasn't happened.

### AI-native approach

1. **You** run the runbook rollback: known, verified, reversible.
2. In parallel, a read-only agent does triage *(the same `--bg` pattern as in [05](05-parallel-worktrees-background-cloud.md))*:

   ```bash
   claude --bg --name lag-triage "Read-only. Compare deploy 4be1c09..a17f3d2 for changes to the consumer
   path, then summarize consumer logs from the last 30 min (logs/ledger-writer/*.log). Write
   docs/incidents/2026-10-19-lag.md with a timeline and ranked hypotheses with evidence. No code changes."
   ```
3. After mitigation, the bug fix goes through scenario 2's workflow, with a reproduction first.

### What to check

- Time-to-mitigate wasn't spent waiting on an agent.
- The triage report's hypotheses cite log lines and diff hunks, so you can verify each one in seconds.
- The rule you apply next time: agents do read-only triage during incidents, and humans do the known mitigation.
