# 01: Checks, not instructions

## The idea

An **instruction** asks the model to behave a certain way: "always run the tests", "never modify test files", "double-check your work". The model reads it as one more token sequence in its context. It competes with everything else in the window, it can be lost to compaction, and the model can misread it, rationalize past it, or follow it so literally that it causes a different failure.

A **check** is a predicate that lives in the environment: a test command, a schema validator, a Stop-hook gate, a permission rule. The run cannot finish, or the action cannot happen, unless the predicate holds. The model doesn't have to remember a check, agree with it, or interpret it. It only has to satisfy it.

The practical rule for this module: **when you want a behavior, ask what predicate would prove it happened, and put that predicate where the agent cannot route around it.** Keep the prompt for what instructions do well: stating the goal, the scope, and *how* success will be measured (the command that will be run). Don't use it to enforce.

## Why it matters

Anthropic's own documentation contains a tension that looks like a contradiction until you separate instructions from checks.

- The Claude Code best-practices page makes verification the central lever: "give Claude a way to verify its work". Without a check, "looks done" is the only signal, and *you* become the verification loop ([Claude Code docs, "Best practices"](https://code.claude.com/docs/en/best-practices)).
- The Opus 5 prompting guide says the opposite thing about *instructions*: "Claude Opus 5 verifies its own work without being told to. If your prompt contains explicit verification instructions ('include a final verification step for any non-trivial task,' 'use a subagent to verify'), remove them: instructions like these cause over-verification on Claude Opus 5, and removing them reduces wasted tokens with no loss in quality" ([Anthropic, "Prompting Claude Opus 5"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). The same guide says "double-check your answer" style prompts "compound with the model's own behavior and add cost without improving results".

Both are right. The first is about giving the agent a **check it can run**. The second is about **telling** it to check. The course stance, from the gap analysis: *put the check in the environment (a test it can run), not in the prompt, and re-measure on every model.*

Another data point comes from the other vendor. When OpenAI introduced Structured Outputs, prompting alone got their model to 93% schema compliance on a hard JSON-schema eval. Constrained decoding, a mechanism, got it to 100% ([OpenAI, "Introducing Structured Outputs"](https://openai.com/index/introducing-structured-outputs-in-the-api/)). Instructions get you most of the way. Mechanisms get you the last nines. You already know this pattern: a comment saying "callers must hold the lock" against an assertion that the lock is held.

## How it works

### The enforcement ladder

Order your options by who enforces them and whether the agent can talk past them.

| Level | Mechanism | Enforced by | Can the agent ignore or argue past it? | Typical use |
|---|---|---|---|---|
| 0 | Prompt text ("verify", "be careful") | the model's attention | yes, and on Opus 5 it can backfire | goal, scope, the done-command |
| 1 | CLAUDE.md / AGENTS.md line | the model's attention, persisted across turns | yes; it's advisory | conventions, where things live |
| 2 | `/goal <condition>` | a separate small model reading the transcript | partly: the evaluator only sees what the worker surfaced | "keep going until X" |
| 3 | Stop-hook gate running the oracle | your script, deterministic | no, but bounded by your retry budget | "not done until tests pass and tests weren't weakened" |
| 4 | PreToolUse deny hook / permission deny rule | Claude Code, before the tool runs | no | "never force-push main", "never read .env" |
| 5 | Sandbox, credentials outside the box, egress allowlist | the OS and network | no, even under prompt injection | blast-radius limits ([Module 16](../16-security-and-containment/README.md)) |

The hooks guide states the difference directly: CLAUDE.md instructions are advisory, while hooks are deterministic and guaranteed to run ([Claude Code docs, "Hooks guide"](https://code.claude.com/docs/en/hooks-guide)). The best-practices page has its own version of the ladder: "run the check and iterate" in the prompt, then a `/goal` condition, then a Stop hook as a deterministic gate, then a verification subagent that tries to refute the result.

### Decision rules

1. **For every "always" or "never" in your prompts or CLAUDE.md**, pick one of three things to do with it:
   - turn it into a check (a test, a validator, a gate),
   - turn it into a permission rule or a PreToolUse deny,
   - or delete it, because the model already does it or because it's unenforceable and noisy.
2. **Tell the agent how done will be measured, not to be careful.** "Done means `make check` exits 0" is information the agent needs. "Make sure everything works" is not.
3. **The done signal must come from something the agent cannot write.** Steve Kinney's Ralph-loop lessons make the point that the done signal should come from CI, a hook or a human, never from a file the agent can edit ([Kinney, AI Development Setup](https://stevekinney.com/courses/ai-development-setup)). That's why the code in this module denies agent writes to `.claude/hooks/`, `.claude/settings.json`, the gate's state directory, and the test-approval file.
4. **Make the check cheap enough that the agent runs it voluntarily.** A 10-second targeted test command gets run after every edit. A 40-minute suite gets run once, at the gate, and the agent flies blind until then. Expose a fast check for iteration and keep the full oracle for the gate.
5. **Re-measure on every model upgrade.** Every instruction you keep encodes an assumption about a model's weakness. The Opus 5 guide is a live example of an instruction that used to help and now costs tokens. ([Module 08](../08-harness-engineering/README.md) covers ablating the harness on each upgrade.)

## Worked example: turning a CLAUDE.md into checks

Here is a CLAUDE.md from a payments service. It was written over a year of incidents, one line per scare.

```markdown
# CLAUDE.md (before)
IMPORTANT: Always run the tests before saying you're done.
IMPORTANT: Verify your work carefully. Use a subagent to double-check non-trivial changes.
NEVER modify or delete existing tests. Tests are the source of truth.
Never push to main. Never force push.
Don't read .env or print secrets.
Be careful with retries in the charge path - idempotency matters!!
Make sure all edge cases are handled.
Use `make check` to run lint + tests.
```

**Why it fails.** Count the enforcement: zero. Lines 1 and 2 are verification *instructions*. On Opus 5 they trigger extra verification passes and subagent spawns that the guide says add cost without improving quality. Line 3 is the important one, and it is exactly the instruction an agent under test pressure breaks. Kent Beck lists "cheating, for example by disabling or deleting tests" as one of his three warning signs ([Beck, "Augmented Coding: Beyond the Vibes"](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)). Lines 4 and 5 describe actions a single misread turns into an incident. Lines 6 and 7 are anxiety, not information.

**After.** Each line became one of three things.

| Before | Became | Where |
|---|---|---|
| "Always run the tests before saying you're done" | Stop-hook gate that runs the oracle and blocks the stop | `code/hooks/stop_gate.py` |
| "Verify carefully / use a subagent to double-check" | deleted (Opus 5 self-verifies); the gate is the real verification | n/a |
| "NEVER modify or delete existing tests" | diff check for weakened, skipped, or deleted tests, run inside the gate; approvals file only a human can write | `code/hooks/test_tamper_check.py`, `pre_tool_guard.py` |
| "Never push to main / force push" | PreToolUse deny on force-push to protected branches; `ask` on any push | `pre_tool_guard.py`, `settings.example.json` |
| "Don't read .env" | `Read(./.env)` deny rule plus a guard on `cat .env` | `settings.example.json`, `pre_tool_guard.py` |
| "Be careful with retries... idempotency" | a property test: N concurrent retries with one key give one charge | the repo's test suite ([Module 13](../13-testing-agentic-systems/README.md)) |
| "Make sure all edge cases are handled" | deleted; edge cases you care about become tests | n/a |
| "Use `make check`" | kept: this is information the agent needs | CLAUDE.md |

```markdown
# CLAUDE.md (after)
Done means `make check` exits 0. For fast iteration on the charge path: `pytest -q services/payments -x`.
Test changes need human approval (.agent/approved-test-changes.txt). If you think a test is wrong, stop and say why.
Idempotency invariants are in docs/invariants.md#payments; the property tests in services/payments/tests encode them.
```

Three lines, all information, no enforcement. Enforcement lives in `.claude/settings.json` (see [`code/settings.example.json`](code/settings.example.json)).

What happens when the agent now tries the classic move: it changes `assert gateway.calls == 1` to `assert gateway.calls >= 1` so the suite goes green. The run below is real, measured by running the hook against a scratch git repo (see [03-hooks-as-gates.md](03-hooks-as-gates.md) for the full sequence):

```json
{
  "decision": "block",
  "reason": "Stop blocked by the verification gate (attempt 2 of 5).\n\nTest tampering detected. Revert these test changes and fix the code under test instead:\n- [high] assertion_weakened test_svc.py:5 exact equality replaced by a looser comparison: 'assert charge_count(retries=2) == 1' -> 'assert charge_count(retries=2) >= 1'\nIf you believe a test is wrong, stop and explain why to the user; only a human can approve test changes."
}
```

The instruction "NEVER modify tests" was a hope. The check is a wall with a door, and only a human holds the key.

## Pitfalls

- **A check the agent can edit is an instruction with extra steps.** If the oracle script, the hook, or the approval file sits in a path the agent can write, it will eventually be "fixed". *Detect:* list every file your gate reads, and confirm a deny rule or guard covers each one.
- **A weak oracle certifies wrong work.** Spotify names "a PR that passes CI but is functionally incorrect" as their most serious error, because it erodes trust ([Spotify Engineering, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). A gate is only as good as the predicate behind it. *Detect:* mutation-test the oracle. Seed a known-bad change and confirm the gate blocks it ("prove it can fail"; [Module 07](../07-loops/README.md)).
- **Keeping verification instructions "just in case".** On Opus 5 they cost tokens and spawn subagents for no gain. *Detect:* A/B the prompt with and without them on your eval set, and compare tokens and pass rate ([Module 12](../12-hill-climbing/README.md)).
- **Checks that flood the context.** A gate that pastes 4,000 lines of Maven output back into the agent's context teaches it nothing and evicts useful state. *Detect:* look at the `reason` your gate emits. If a human can't spot the failure in 10 seconds, neither can the model. Spotify's verifiers use regexes to extract only the relevant errors ([Spotify, part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)).
- **Turning every rule into a gate.** Each gate has latency, false positives and maintenance cost. Gate the invariants whose violation is expensive (correctness, security, irreversible actions). Leave style to linters and review.

## In your day job

- Audit your team's CLAUDE.md or AGENTS.md this week. Tag each line as *information*, *enforceable*, or *delete*, and move each enforceable line into a hook, a permission rule or a test.
- Write down the one-line definition of done for your repo (`make check` exits 0) and put it at the top of CLAUDE.md. That is the only "verify" instruction the agent needs.
- Before you trust a gate, run it against a deliberately broken change and against a deliberately weakened test. If it doesn't block both, it isn't a gate yet.
