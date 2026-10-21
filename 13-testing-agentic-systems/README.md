# 13: Testing agentic systems
> After this module you can put an agent inside a deterministic fake world, assert on what it *did* as well as where it ended up, measure how often it fails under seeded faults and sampling noise, and prove that your tests can fail.

## Why this matters
An agent is a nondeterministic process that issues side-effecting calls against shared state, over many steps, and decides for itself when to stop. You have tested systems like that before. They are the ones where the bug shows up one run in forty, only under a lost ack, and only if two steps interleave in a particular order. Agents fail the same way. A deploy agent that retries a timed-out rollout with a fresh request ID passes every test until the network drops one ack, and then it ships the same change twice. A run that promotes to prod without checking staging ends in the correct final state 95% of the time, so an outcome-only eval scores it green.

The usual eval toolkit (a dataset, a grader, a pass rate) gives you a number. It does not tell you *where* the run went wrong, whether the failure was the model or the sandbox, or whether the grader can fail at all. Anthropic found that infrastructure configuration alone moved Terminal-Bench 2.0 scores by 6 points ([Anthropic, "Quantifying infrastructure noise"](https://www.anthropic.com/engineering/infrastructure-noise)). On τ-bench, GPT-4o succeeded on fewer than half the tasks, and its pass^8 in retail fell below 25% ([Yao et al., τ-bench](https://arxiv.org/abs/2406.12045)). Most agents in production are less consistent than their pass@1 suggests.

This module is the test-engineering half of evals. [Module 10](../10-evals-fundamentals/README.md) teaches you to find failure modes and grade them. This module teaches you to build the harness that makes those failures reproducible: simulated worlds, simulated users, cassettes, seeded fault injection, property search, and mutation testing on the checks themselves.

## The distributed-systems anchor
**Testing an agent is closer to testing a distributed system for race conditions than to unit-testing a function.** The same tools carry over:

| You already use | Agent version | Code |
|---|---|---|
| FoundationDB-style deterministic simulation | A fake world where every fault and every "random" choice comes from one seed | `world.py` |
| Jepsen: inject faults, check a history against a consistency model | Inject 503s and lost acks, then check the action log against invariants | `world.violations()`, `trajectory_checks.py` |
| Idempotency keys and at-least-once delivery | "Retry reuses request_id", tested under ack loss | `test_properties.py` |
| Flaky-test quarantine | pass^k, flakiness budgets, and separating infra noise from model failures | `flaky.py` |
| VCR cassettes / recorded fixtures | `RecordingClient` / `ReplayClient`, plus a staleness check | `replay_demo.py` |
| Mutation testing | Mutate the trajectory checker and count how many mutants each suite kills | `mutation_demo.py` |

**Where the analogy breaks.** In FoundationDB, the code under test is deterministic once you control the scheduler and the network. An agent's policy is sampled: the same context can produce a different next action. You can make the *world* deterministic, but with a real model the *agent* stays stochastic. So you get reproducibility for the environment, and statistics for the agent. You also have no spec for the agent's internals. You can only check its observable behavior (calls, final state, claims) against invariants.

## Learning goals
- [ ] List the agent failure surface (wrong tool, wrong args, loops, premature stop, state corruption, side effects, nondeterminism) and name a check for each
- [ ] Write outcome checks against world state, and trajectory assertions for forbidden calls, ordering policies, step budgets, and retry discipline
- [ ] Build a transition failure matrix from a batch of runs and use it to pick the next fix
- [ ] Build a seeded simulated environment whose action log is identical for the same seed
- [ ] Run a τ-bench-style simulated user, and audit the simulator for leaks, solution-dictation, and false stops
- [ ] Record and replay agent runs, and list the cases where a green replay means nothing
- [ ] Compute pass@k and pass^k from N trials, classify a test as stable, flaky or broken, and keep infra errors out of the denominator
- [ ] Write Hypothesis properties (no forbidden actions across seeds, idempotent retries, paraphrase-invariant classification) and let Hypothesis find a counterexample
- [ ] Score a test suite by mutation testing, lint agent-written tests for tautologies, and add negative controls to every check

## Reading order
1. [01-the-race-conditions-of-agents.md](01-the-race-conditions-of-agents.md): the analogy, and the seven ways agents fail
2. [02-outcome-vs-trajectory-testing.md](02-outcome-vs-trajectory-testing.md): grade the world, assert the path, and find where runs break with a transition failure matrix
3. [03-deterministic-worlds-and-simulated-users.md](03-deterministic-worlds-and-simulated-users.md): FoundationDB-style fake worlds, seeds, and τ-bench simulated users along with their pitfalls
4. [04-record-replay-and-sandboxes.md](04-record-replay-and-sandboxes.md): cassettes, when replay lies, and the environment ladder up to real sandboxes
5. [05-statistical-testing-under-nondeterminism.md](05-statistical-testing-under-nondeterminism.md): run N times, pass^k, flakiness budgets, quarantine, and infra noise
6. [06-property-based-and-metamorphic-testing.md](06-property-based-and-metamorphic-testing.md): invariants with Hypothesis, and metamorphic relations when you have no oracle
7. [07-testing-the-tests.md](07-testing-the-tests.md): mutation testing, tautological agent-written tests, and negative controls
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/)

## Prerequisites
- [Module 07: Loops](../07-loops/README.md), for the agent loop and its governors (budgets, repeat detection)
- [Module 10: Evals fundamentals](../10-evals-fundamentals/README.md), for traces, error analysis, and the basics of pass@k vs pass^k
- Helpful: [Module 06: Agent architectures](../06-agent-architectures/README.md) (idempotency and durable state) and [Module 12: Hill-climbing](../12-hill-climbing/README.md) (error bars and noise checks)

## Key takeaways
- Treat agent failures like race conditions. They depend on the path and on timing, and they are rare per run, so you find them with controlled environments, fault injection, and many seeded runs, not with one happy-path example.
- Grade the outcome against world state. Assert the trajectory only for invariants (forbidden calls, required ordering, retry discipline, budgets), never for an exact tool sequence.
- Make the world deterministic: one seeded RNG for every fault and timing decision, and a test that the same seed gives a byte-identical action log. The agent will still be stochastic, so measure it.
- Report pass^k next to pass@1. At 75% per trial, pass^3 is about 42%. Retry infra errors on a fresh environment and exclude them from the denominator. Never retry a model failure away.
- A simulated user is itself a model under test. Audit it for leaked facts, dictated solutions, and stopping before the world shows success.
- A replay that passes tells you the code is unchanged. It tells you nothing about a new model, a new prompt, or the run-to-run variance you froze when you recorded it. Put the prompt hash and model ID in the cassette's metadata and check them.
- Every check needs a negative control: a known-bad run it must fail. Score suites by mutation testing. A suite that kills 0 of 10 mutants is decoration, and agents write that kind of suite readily.
