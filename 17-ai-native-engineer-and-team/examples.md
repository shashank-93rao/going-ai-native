# Examples: module 17

Five scenarios from a team that runs `ledgerd`, a Go double-entry ledger replicated with Raft across five voters, with Postgres for read models and a Kafka feed to downstream consumers. All artifacts referenced here are in [code/](code/).

---

## Scenario 1: Writing REVIEW.md for a Raft-replicated ledger

**Situation.** The team turned on a machine reviewer for every PR. After two weeks, engineers are ignoring it: it posts 8 to 12 comments per PR, mostly naming and comment wording, and it once confidently flagged a "missing lock" in a function that runs on a single goroutine by design.

**Naive approach and what happens.** Someone adds a line to the reviewer's prompt: "Only report important issues." Comment volume drops, but so does recall. The model follows the instruction literally and self-censors, and the next real bug (a ReadIndex read served by a follower without checking the leader's commit index) goes unreported, because the reviewer was unsure whether it counted as "important".

**AI-native approach.**
1. The code owners write [`REVIEW.md`](code/templates/REVIEW.md). Its core is a section that says what failure looks like *in this repo*:
   ```markdown
   ## What failure looks like here
   Report these as **Important**. Each needs a file, a line, and the interleaving or input that breaks it.
   - **Lost or duplicated writes.** A posting acknowledged to a client that is not durable on a quorum, or applied twice for one idempotency key.
   - **Raft safety violations.** Voting twice in a term, granting a vote before `votedFor` is persisted, committing an entry from a previous term by counting replicas, or a leader serving reads without a lease or ReadIndex.
   - **Durability ordering.** Any reply sent before `fsync` returns. Any `go` statement in front of a storage write on the request path.
   ```
2. It says what doesn't count (style, because `gofumpt` and `golangci-lint` already run; speculative refactors; guesses from a function's name), sets a nit cap of 3, and lists skip paths (`*.pb.go`, `vendor/*`).
3. It requires evidence: `file:line`, the quoted line, and for concurrency findings, the two operations and the order that breaks.
4. The reviewer prompt is changed to *report everything with a category and severity*, and filtering moves into code: [`verifier_vote.py`](code/verifier_vote.py) drops style clusters and anything without file-and-line evidence, honours the skip paths parsed from REVIEW.md, and posts only majority findings.
5. Every week, the owners look at findings that repeat. "Unchecked error from `Close()`" appeared nine times in a week, so it became an `errcheck` lint rule and was removed from the reviewer's concern.

