# 04: Agentic coding workflows
> After this module you can take a real change from ticket to merged PR with Claude Code or Codex, using explore-plan-implement-verify, research-plan-implement, spec-driven development and agentic TDD. You'll know how to run parallel, background and headless agents safely, how to review what they produce, and when not to use one.

## Why this matters

The difference between engineers who get leverage from coding agents and engineers who get slop is mostly **workflow**, not prompting skill. Same model, same repo, same ticket. The engineer who reads first, plans in a reviewable artifact and hands the agent a check it can run gets a correct diff. The one who types "fix the flaky test" gets a weakened assertion and a green build.

The stakes are highest in the kind of code you write. Agents fill gaps with plausible defaults: a global idempotency key instead of a per-tenant one, `commitSync` in the wrong place, a key that preserves no ordering. They then write tests that confirm those defaults. CI goes green, and the bug ships with a test suite vouching for it. Every workflow in this module exists to move a human decision, or an automatic check, in front of the step where that happens.

The workflows also decide how much autonomy you can afford. With a per-target verifier you can fan one prompt out across 40 files and walk away. Without one, a single session needs your eyes on every step. That's the course thesis in its most practical form: **autonomy scales with verifiability**.

## The distributed-systems anchor

**Change management, the RFC process.** Research is the design review of the current system ("how does it work today, with evidence"). The SPEC or plan is the RFC. Implementation is the rollout. Verification is the health check, the canary and the rollback trigger. Fan-out is a batch job with a worker pool, a canary, a circuit breaker and a single writer for shared state. Parallel sessions are processes that each need their own resources and their own lock domain.

**Where the analogy breaks.**
- The "engineer" executing your RFC is nondeterministic, has no memory between sessions, and is uniformly confident whether right or wrong. You can't calibrate trust from tone the way you do with a colleague.
- The engineer is cheap. Throwing away a wrong implementation and rerunning from a better spec is often faster than fixing it, which is never true of a human rollout.
- Its working memory (the context window) degrades as it fills. So you design the process around small, fresh contexts with durable artifacts, closer to a stateless worker reading a WAL than to a long-lived service.

## Learning goals
- [ ] Run explore → plan → implement → verify in Claude Code (plan mode, `Ctrl+G`) and Codex, choosing the right verification gate
- [ ] Run research-plan-implement with fresh sessions per phase and produce a reviewable `research.md` and `plan.md`
- [ ] Use the interview prompt to produce a SPEC.md whose requirements map to named tests, and validate the diff against it
- [ ] Do TDD with an agent: an observable red step, test files locked during green, Beck's three warning signs as interrupts
- [ ] Run parallel sessions in git worktrees without shared ports or databases, and dispatch background and cloud sessions
- [ ] Fan a change out with `claude -p` / `codex exec` through a driver with bounded concurrency, a canary, a breaker and per-target verification
- [ ] Review an agent's PR in leverage order and identify tautological tests
- [ ] Decide when *not* to delegate, and measure whether delegation helped you

## Reading order
1. [01-explore-plan-implement-verify.md](01-explore-plan-implement-verify.md): the base loop, plan mode, verification gates, and the over-verification tension
2. [02-research-plan-implement.md](02-research-plan-implement.md): fresh context per phase, the leverage hierarchy, the parquet-java failure
3. [03-spec-driven-development.md](03-spec-driven-development.md): interview → SPEC.md → plan → implement → validate → replan
4. [04-tdd-with-agents.md](04-tdd-with-agents.md): Beck's augmented coding, red/green, a hook that locks tests
5. [05-parallel-worktrees-background-cloud.md](05-parallel-worktrees-background-cloud.md): worktrees, the single-writer rule, `--bg`, `--cloud`
6. [06-headless-fan-out.md](06-headless-fan-out.md): `claude -p`, `codex exec`, and the fan-out driver's reliability controls
7. [07-reviewing-ai-code-and-when-not-to-delegate.md](07-reviewing-ai-code-and-when-not-to-delegate.md): leverage-ordered review, tautological tests, the delegation decision table
- [examples.md](examples.md): idempotency keys (SDD), a flaky Kafka consumer test (RPI + TDD), a 40-call-site migration (fan-out), and an incident you shouldn't delegate
- [exercises.md](exercises.md), [code/](code/) (fan-out driver, fake agent, tautology linter, clean-context reviewer, SPEC/plan/research templates), [references.md](references.md)

## Prerequisites
- [Module 00](../00-orientation/README.md): verifiability as the deciding question
- [Module 01](../01-llms-for-systems-engineers/README.md): context windows and why they degrade
- Helpful: [Module 02](../02-prompting-as-specification/README.md) (prompts as specs) and [Module 03](../03-context-engineering/README.md) (context management)
- Next: [Module 05](../05-tools-mcp-skills-hooks/README.md) (hooks and tools), [Module 07](../07-loops/README.md) (loops built on these workflows), [Module 08](../08-harness-engineering/README.md) (making the repo agent-ready)

## Key takeaways
- **Give the agent a check it can run, and put it in the environment, not the prompt.** A test command, `make check` or a Stop hook beats "please double-check". Ask for evidence (command plus output), never assertions.
- **Review where the leverage is.** A bad line of research becomes thousands of bad lines of code. Read research, plans and tests closely, and skim implementation.
- **Fresh context per phase, durable state in files.** research.md and plan.md (with a progress log) are what survive `/clear`, crashes and handoffs.
- **The SPEC's most valuable sections are Non-goals, Invariants and Done-when.** Requirement IDs should appear in test names.
- **TDD is the cheapest oracle.** A test seen failing for a behavioural reason before the code exists can't be a mirror of that code. Lock test files during green.
- **Parallel agents follow the single-writer rule.** One worktree, branch, port range and DB per session. Serialize commits in fan-out.
- **Fan-out is a batch job.** Bounded concurrency, a canary, a circuit breaker, a per-target verifier, capped retries with feedback, and a results ledger. Count how often the agent claimed success and was wrong.
- **Don't delegate what you can't check, or what you must deeply understand.** And measure whether delegating helped, because the feeling is unreliable (METR).
