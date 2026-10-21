# 14: Steering & guardrails
> Make an agent do what you asked, or at least make it unable to finish until it has: checks instead of instructions, validators with repair loops, blocking hooks, mid-run redirects, drift alarms, risk-tiered approvals, and permission rules.

## Why this matters

You have probably watched this happen. You ask an agent to fix a failing idempotency test. Twenty minutes later it reports success. The suite is green because `assert gateway.calls == 1` became `assert gateway.calls >= 1`. Or the fix is correct, but it also added a retry wrapper around a non-idempotent charge call, bumped a page size in an unrelated service, and pulled in a new dependency. Or you spent three rounds typing "no, that's wrong" while it got further from the answer.

Each of these is a **steering failure**, and the reflex fix, more and louder instructions, makes it worse. Instructions are advisory. They compete with everything else in context, and on current models some of them backfire: Anthropic's Opus 5 guide says explicit verification instructions cause over-verification and should be removed. What works is the same thing that works for any unreliable worker: **predicates the work can't route around**, enforced by the harness rather than by the worker's good intentions.

This module is the "make it do what I asked" toolkit, roughly in the order a run goes. First you shape the output (schemas and validators). Then you constrain the actions (permissions, PreToolUse guards). Then you watch the trajectory (drift signals, mid-run redirects). Then you gate completion (Stop hooks running the oracle and a tamper check). And you put humans where the automated checks are weakest and the blast radius is largest. Every piece has runnable code and tests.

The course thesis applies directly: **autonomy should scale with verifiability.** Each mechanism here either makes something checkable or uses a check to steer.

## The distributed-systems anchor

| You know | Here it is |
|---|---|
| Kubernetes **validating admission controller** | a `PreToolUse` hook returning `deny` with a reason, before the action is persisted |
| **Readiness gate** on a rollout | a `Stop` hook that blocks "done" until the oracle passes |
| **Schema registry + consumer validation + DLQ** | structured outputs (shape) + local validator (constraints, semantics) + bounded repair loop + dead-letter |
| **Feedback control** (error signal, gain, saturation) | retry-with-feedback: the validator error is the error signal, and max-attempts plus no-progress detection are the saturation limits |
| **Burn-rate alerts** before SLO breach | diff-size and out-of-plan alarms before the final check fails |
| **Two-phase commit with a human coordinator** | approval requests bound to an exact action hash, with a timeout default |
| **Firewall allowlist vs denylist** | `dontAsk` plus `--allowedTools` vs `deny: ["Bash(rm -rf *)"]` |

**Where the analogy breaks:** the worker being gated is adaptive. A rejected `kubectl apply` doesn't rewrite itself to pass the admission check. A blocked agent will try again, and the cheapest way to pass a check is sometimes to attack the check: weaken the test, deselect it, or edit the hook. So every gate in this module also protects itself, with tamper detection and with deny rules on the guardrail files.

## Learning goals
- [ ] Convert a CLAUDE.md full of "always/never" lines into checks, permission rules, and deletions, and explain the Opus 5 over-verification tension.
- [ ] Build a validator that reports every schema and semantic error with precise paths, and a repair loop that feeds those errors back with a hard cap and no-progress detection.
- [ ] Write Claude Code `PreToolUse` and `Stop` hooks against the current hook schema, and explain why the built-in 8-continuation cap does not bound a test gate.
- [ ] Detect assertion weakening, skips and test deletion in a diff, and block completion on them.
- [ ] Choose between queue, interrupt, rewind and `/clear`; write a nudge with evidence, a constraint and a check; and use `/goal` with a Stop gate as the source of truth.
- [ ] Flag drift (out-of-plan files, diff-size overruns, loops) from a diff and a tool-event stream, and route warnings to humans rather than the agent.
- [ ] Design approval tiers by reversibility, blast radius and verifiability, and write an approval request a human can decide in a minute.
- [ ] Configure permission modes and rules, knowing deny-ask-allow precedence and why a Bash denylist isn't a boundary.

## Reading order
1. [01-checks-not-instructions.md](01-checks-not-instructions.md): the enforcement ladder; the Opus 5 over-verification tension, resolved.
2. [02-structured-outputs-and-repair-loops.md](02-structured-outputs-and-repair-loops.md): shape vs constraints vs truth; retry with validator feedback, bounded.
3. [03-hooks-as-gates.md](03-hooks-as-gates.md): current hook schema; Stop gates that work; why steering hooks mostly don't (Ronacher vs Spotify).
4. [04-mid-run-steering.md](04-mid-run-steering.md): Esc, queue, rewind, `/clear`, `/goal`, OpenAI's steer API; nudges that work.
5. [05-detecting-drift.md](05-detecting-drift.md): plans as contracts, Beck's warning signs, diff-size and scope alarms.
6. [06-human-in-the-loop.md](06-human-in-the-loop.md): approval tiers, agent UX for approvals, the inbox.
7. [07-permissions-as-guardrails.md](07-permissions-as-guardrails.md): modes, rule precedence, what deny rules don't stop.
- [examples.md](examples.md): four end-to-end scenarios.
- [exercises.md](exercises.md): eight exercises, offline and with a real agent.
- [code/](code/README.md): `validators.py`, `repair_loop.py`, `hooks/stop_gate.py`, `hooks/pre_tool_guard.py`, `hooks/test_tamper_check.py`, `drift_monitor.py`, `settings.example.json`, and tests.
- [references.md](references.md)

## Prerequisites
- [Module 04: Agentic coding workflows](../04-agentic-coding-workflows/README.md): plan mode and explore-plan-implement-verify.
- [Module 05: Tools, MCP, skills, hooks](../05-tools-mcp-skills-hooks/README.md): hook basics and tool design.
- [Module 07: Loops](../07-loops/README.md): oracles ("prove it can fail") and governors. This module's gates are the loop's stop conditions.
- Helpful: [Module 13: Testing agentic systems](../13-testing-agentic-systems/README.md) for tautological-test detection, and [Module 16: Security & containment](../16-security-and-containment/README.md) for the adversarial threat model this module deliberately does not cover.

## Key takeaways
- **Give checks, not instructions.** Tell the agent how done is measured (`make check` exits 0), then enforce it with a gate it can't edit. Delete "verify carefully" prompts; on Opus 5 they cost tokens without improving quality.
- **Constrained decoding guarantees shape, not constraints or truth.** Anthropic's decoder doesn't enforce `minimum`, `maximum`, `minLength` or `maxLength`. Validate locally, feed exact errors back, cap at about 3 attempts, and dead-letter the rest.
- **Blocking gates work; steering hooks mostly don't.** A Stop hook that runs the oracle and blocks with the compact failure is a control loop. A hook that injects advice is a memo.
- **Claude Code's 8-continuation Stop cap resets on every tool call**, so it doesn't bound an agent that keeps editing and failing. Give your gate its own budget, and halt with `continue: false` when the oracle itself is broken.
- **A green suite after a test edit is not evidence.** Check the diff for weakened, skipped or deleted assertions, and let only a human approve test changes.
- **After two failed corrections, `/clear`** and restart with a prompt that carries evidence, a constraint and a check. Accepted steering isn't applied steering, and in-flight side effects are not undone.
- **Scope signals catch what size signals miss.** A 3-line retry decorator on a charge call is more dangerous than a 600-line in-plan change. Alarm on both, and send warnings to a human.
- **A denylist over a shell is a list of spellings.** Use allowlists (`dontAsk` plus `--allowedTools`) for unattended runs, a parsing PreToolUse hook for interactive ones, and a sandbox when it has to hold against an adversary.
