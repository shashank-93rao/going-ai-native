# 03: Deterministic worlds and simulated users

## The idea
To test an agent's behavior under faults, you need an environment where you decide what the faults are and can replay them exactly. A **deterministic simulated world** is a fake of the systems the agent acts on (a cluster, a database, a ticketing API). All of its nondeterminism (failures, latencies, ordering) comes from a single seeded RNG. The same seed gives the same world history, so a failing run becomes a failing seed you can hand to a colleague.

Conversational agents need a second simulated party, **the user**. τ-bench pairs a simulated world (domain APIs plus a policy document) with an **LLM-simulated user** who has a goal and private information, and it grades the episode by comparing the final database state with an annotated goal state ([Yao et al.](https://arxiv.org/abs/2406.12045)). The simulated user is how you test whether the agent asks the right questions, rather than only whether it acts correctly once it has every fact it needs.

## Why it matters
FoundationDB is the standard reference. Its simulator runs a whole cluster (machines, disks, network) "within a single-threaded process", deterministically, so any run can be repeated exactly. It injects machine, network and datacenter failures, including "swizzle-clogging" of random subsets of connections. The team reports tens of thousands of simulations each night and estimates about a trillion CPU-hours of simulation in total ([FoundationDB, "Simulation and Testing"](https://apple.github.io/foundationdb/testing.html)). The lesson for agents: you can't make the model deterministic, but you *can* make everything around it deterministic. Once you have, a flaky agent test splits into a reproducible world history plus a measurable model variance.

Simulated users matter because real requests are underspecified. τ²-bench found that agents' performance drops significantly when they move from a setting with no user to one where they must guide a user who also has tools ([Barres et al., τ²-bench](https://arxiv.org/abs/2506.07982)). An agent that only ever sees complete, well-formed tasks has not been tested on the part that fails in production.

But user simulators fail too. τ²-bench had two annotators review traces for simulator errors. In airline, 47 of 100 conversations contained a user-simulator error, 13 of them task-critical. Retail had 20 of 50 (6 critical), and telecom 8 of 50 (3 critical), where the simulator is constrained by its own tools and observable state ([τ²-bench §4.3, Table 2](https://arxiv.org/html/2506.07982)). A simulator that is wrong 10%+ of the time on the critical path can easily move your pass rate more than your prompt change does.

## How it works

### Building a deterministic world (`world.py`)
Five rules:

1. **One RNG, one draw per call.** `OpsWorld.execute` draws exactly one `rng.random()` per tool call, whatever the tool. The fault schedule is then a pure function of (seed, call index): the k-th call always sees the k-th draw. A different trajectory still shifts which call gets which fault. That is why you sweep many seeds rather than hand-pick one.
2. **Fault kinds that match real failures.** Model the failures your agent's *decisions* depend on, not every failure that exists:

   | Fault | Semantics | What it tests |
   |---|---|---|
   | `transient_rate` | 503, **not applied** | Retries happen at all |
   | `ack_loss_rate` | **applied**, response lost (timeout) | Retries are idempotent |
   | `infra_crash_rate` | Environment raises `InfraError` | The harness classifies infra noise separately |

3. **An action log, not just state.** `world.log` records every call, its result, and whether it was applied. Invariants run over the log, which is what makes "prod was deleted at step 3, then recreated" visible after the fact.
4. **Invariants that hold for every task.** `world.violations()` checks no prod deletes, at least 2 prod replicas, no duplicate rollouts per intent, and no promotion while staging wasn't healthy at that version. These run after every test, like Jepsen's checker.
5. **Determinism is itself tested.** `test_world_is_deterministic_per_seed` runs the same seed twice and compares action logs byte for byte, then checks that a different seed differs. A simulator that leaks wall-clock time, dict ordering, or a global `random` breaks reproducibility without any visible symptom, so test it the way FoundationDB tests its own simulator.

**Seed everything, including the "model".** Offline, the model is a scripted policy (`policies.py`). `noisy_policy(seed)` draws its one mistake per run from the seed, imitating sampling variance. With a real model you can't seed the sampler reliably, so you fix the world's seed and run N trials ([05](05-statistical-testing-under-nondeterminism.md)).

### Simulated users (`user_sim.py`)
A simulated user has three parts: an **opening** (deliberately underspecified), **private facts** it reveals only when asked, and a **success predicate on the world**, never on the conversation.

```python
ROLLBACK_GOAL = UserGoal(
    opening="checkout is throwing 500s since the last deploy, can you fix it?",
    facts={"env": "prod", "ticket": "INC-4821"},
    success=lambda w: w.snapshot()["checkout/prod"] == {"version": "v2.3.0", "healthy": True, "replicas": 3},
    forbidden_hints=["rollback", "kubectl", "v2.3.0"],
)
```

There are two implementations:
- `ScriptedUser`: keyword rules, fully deterministic. Use it in CI.
- `LLMUser`: a model plays the user from a system prompt modeled on τ-bench's. The τ-bench simulator is told to reveal only what the current step needs, not to hallucinate facts, and to emit `###STOP###` when the goal is satisfied ([tau-bench `user.py`](https://github.com/sierra-research/tau-bench/blob/main/tau_bench/envs/user.py)). Note that the roles flip: the agent's text arrives as the simulator's `user` turn.

τ-bench also ships simulator *strategies* beyond plain LLM: `react` (think, then respond), `verify` (a supervisor model checks each user turn and regenerates it), and `reflection`. These exist because plain simulators make the mistakes listed below.

### Auditing the simulator
`audit_user_sim(conv, goal)` flags four failure modes. Each one makes the eval easier or meaningless:

| Pitfall | Effect on the eval | Detector |
|---|---|---|
| **Leaks facts** before the agent asks | The agent never has to ask, so the "ask clarifying questions" behavior goes untested | A fact value appears in a user turn before the agent mentioned the topic |
| **Dictates the solution** ("just run rollback to v2.3.0") | Tests instruction-following, not diagnosis | `forbidden_hints` appear in user turns |
| **False stop**: says done when the world isn't | Inflates the pass rate, or ends the episode early | The user emits STOP while `goal.success(world)` is false |
| **Never stops** | Wastes budget, and the turn cap hides real failures | Episode hits `turn_cap` |

## Worked example: a keyword user fooled by a guessing agent
The agent policy `rollback_agent_policy(ask_first=False)` has a common bug. It doesn't ask which environment. It guesses staging, rolls it back, and reports success.

**Bad test: grade by the user's satisfaction.**
```python
conv = run_conversation(agent, ScriptedUser(ROLLBACK_GOAL), rollback_world())
assert conv.stop_reason == "user_stop"      # passes
```
Transcript:
```text
user : checkout is throwing 500s since the last deploy, can you fix it?
agent: Rolled back checkout in staging.
user : ###STOP###
```
The scripted user stops on the phrase "rolled back". That is the user-simulator false-stop failure, and it happens with LLM users too, which tend to accept confident claims. Meanwhile `checkout/prod` is still `v2.5.0, healthy: False`.

**Good test: grade the world and audit the simulator.**
```python
assert not ROLLBACK_GOAL.success(conv.world)
assert any("goal is not met" in i for i in audit_user_sim(conv, ROLLBACK_GOAL))
```
The correct agent produces this:
```text
user : checkout is throwing 500s since the last deploy, can you fix it?
agent: Which environment is affected, staging or prod?
user : env: prod
agent: Rolled back checkout in prod to v2.3.0.
user : ###STOP###
```
and the world shows `checkout/prod: v2.3.0, healthy`. The audit is empty: no leaks, no dictation, no false stop.

`test_audit_flags_leaky_and_bossy_user_sim` covers the other common simulator failure. A FakeClient user whose first line is `"prod, INC-4821. just run rollback to v2.3.0"` makes the task trivial, and the audit reports both the leaked ticket and the dictated `rollback`.

## Pitfalls
- **A world that's too faithful to build.** You don't need a fake Kubernetes. You need the 5–10 behaviors the agent's decisions depend on. *Detect:* if you're modeling something no check reads, cut it.
- **A world that's too kind.** With no faults, no ambiguous requests and no bad versions, the agent's recovery logic never runs. *Detect:* coverage of the world's error branches across the suite should be above zero for each one.
- **Hidden nondeterminism in the simulator.** Wall-clock timestamps, `set` iteration order, `uuid4()` in IDs. *Detect:* the same-seed, byte-identical action-log test.
- **Grading on the simulated user's verdict.** The user is a model. It's not ground truth. *Detect:* every conversational eval has a world-state success predicate.
- **Using the agent's model as the user's model.** It shares the agent's blind spots and phrasing, and tends to cooperate too readily. *Course synthesis:* use a different model, or a smaller and more literal one, and calibrate it. Read 30+ simulated conversations and label simulator errors the way τ²-bench did before trusting the pass rate.
- **Simulator drift.** Changing the user prompt changes your eval. *Detect:* version the simulator prompt and record its hash with every result, exactly like the agent prompt.

## In your day job
- Pick your agent's riskiest dependency (the deploy API, the payments DB) and write a 150-line fake with a seeded fault plan and an action log. Wire it in as the tool backend for tests.
- Add the same-seed determinism test to that fake before anything else.
- For any conversational agent, write 10 `UserGoal`s whose openings are missing exactly one critical fact, and grade them on world state.
- Before you trust an LLM user simulator, label 30 of its conversations for leak, dictation, and false-stop errors.
