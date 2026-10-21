# AGENT_POLICY.md: ledgerd team

How this team runs coding agents. It is a policy, not a guide: each rule says who
owns it and how it is enforced. A rule with no enforcement is a wish; mark it as such.

Version: 1. Owner: @ledger-tech-lead. Review: every quarter, and after any agent-caused incident.

## 1. Ownership
- **Every agent run has a named human owner**: the person who launched it, or the owner of
  the schedule that launched it. The owner is the author of record of the PR.
  *Enforced by:* the PR bot refuses PRs from agent identities that have no `Owner:` trailer.
- The owner must be able to explain the change without the agent. See section 5.
- An agent's approval never counts as a human approval. *Enforced by:* branch protection
  counts only human accounts in the approver group.
- Approvals cover one commit. A new commit needs a new approval unless it was produced by
  a verified mechanical step (rebase with no conflicts, formatter).

## 2. Review tiers
Review is routed by `review_router.py` with `data/review_policy.json`. A model classifier may
raise the tier and never lower it.

| Tier | Human approvals | Machine verifiers | Round cap |
|---|---|---|---|
| Low | 0 (trusted authors only) | 3 | 3 |
| Medium | 1 | 3 | 3 |
| High | 2, including one owner | 5 | 2 |

- Paths marked always-human (CI workflows, CLAUDE.md, REVIEW.md, `.claude/`) need a human at any tier.
- After the round cap, the reviewer stops and asks the owner to rethink the approach.
- If machine review is degraded (most reviewers returned unusable output), the PR is treated as having no machine review.

## 3. What agents may do unattended
| Work type | Allowed unattended? | Gate before a PR opens |
|---|---|---|
| Dependency bumps, lint fixes, flaky-test triage reports | Yes | build, unit tests, `-race` |
| Ports and migrations with a conformance suite | Yes | the conformance suite |
| New features | No, interactive only | spec reviewed by a human first |
| `internal/raft`, `internal/wal`, `migrations/` | No | owner pairs on the plan |
| Anything touching production credentials | Never | n/a |

## 4. Budgets
- Per run: 2 CI rounds maximum (after Stripe's minion limit), 60 minutes wall clock, a token budget set per task class.
- Per engineer: a monthly spend cap. The team lead sees the spend dashboard weekly.
- Over budget means pause and notify the owner, not kill silently and not continue.
- Spend is reported per merged PR and per task class, not per engineer leaderboard.

## 5. Shared understanding
- Any PR over 200 changed lines in a high-tier path needs an "explain it back": the owner writes,
  without the agent, three sentences on what changed and what would break if it were wrong.
- Decisions that others will copy get an ADR in `docs/adr/`. Agents may draft it. A human signs it.
- PR descriptions state what was verified and how ("ran `make jepsen-lite`, 0 anomalies in 200 ops").

## 6. Inbox and on-call
- Background agents report to the team agent inbox, never to direct messages. Each item is
  one of: notify, question, review.
- Inbox items have an SLO: questions answered within one working day; stale items auto-close.
- The on-call engineer owns agent runs that break main or page anyone. They can disable any
  schedule with one flag (`agents.enabled=false`), without a deploy.

## 7. Measurement
- Guardrails: change fail rate, revert rate, incidents attributed to agent-authored changes.
- Throughput: lead time for changes, and merged PRs per task class.
- Not used for evaluating people: PR counts, lines of code, tokens spent, "% written by AI".

## 8. Incidents
- Every incident review asks: which layer should have caught this (spec, verifier, machine review,
  human review, rollout)? The fix goes into that layer.
- Each incident-causing PR is added to the reviewer eval set within a week.
