# 07: Reviewing AI-written code, and knowing when not to delegate

## The idea

Two judgment calls stay with you however good the agent gets. The first is **whether a change is right**: review. The second is **whether to delegate at all**. Both answer the same question as the course thesis: what can be checked here, and by whom?

Review of agent code differs from review of human code in one structural way. A human author's mistakes are correlated with their understanding, so a confident, clean diff is usually a sign they understood the problem. An agent's diffs are uniformly confident and clean, whether or not it understood. **Surface quality carries no signal.** Your review has to go where the agent's errors actually live: design decisions, invariants, scope, and the tests themselves.

## Why it matters

- Mitchell Hashimoto: "Please don't ever ship AI-written code without a thorough manual review" ([Hashimoto, "Vibing a Non-Trivial Ghostty Feature"](https://mitchellh.com/writing/non-trivial-vibing)). Geoffrey Huntley takes the other side: "If humans eyeballing code were sufficient engineering to stop bugs, we'd never have had any defects", so verification must be automated ([Huntley, "nobody should type code by hand anymore"](https://ghuntley.com/agency/)).
- Anthropic's Claude Code team reports doing both. Most review moved *before* the PR (a runnable check, then a fresh-context review subagent), and human approvals are set by **risk tier**: low-risk changes need 0 humans, medium need 1, high need 2. An agent's approval never counts as a human's. They report that merged PRs more than doubled while the revert share fell by more than 40% ([Claude blog, "How the Claude Code team does code review"](https://claude.dev/blog/solving-code-review-at-anthropic/), 2026-10). Those are one team's reported figures.
- METR's 2025 randomized trial found experienced open-source developers took **19% longer** with AI tools on their own mature repos, while believing afterwards they had been sped up by about 20% ([METR, 2025-07-10](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)). METR now marks those results as out of date, and its 2026 follow-up suggests speedups are likely now but hard to measure ([METR, 2026-02-24](https://metr.org/blog/2026-02-24-uplift-update/)). The durable lesson is the perception gap: **your sense of whether delegation helped is not evidence.**

> **Course stance (gap analysis):** risk-tiered review. Automated verification decides most low-risk changes. Humans review intent, invariants and tests on the rest. And measure your own productivity rather than trusting the feeling ([Module 00](../00-orientation/README.md), [Module 17](../17-ai-native-engineer-and-team/README.md)).

## How to review an agent's diff

### Review in this order (leverage first)

1. **The spec and plan** ([02](02-research-plan-implement.md), [03](03-spec-driven-development.md)). Was the right thing built? Most of the leverage is here.
2. **The tests.** Can each one fail? Does it test behaviour through a real boundary? Horthy: "I still read the tests pretty carefully."
3. **Scope.** Compare the files in the diff with the plan's "files expected to change". Each file outside that list needs a reason.
4. **Invariants.** Walk the diff against your invariants: ordering, idempotency, transactional boundaries, auth, backward compatibility.
5. **The implementation.** Skim for the agent-specific smells below.

### Agent-specific smells

| Smell | Example | Why agents do it |
|---|---|---|
| Plausible-but-wrong identity/key | Joining payments to users by email (Karpathy's MenuGen bug); `RemoteAddr` as tenant | Picks the first identifier it finds |
| Unrequested functionality | New config flags, "also supports X" | Beck's warning sign #2. Optimizes for apparent helpfulness |
| Defensive sprawl | try/except around everything, fallback defaults that hide failures | Avoids visible errors, which reads to it as success |
| Check-then-act races | `SELECT` then `INSERT` without a constraint or lock | Sequential-looking code passes single-threaded tests |
| Duplicated helpers | A new `retry()` next to the existing `backoff.Retry` | Didn't search, or the search hit context limits |
| Test-shaped code | Special cases that match test inputs | The anti-hardcoding prompt exists for this ([04](04-tdd-with-agents.md)) |
| Silent contract changes | A changed JSON field name, status code or default | Doesn't know who consumes it |
| Lockfile / dependency churn | New dependency, `go.sum` or `package-lock.json` changes | Reached for a library instead of the existing utility |
| Disarmed tests | `skip`, `xfail`, weakened asserts, deleted cases | Beck's warning sign #3 |

### Tautological tests: the catalog

A tautological test passes whatever the implementation does. Agent-written tests produce them at scale, and they inflate coverage while checking nothing. OpenAI's guidance names one form: tests "that mirror the implementation" ([OpenAI prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance)).

| Pattern | Shape | Fix |
|---|---|---|
| Asserts the mock | `store.get.return_value = X; ...; assert resp == store.get.return_value` | Use a real or fake store, and assert on observable effects |
| Oracle from implementation | `assert fee(x) == _compute_fee(x)` | Literal expected values from the spec |
| Identical sides | `x = f(); assert x == x` | Delete it |
| No assertion | Calls the function, asserts nothing | Assert the effect |
| Swallowed | `try: assert ... except AssertionError: pass` | Remove the try |
| Mocked SUT | `patch("svc.charge")` in `test_charge` | Patch dependencies, never the subject |
| Disarmed | `@pytest.mark.skip("flaky")` added in the same PR | Fix the flake or quarantine it with a ticket |

[`code/tautology_lint.py`](code/tautology_lint.py) flags the first five with AST heuristics and scans diffs for removed asserts and new skips. It's a triage tool, not a verdict. See the worked example for a false positive.

The strongest single check for whether a test can fail is **mutation**: break the implementation on purpose, and see whether any test fails. Mutation tools exist for most languages (mutmut for Python, PIT for Java, go-mutesting for Go). Or ask a second session to "introduce one plausible bug in `idempotency.go` and tell me which test catches it". If none does, you have a tautology.

### The clean-context reviewer

Have a fresh context review the diff against the spec. It "sees only the diff and the criteria you give it, not the reasoning that produced the change" ([Claude Code docs](https://code.claude.com/docs/en/best-practices)). The docs prompt:

```text
Use a subagent to review the rate limiter diff against PLAN.md. Check that
every requirement is implemented, the listed edge cases have tests, and
nothing outside the task's scope changed. Report gaps, not style preferences.
```

The docs also warn: "A reviewer prompted to find gaps will usually report some, even when the work is sound... Chasing every finding leads to over-engineering." Tell it to flag only gaps that affect correctness or stated requirements. [`code/diff_reviewer.py`](code/diff_reviewer.py) also enforces this in code: it drops style findings, and drops any finding whose quoted evidence doesn't appear in the diff. Claude Code also ships `/code-review` for a fresh-subagent correctness pass.

## When not to use an agent

> **Synthesis:** delegate in proportion to how cheaply you can verify the result, discounted by how much it costs you not to understand it.

| Situation | Delegate? | Why |
|---|---|---|
| A crisp oracle exists (tests, compiler, schema, benchmark) and the task is bounded | Yes, and consider fan-out | This is where reported gains concentrate: migrations, ports, upgrades |
| You can't say how you'd check the result | **No**, or only for research | "You can't delegate what you can't verify" ([Eugene Yan](https://eugeneyan.com/writing/working-with-ai/)) |
| The change is a one-liner you already know | No | Prompting plus review costs more than typing it |
| Active incident, mitigation step | Usually no for the action; yes for read-only triage | Runbook actions are known and time-critical. An agent's exploration adds latency and risk. Let it read logs in parallel |
| You need to *own* this code deeply (core consensus path, new domain you must learn) | Use it as a tutor, not an author | "You can outsource your thinking, but you can't outsource your understanding" ([Karpathy, Sequoia Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)) |
| Off-distribution code (novel algorithms, unusual DSLs) | Test it first with a scout | Karpathy found agents not net useful on nanochat in 2025 ([Dwarkesh interview](https://www.dwarkesh.com/p/andrej-karpathy)) |
| The agent would combine private data, untrusted input and an outbound channel | Not without containment | The lethal trifecta ([Module 16](../16-security-and-containment/README.md)) |
| Ambiguous requirements with real stakeholders | Interview *yourself* first | SDD interview ([03](03-spec-driven-development.md)), then decide |

## Worked example: reviewing the idempotency PR

The agent's PR for scenario 1 ([examples.md](examples.md)) is green in CI. Here is the review.

**The bad review.** "LGTM, tests pass, nice clean code." *(This is the trust-then-verify gap.)*

**The good review.** Step 1: scope. `git diff --stat main` shows `internal/psp/client.go` changed. That file isn't in the plan, and the spec lists "changing the PSP client's retry policy" as a non-goal. The agent added a retry on 5xx inside the PSP client. Combined with the handler's own retry, that's up to 9 PSP calls per request, each with the same PSP idempotency key. Safe only if the PSP dedupes perfectly. Revert, and point at the non-goal.

Step 2: tests. Run the linter on the new test file. Actual output (paths shortened):

```text
test_idempotency.py::test_replay_returns_stored_response:9: [asserts-mock-return] compares against a mock's return_value: this tests the mock
test_idempotency.py::test_fingerprint_stable:14: [oracle-from-impl] expected value is computed by the code under test; use a literal
test_idempotency.py::test_concurrent_same_key:18: [swallowed] assertion inside try/except that swallows the failure
```

Triage each one:

- `asserts-mock-return`: a real problem. The test passes even if `handle_charge` ignores the store. Replace it with a fake store and assert `psp.calls == 1` across two requests.
- `oracle-from-impl`: **a false positive.** `fingerprint(body) == fingerprint(reordered body)` is a *metamorphic* property (order independence), which is a legitimate test. Keep it, and add one literal-hash test so a change to the canonicalization is visible.
- `swallowed`: a real problem, and the worst kind. The "concurrency" test can never fail. Rewrite it with 50 goroutines and a counting fake PSP, per the SPEC's done-when.

Step 3: mutation spot check. Ask a fresh session: "In internal/idempotency/store.go, change `ON CONFLICT DO NOTHING` to an upsert, and run the tests." All tests still pass. That proves the concurrency guarantee is untested, so it goes into the review as the blocking comment.

**Why the second review works.** It spent its minutes on scope, tests and one mutation, the places agent errors live. It ignored the clean surface of the code.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Line-by-line review of a big agent diff | You approve long diffs faster than short ones. Switch to the leverage order above. |
| Coverage as evidence | Coverage went up while mutation survivors stayed the same. Spot-check with a mutation. |
| Chasing every reviewer finding | Follow-up commits add abstractions nobody asked for. Restrict the reviewer to correctness and requirements. |
| Treating a linter hit as a verdict | You deleted a valid metamorphic test. Triage each hit. |
| Delegating because it feels faster | No measurement. Time a few comparable tasks both ways (METR's perception gap). |
| Agent approval counted as review | A merge with only bot approvals on a high-risk path. Encode tiers in CODEOWNERS and branch protection. |

## In your day job

- Review in leverage order: spec and plan, tests, scope (`git diff --stat` vs. the plan), invariants, then code.
- Run `tautology_lint.py` (or an equivalent for your language) and `--diff` on agent PRs as a pre-review step, and triage the hits.
- Do one mutation spot check on any agent PR that claims a concurrency or idempotency guarantee.
- Before delegating, say the verification out loud: "I'll know it's right because ___." If the blank is empty, don't delegate the write.