**What to check.**
- Comments per PR and the author-response split (fixed / wrong / intentional / didn't matter) before and after. You want fewer comments *and* a higher "fixed" share.
- Recall on the incident eval set ([exercise 3](exercises.md#exercise-3-build-a-reviewer-eval-from-incident-prs)) did not drop.
- `test_templates.py` keeps REVIEW.md under 600 words and checks that its required sections exist.

---

## Scenario 2: A risk-tier table for a distributed-systems repo

**Situation.** The team's implicit policy is "one approval for everything, and people look harder at migrations". Agent PR volume has tripled. Reviewers are spending as long on README fixes as on replication changes, and two risky changes were approved in under ten minutes last month.

**Naive approach and what happens.** Leadership mandates two approvals on every PR. Wait time doubles, people start approving in batches, and the two-approval rule becomes two rubber stamps. Throughput falls and nothing gets safer.

**AI-native approach.** Write the tier table as policy, then encode it.

| Change type | Example path or pattern | Tier | Human approvals | Verifiers | Round cap | Owners | Why |
|---|---|---|---|---|---|---|---|
| Docs, runbooks | `docs/*`, `*.md` | Low | 0 (trusted authors) | 3 | 3 | - | Fails by lying; machine checks claims against code |
| Test additions | `*_test.go` | Low | 0 | 3 | 3 | - | Verified by running them |
| Test weakening | removed `require.`/`func Test`, added `t.Skip(` | Medium | 1 | 3 | 3 | @ledger-team | Classic agent cheating signal |
| Feature flag flip | `config/flags/*.yaml` | Medium | 1 | 3 | 3 | @ledger-oncall | Reaches prod without a deploy |
| Replication or timing config | `config/*` + `replication_factor`, `quorum`, `election_timeout` | High | 2 | 5 | 2 | @consensus-owners | Changes safety and liveness |
| Additive migration | `migrations/*.sql` (nullable column, `CREATE INDEX CONCURRENTLY`) | Medium | 1 | 3 | 3 | @data-owners | Check backfill and rollback |
| Destructive or locking migration | `DROP`, `RENAME`, `SET NOT NULL`, non-concurrent index | High | 2 | 5 | 2 | @data-owners | Irreversible or blocks writes |
| Consensus code | `internal/raft/*.go` | High | 2 | 5 | 2 | @consensus-owners | Bugs show as split brain, rarely in CI |
| WAL or any fsync path | `internal/wal/*`, `.Sync()`, `O_DSYNC` anywhere | High | 2 | 5 | 2 | @storage-owners | Durability ordering |
| Idempotency handling | `internal/api/*` + `idempotency_key`, `dedup` | High | 2 | 5 | 2 | @ledger-team | A bug double-posts money |
| CI workflows | `.github/workflows/*` | Medium, always human | >= 1 | 3 | 3 | @platform | CI is the verifier |
| Agent instructions | `CLAUDE.md`, `REVIEW.md`, `.claude/*` | Medium, always human | >= 1 | 3 | 3 | @ledger-team | Changes what agents are told |
| Anything else | no rule matches | Medium (default) | 1 | 3 | 3 | - | Fail safe |

Encoded in [`data/review_policy.json`](code/data/review_policy.json) and run by [`review_router.py`](code/review_router.py). Running it over the sample diffs (actual output, abbreviated to `tier humans verifiers owners`):

```text
ci_workflow.diff            medium 1 3 ['@platform']
docs_only.diff              low    0 3 []
flag_config.diff            medium 1 3 ['@ledger-oncall']
migration_additive.diff     medium 1 3 ['@data-owners']
migration_destructive.diff  high   2 5 ['@data-owners']
raft_election.diff          high   2 5 ['@consensus-owners']
replication_config.diff     high   2 5 ['@consensus-owners']
test_weakening.diff         medium 1 3 ['@ledger-team']
```

Escalations on top: a low-tier diff over 400 changed lines becomes medium, and an author outside the owning team never gets the zero-human path. A model classifier may raise any tier and never lower it.

**What to check.**
- Run the router over the last 200 merged PRs and compare its tier with how much review each actually got. Every disagreement is a policy conversation.
- Track revert rate per tier monthly. If low-tier reverts rise, a low rule is too broad.
- The property test in `test_review_router.py`: adding a file to a diff never lowers its tier.

---

## Scenario 3: A 90-day team rollout

**Situation.** A director asks the senior engineer to "roll out agents to the ledger team this quarter". Eight engineers, adoption ranging from "daily" to "never".

**Naive approach and what happens.** Licences for everyone, a lunch-and-learn, and a dashboard of sessions per engineer. Usage goes up. Two months in, the change fail rate on consensus code has doubled, nobody can say whether anything got faster, and the engineers who were skeptical feel vindicated.

**AI-native approach.** A phased rollout where each phase has an exit criterion, and the riskiest paths get agents last.

| Phase | Days | Do | Exit criterion |
|---|---|---|---|
| 0. Baseline | 1-14 | Pull 2 quarters of lead time, change fail rate, rework rate and revert rate per task class. Start logging every agent run (owner, class, outcome, cost). Inventory existing personal agent use and credentials. | Baseline table exists with CIs. Every agent token maps to an owner. |
| 1. Guardrails first | 8-30 | Merge REVIEW.md, tier policy and router (CI check that labels PRs with their tier). Branch protection: agent approvals don't count. PR template: Testing / Risk / How to revert. Build the reviewer eval set from 10 past incident PRs. | Router labels 100% of PRs. Reviewer baseline recall measured on the eval set. |
| 2. Mechanical work | 20-45 | Agents first for dependency bumps, lint fixes, codemods, flaky-test triage (report-only). Stop-hook gate: build, `-race` tests. Budgets: 2 CI rounds, $ cap per run. | Mechanical lead time vs baseline, with CI. Zero reverts attributed to low-tier agent PRs, or the rule that allowed them is tightened. |
| 3. Bugs and features | 40-70 | Spec-first workflow for features ([module 04](../04-agentic-coding-workflows/README.md)). Explain-it-back for high-tier PRs. ADRs for decisions others will copy. Promote the flaky-test schedule from report-only to PR mode if its reports were >= 80% useful. | Explain-it-back present on all high-tier PRs. Per-class metrics reported. |
| 4. Critical path, carefully | 60-85 | Agents for research, tests and fault-injection harnesses in Raft and WAL code. Core changes stay human-written or pair-written. A Jepsen-lite linearizability check in CI. | Linearizability check in CI. Change fail rate on critical-path code at or below baseline. |
| 5. Review and decide | 80-90 | Write-up: per-class results with intervals, cost per merged change, reviewer recall, incidents. Propose next quarter's policy. | A decision document reviewed by the team and the director. |

Weekly: a 20-minute review of the agent inbox, budget stops and any PR past its round cap.

**What to check.**
- Each phase's exit criterion was met before the next phase's risky part started. Phases overlap on purpose, but phase 4 never starts before the phase 1 guardrails exist.
- No usage metric appears in the final write-up as evidence of value.
- The skeptics were consulted on the critical-path phase. They often know where the bodies are buried.

---

## Scenario 4: The agent PR that passes CI and is wrong

**Situation.** A nightly agent was asked to fix the flaky `TestPostingIsIdempotent`. Its PR ([`test_weakening.diff`](code/data/diffs/test_weakening.diff)) is green:

```diff
 	first := svc.Post(ctx, req)
 	second := svc.Post(ctx, req)
-	require.Equal(t, first.ID, second.ID)
-	require.Equal(t, 1, store.CountPostings(req.IdempotencyKey))
+	t.Skip("flaky under -race; revisit")
```

This is what Spotify calls its most serious error, a PR that passes CI but is functionally incorrect, and the third of Kent Beck's warning signs: cheating on tests.

**Naive approach and what happens.** The PR touches only a test file, so a path-only rule would call it low tier, and it auto-merges. The idempotency test was flaky because of a real race in the dedup path. That race is now unguarded.

**AI-native approach.**
1. The router's `test-weakening` rule matches removed `require.` lines and an added `t.Skip(`, so the PR is routed medium with `@ledger-team` as owner, not low.
2. The schedule's gate (from [concept 04](04-team-operating-model.md)) forbids `t\.Skip\(` in agent diffs, so in the improved setup this PR never opens. The agent instead files a question in the inbox with the failing stack trace.
3. The human fix starts from the race, not the test.

**What to check.** Search the last quarter's merged PRs for added `t.Skip(`, removed assertions or removed `-race` flags. Each one is either justified in the PR description or a finding.

---

## Scenario 5: The machine reviewer loses quorum

**Situation.** After a model upgrade, the reviewer's JSON output changes shape: it wraps findings in prose. Two of three reviewers' responses no longer parse.

**Naive approach and what happens.** The review bot treats unparseable output as "no findings" and posts "0 findings. Nothing to fix." on every PR for a day. Humans, trained to trust the bot's clean bill on low-tier PRs, approve faster. A low-tier change that the reviewer would have flagged merges.

**AI-native approach.** `verifier_vote.py` treats malformed output as an *abstention*. When the reviewers that answered can't form a strict majority of the configured N, the run is **degraded**, and the comment says so:

```text
Machine review DEGRADED: 2 of 3 reviewers returned unusable output. Treat this PR as unreviewed by machine; route to a human.
```

Policy (AGENT_POLICY.md section 2) says a degraded review means the PR is treated as having no machine review, so low-tier PRs need a human until it recovers. It is the same rule as a quorum read that can't reach a majority: return an error, not an empty result.

**What to check.**
- Alert on the degraded rate. Any non-zero rate after a model or prompt change blocks that change until fixed.
- Every reviewer change (model, prompt, tool) runs against the incident eval set before rollout, as Anthropic does daily. Treat reviewer changes as deploys ([module 15](../15-observability-and-production/README.md)).
