# 01: Verifiability is the deciding question

## The idea

Karpathy's framing gives the course its spine. Software 1.0 is code you write by hand. Software 2.0 is neural-network weights, found by optimization rather than written. Software 3.0 is prompting: in his YC talk, "Prompts are now Programs", and all three layers coexist in one system ([Latent Space notes on Karpathy, "Software Is Changing (Again)", June 2025](https://www.latent.space/p/s3)).

In "Verifiability" (Nov 2025), he names the property that predicts what each kind of software can automate. "Software 1.0 easily automates what you can specify." "Software 2.0 easily automates what you can verify." For a task to be automatable this way, the environment has to be:

- **resettable**: you can start a new attempt;
- **efficient**: you can make many attempts;
- **rewardable**: some automated process can score each attempt.

([Karpathy, "Verifiability"](https://karpathy.bearblog.dev/verifiability/))

He wrote that about *training*: those three properties are what lets reinforcement learning hill-climb a skill. The course applies the same test to *delegation*. When you hand work to an agent, you are running the same kind of search at inference time. The agent tries something, a check scores it, and the agent tries again. So the question that decides how far you can let go is the one Karpathy asks about training:

> **Course thesis: autonomy should scale with verifiability.** Before you choose a tool, a prompt or a loop, ask three things. What can be checked here? How do I make it checkable? How do I use that check to steer, loop or hill-climb?

The rest of this module, and the other eighteen, are elaborations of that sentence.

## Why it matters

Karpathy's April 2026 Sequoia summary separates two activities that share the same tools: "Vibe coding is fine for prototypes and personal tools. Agentic engineering is what serious teams need." And: "Vibe coding raises the floor. Agentic engineering is about extrapolating the ceiling." ([Karpathy, Sequoia AI Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)). Simon Willison makes the same split: vibe coding means not caring how the code works, and agentic (earlier "vibe") engineering means experienced engineers using agents while staying accountable for the result ([Willison, "Vibe engineering"](https://simonwillison.net/2025/Oct/7/vibe-engineering/)).

The difference between the two is not the tool. **It is whether anything checks the output other than "it seemed to work when I tried it."** In vibe coding, your eyes on the running program are the oracle. That is a weak oracle: it samples one path, it gets tired, and it is biased toward believing the thing you just built. In agentic engineering you build checks first. Those checks can be tests, types, contract suites, golden files, invariants or calibrated judges. Then you let the agent iterate against them.

Karpathy's MenuGen write-up is the standard failure case. The app worked in the demo, but the agent's design matched Stripe payments to users by email instead of by a persistent user ID ([Karpathy, "Vibe coding MenuGen"](https://karpathy.bearblog.dev/vibe-coding-menugen/)). No check covered "a payment belongs to exactly one user across email changes", so nothing could catch the bug, and more autonomy would only have shipped it faster.

Karpathy's Sequoia summary has the line that sets the boundary of what you can delegate: "You can outsource your thinking, but you can't outsource your understanding."

## How it works

### The verifiability scorecard

Karpathy's three properties map directly onto engineering artifacts you already know. The course adds a fourth, because for delegation the check itself can be wrong.

| Property | The question | Engineering artifact | Weak version | Strong version |
|---|---|---|---|---|
| Resettable | Can the agent try again from a clean state? | Worktree, hermetic build, ephemeral DB, sandbox | Shared staging DB the agent mutates | Per-worktree Postgres from a fixture, torn down per run |
| Efficient | Is a check cheap enough to run every iteration? | Fast local tests, incremental builds, lint | 40-minute CI as the only check | Sub-10-second targeted check; Stripe runs a lint subset on push in under 5 s ([Stripe Minions](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)) |
| Rewardable | Does an automated process score the attempt? | Tests, type checker, contract suite, benchmark threshold | "Looks right to me" | `make check` exits non-zero on wrong output |
| **Faithful** (*course addition*) | Does passing the check imply the thing you care about? | Mutation testing, a known-bad input, a seeded bug | Tests the agent wrote for its own code | An oracle you have watched fail on a wrong implementation |

> **Synthesis:** "faithful" is the property Karpathy's training framing takes for granted and delegation cannot. An RL reward that is gameable produces reward hacking. A test suite that is gameable produces green CI on wrong code. Spotify calls the second, a PR that passes CI but is functionally incorrect, "the most serious error" ([Spotify, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). [07-loops](../07-loops/README.md) turns this into a rule: write the oracle first, and prove it can fail.

### Decision rules

1. **Score the task before you pick a mode.** Do it per task, not per repo. A repo can have a strong oracle for its parser and none for its retry policy.
2. **If the task scores weak, the first deliverable is a check, not the change.** This is the most common move in the course. It is also usually cheap with an agent, because writing a test harness is itself a well-specified, verifiable task.
3. **Jaggedness follows verifiability.** Karpathy attributes the uneven frontier, with fast progress in math and code and slow progress elsewhere, to verifiability *and* to how much training attention labs give a domain ([Sequoia 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/)). For you, this means an agent that is brilliant on a CRUD endpoint can be useless on your custom consensus code, and both observations can be true on the same day. [01-llms-for-systems-engineers](../01-llms-for-systems-engineers/README.md) covers why.
4. **Put the check in the environment, not in the prompt.** "Please double-check your work" is not a verifier. A command that exits non-zero is. Anthropic's guidance has moved this way: its prompting guidance for recent models reports *over*-verification when you instruct the model to verify, while its Claude Code guidance still makes a runnable check central. The course reconciles the two by putting the check in the environment and re-measuring on each model. [14-steering-and-guardrails](../14-steering-and-guardrails/README.md) covers this.

## Worked example: an exactly-once change to a Kafka consumer

**The task.** `ledger-consumer` reads `payments.settled` and writes ledger entries. During a rebalance it double-applies some events. You want it to commit offsets only after the DB transaction commits, and to dedupe on `event_id`.

### Bad version: delegate the change, verify by inspection

```text
Prompt to agent:
Make ledger-consumer exactly-once. Commit offsets after the DB write and dedupe on event_id.
Make sure it works.
```

What happens (illustrative output):

```text
Agent: I've moved commitSync() after the transaction and added a unique index on
ledger_entries(event_id) with ON CONFLICT DO NOTHING. All 112 existing tests pass. Done.
```

Why this fails. The existing tests never kill the consumer between the DB commit and the offset commit, so they cannot tell the old code from the new. "All tests pass" was true before the change too. The agent's claim is unfalsifiable as stated. Score it: resettable (yes, it's a unit-test run), efficient (yes), rewardable (technically), **faithful: no**. The check doesn't fail on the bug you care about. Autonomy here amounts to a coin flip with a confident summary.

### Good version: make it checkable, then delegate

**Step 1. Build the oracle first**, and watch it fail on current `main`. This task is itself very delegable because its own success criterion is crisp: the test must fail on `main`.

```text
Prompt to agent (step 1):
Write an integration test `test_rebalance_no_double_apply` using the Testcontainers Kafka + Postgres
fixtures in tests/integration/conftest.py. It must:
- produce 500 events with unique event_ids to payments.settled
- run the consumer, and inject a crash (via the existing FAULT_AFTER_DB_COMMIT hook) after the DB
  commit but before the offset commit, at event 137 and event 402
- restart the consumer and drain
- assert: count(ledger_entries) == 500 and sum(amount) equals the produced sum
Run it against current main and show me it FAILS. Do not change src/.
```

```text
(illustrative output)
FAILED tests/integration/test_rebalance.py::test_rebalance_no_double_apply
  assert 502 == 500
```

Now the check is faithful: it fails on the known-bad implementation.

**Step 2. Delegate the change against the oracle.**

```text
Prompt to agent (step 2):
Make test_rebalance_no_double_apply pass without editing any file under tests/.
Constraints: offsets are committed only after the DB transaction commits; idempotency via
event_id; no change to the public consumer config. Run `make check` (unit + this integration test)
before you say you are done, and paste its output.
```

The scorecard now reads resettable (containers), efficient (about 40 s), rewardable (exit code), and faithful (watched it fail). That task can safely run as a supervised agent, and it is a candidate for a loop if you had 30 similar consumers. [03-autonomy-dial](03-autonomy-dial.md) makes that choice explicit.

**What changed:** the same model, the same repo and an almost identical request. The only difference is that a check now exists which could tell you the agent was wrong.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| **Treating "tests pass" as verification** when the tests predate the behavior you're changing | Revert the change and run the tests. If they still pass, they weren't checking it. |
| **Agent-written tests that encode the agent's bug** (tautological tests) | Mutation test, or hand-seed one bug and confirm a test goes red. See [13-testing-agentic-systems](../13-testing-agentic-systems/README.md). |
| **Vibe coding on a production path** because the prototype "already works" | Ask what would fail if the design were wrong (MenuGen's email-as-key). If the answer is "nothing", you are still vibe coding. |
| **Slow oracles**: a check that takes 30 minutes gets skipped, or the agent stops running it | Time your check. If it takes more than a couple of minutes, build a targeted subset for the inner loop and keep the full suite as a gate. |
| **Prompt-as-verifier** ("be careful", "double-check") | Grep your prompts and CLAUDE.md for "make sure" and "verify". Each one should point to a command, or be deleted. |

## In your day job

- Before delegating any ticket, write its scorecard in the ticket: resettable, efficient, rewardable, faithful. It takes two minutes and decides the mode.
- When a task scores weak, ask the agent for the check first, and watch it fail on `main` before you ask for the change.
- Keep one command (`make check`, `just verify`) that is the repo's definition of done, and make it fast enough to run every iteration. [08-harness-engineering](../08-harness-engineering/README.md) builds this out.
- Use vibe coding deliberately for throwaway spikes and scouts, and label the branch so nobody merges it.
