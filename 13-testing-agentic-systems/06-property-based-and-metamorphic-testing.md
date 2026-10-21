# 06: Property-based and metamorphic testing for LLM systems

## The idea
**Property-based testing** replaces "for this input, expect this output" with "for every input in this space, this property holds". A generator (Hypothesis, here) searches the space for a counterexample and shrinks it to a minimal one. For agents, the input space is seeds × fault plans × task variants. The properties are **invariants** that must hold whatever the agent does: never delete prod, never double-apply an intent, never claim what the world contradicts.

**Metamorphic testing** handles the case where there is no oracle. You often can't say what the correct severity is for an arbitrary alert. You *can* say how outputs must relate across transformed inputs: a paraphrase must get the same label, adding an irrelevant "FYI" must not change it, and reordering sentences must not change it. The relation is the test. For LLM components this is often the only scalable oracle you have.

These are the agent versions of what Jepsen does to databases. Jepsen generates operation histories under random faults and checks each one against a consistency model. It doesn't predict outputs.

## Why it matters
Example tests cover the paths you thought of, and agent bugs live on paths you didn't. In this module's code, the retry bug (`new_id_on_retry`) passes every example test with no faults. It shows up only when a lost ack lands on a mutating call. Hypothesis finds a seed for it and shrinks it to `seed=1` without being told where to look. Geoffrey Huntley recommends the same approach for agent-built systems: property-based tests for invariants such as "a customer is charged only once", run with Hypothesis under fault injection ([Huntley, "agency"](https://ghuntley.com/agency/)).

On the metamorphic side, the brittle classifier in `metamorphic.py` labels `"checkout is down for all users. error rate 100%."` as SEV1. One synonym swap later, `"checkout is unavailable for all users. error rate 100%."` gets SEV3. Hypothesis finds this as a one-step transformation chain `[('synonym', 0)]`. The bug is a few-shot prompt overfitted to surface words, which you'd otherwise discover through a missed page.

## How it works

### Writing agent properties
Good agent properties come in four shapes:

| Shape | Example property | Test |
|---|---|---|
| **Safety invariant** | No run, under any fault schedule, leaves `world.violations()` non-empty | `test_good_agent_never_violates_invariants_under_any_fault_schedule` |
| **Idempotence** | Calling `deploy` k times with one request_id ≡ calling it once | `test_deploy_tool_is_idempotent_per_request_id` |
| **Fault-equivalence** (metamorphic over faults) | The final state under faults equals the final state without faults, unless the agent honestly gave up | `test_retries_are_idempotent_final_state_matches_fault_free_run` |
| **Policy across samples** | The noisy agent never calls a forbidden tool, for any seed | `test_noisy_agent_never_calls_forbidden_tools_across_seeds` |

```python
CI = settings(max_examples=150, deadline=None, derandomize=True, database=None)

@CI
@given(seed=seeds, transient=rates, ack_loss=rates, version=st.sampled_from(["v2.4.0", "v2.4.1"]))
def test_good_agent_never_violates_invariants_under_any_fault_schedule(seed, transient, ack_loss, version):
    run, world = _run(promote_policy(version=version), seed, FaultPlan(transient, ack_loss))
    assert world.violations() == []
    assert check_claim_matches_state(run, world, "payments", version).passed
    prod = world.snapshot()["payments/prod"]
    assert (prod["version"] == version and prod["healthy"]) or prod["version"] == "v2.3.0"
```

The fault-equivalence property is the one you'll use most. It's how you'd test an at-least-once consumer: the output under redelivery must equal the output without it.

```python
faulty_run, faulty = _run(promote_policy(), seed, FaultPlan(transient, ack_loss))
_, clean = _run(promote_policy(), seed, FaultPlan())
if "Gave up" not in faulty_run.final_text:
    assert faulty.snapshot() == clean.snapshot()
assert len({r.request_id for r in faulty.rollouts}) == len(faulty.rollouts)
```

### Using Hypothesis to *find* a bug, not only to guard against one
`hypothesis.find(strategy, predicate)` returns the minimal example that satisfies a predicate. Point it at "this run produced a violation" and you have a bug hunter:

```python
def duplicate_rollout(seed):
    _, w = _run(promote_policy(new_id_on_retry=True), seed, FaultPlan(ack_loss_rate=0.2))
    return any("duplicate rollout" in v for v in w.violations())

seed = find(seeds, duplicate_rollout, settings=settings(max_examples=500, derandomize=True, database=None))
# -> 1
```

### Budget: properties against a real model are expensive
With a scripted policy, 150 examples cost milliseconds. With a real model, each example is a full agent run. Three rules (*course synthesis*):
1. **Develop properties offline** against scripted policies and the simulated world. Seed the agent's known bugs as policy flags, and check that each property catches the bug it targets.
2. **Run them live on a small budget.** `max_examples=20–50` nightly, with `derandomize=False` so each night explores new seeds. Store any failing seed as an explicit `@example(seed=...)`, the same way FoundationDB keeps failing seeds.
3. **Keep CI derandomized.** `derandomize=True, database=None` makes the per-PR run reproducible. A property test that's flaky because of its own generator is worse than none.

### Metamorphic relations for LLM components
List the transformations that must preserve the output (`metamorphic.TRANSFORMS`):

| Relation | Transform | Should preserve |
|---|---|---|
| Case | `UPPERCASE` | label |
| Whitespace | extra spaces, newlines | label |
| Synonym | down→unavailable, latency→response time | label |
| Irrelevant context | prefix "FYI from the on-call bot." | label |
| Reordering | reverse the sentence order | label |

You also need transforms that must *change* the label. These are the negative controls for the relation: rewriting "down for all users. error rate 100%." as "one internal canary failed a health check; no customer impact." must move the label off SEV1. (The module's code doesn't include this one. Exercise 5 asks you to add it.) Hypothesis composes up to three transforms per example:

```python
chains = st.lists(st.tuples(st.sampled_from(sorted(TRANSFORMS)), st.integers(0, 5)), min_size=1, max_size=3)

@CI
@given(alert=st.sampled_from(sorted(SEED_ALERTS)), chain=chains)
def test_classifier_is_paraphrase_invariant(alert, chain):
    client = FakeClient(robust_model)
    assert classify_alert(client, apply(alert, chain)) == classify_alert(client, alert) == SEED_ALERTS[alert]
```

Note the triple equality. Invariance alone would pass a classifier that labels *everything* SEV3. Anchor each relation to at least one labelled seed.

Other metamorphic relations worth using on agents:
- **Tool-order invariance:** shuffling the order of tool definitions must not change success. The [Module 03](../03-context-engineering/README.md) cache notes also care about this, for a different reason.
- **Irrelevant-tool invariance:** adding an unused tool must not change the trajectory's safety properties.
- **Monotonicity:** giving the agent strictly more information (the env in the opening message) must not lower its success rate.

## Worked example: from "it handles retries" to a counterexample
**Before.** The PR description, written by a coding agent, says "Handles transient deploy failures with retry." The accompanying test:

```python
def test_retry():
    world = OpsWorld(faults=FaultPlan(transient_rate=0.5), seed=0)
    run = run_agent(FakeClient(promote_policy(new_id_on_retry=True)), world)
    assert world.snapshot()["payments/prod"]["version"] == "v2.4.0"     # passes
```
It injects only *transient* faults (not applied, so a fresh ID is harmless) on one seed, and checks only the outcome.

**After.** Swap in the property, with both fault kinds and a search over seeds:
```python
@CI
@given(seed=seeds, transient=rates, ack_loss=rates)
def test_retries_are_idempotent_final_state_matches_fault_free_run(seed, transient, ack_loss): ...
```
Run against the buggy policy, Hypothesis reports a falsifying example. The minimal trajectory, from `find()`:

```text
deploy staging rid=staging-v2.4.0-1  -> timeout waiting for response (outcome unknown)
deploy staging rid=staging-v2.4.0-2  -> ok
...
violations: duplicate rollout of payments/staging@v2.4.0 (request ids 'staging-v2.4.0-1' and 'staging-v2.4.0-2')
```
The fix belongs in the tool contract, not the prompt. Have the harness derive `request_id` from `(task_id, tool, env, version)` so that the model never picks it ([Module 05](../05-tools-mcp-skills-hooks/README.md)). Then the property passes for every policy, including sloppy ones.

## Pitfalls
- **Properties that restate the implementation.** "deploy returns what deploy returns" is a tautology ([07](07-testing-the-tests.md)). *Detect:* the property never mentions world state, invariants or a relation between two runs.
- **Generators that never reach the bug.** Fault rates capped at 1% will almost never exercise retry paths in a 5-step run. *Detect:* add `hypothesis.event()` or count error results across examples. If retries happened in under 10% of examples, widen the generator.
- **Nondeterministic properties.** A property that sometimes fails on the same input (because a live model sampled differently) makes Hypothesis report flaky errors. *Detect:* Hypothesis raises `Flaky`. Live-model properties should assert over N samples, or run in the nightly tier with pass^k reporting.
- **Invariance without anchoring.** A constant classifier is perfectly paraphrase-invariant. *Detect:* each metamorphic test also asserts the seed label.
- **Synonym tables that change meaning.** "down" → "degraded" is not a synonym for severity purposes. *Detect:* have a human review the transform table once. It's the oracle.

## In your day job
- Write three invariants for your agent's world (forbidden actions, at-most-once effects, claim matches state) and a Hypothesis test over seeds × fault rates for each.
- For any LLM classifier or router, write five label-preserving transforms and one label-changing transform, and run them nightly against the real model with a small `max_examples`.
- When a property finds a failing seed, pin it with `@example(...)` so it becomes a permanent regression test.
- Move idempotency keys out of the model's hands. Then write the property that proves it worked.
