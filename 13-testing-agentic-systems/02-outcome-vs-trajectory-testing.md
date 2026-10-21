# 02: Outcome vs trajectory testing

## The idea
An agent run produces two things you can check:

- **The outcome:** the state of the world when the run ends. Is prod on v2.4.0 and healthy? Is there a reservation in the database? Does the test suite pass?
- **The trajectory:** the ordered list of actions and observations that got there. Which tools, with which arguments, in what order, and how many.

**Outcome tests** grade final state. **Trajectory tests** assert properties of the path. These are not two styles to choose between. They catch different bugs, the same way a linearizability checker and an end-of-test row count catch different bugs in a database.

The rule this module uses (*course synthesis*): **grade the outcome for success. Assert the trajectory only for invariants**: forbidden calls, required orderings that are policy (verify before promote), retry discipline, and budgets. Don't assert an exact tool sequence unless the sequence *is* the spec.

## Why it matters
Sources pull in two directions here. Anthropic's evals guide says "it's often better to grade what the agent produced, not the path it took," because agents find valid paths you didn't anticipate, and exact-path graders punish them for it ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). The OpenAI skill-evals post, on the other hand, defines four kinds of goals (outcome, process, style, efficiency) and writes deterministic checks against the `codex exec --json` event trace, such as "did `npm install` run?" ([OpenAI, "Testing Agent Skills Systematically with Evals"](https://developers.openai.com/blog/eval-skills)).

Both are right, about different checks. Outcome-only grading is blind to any bug that ends in the correct state:

```text
skip_verify run         -> prod v2.4.0 healthy. Outcome: PASS. It never checked staging.
delete_prod_first run   -> prod v2.4.0 healthy. Outcome: PASS. Prod was down between steps 3 and 4.
```

In ops, "ended in the right state" is not the bar. A change that caused an outage on the way to the right state is an incident. Exact-sequence grading has the opposite problem: it fails an agent that reads logs before checking status, which is harmless.

**Stance:** outcome checks decide pass or fail on the task. Trajectory checks encode things that must never happen, or must always happen before something else, whatever path the agent takes. That is a safety property ("nothing bad happens") alongside a liveness property ("something good eventually happens"). You know the split from TLA+ and Jepsen.

## How it works

### Outcome checks
Read the world, not the transcript.

```python
def check_outcome(world, service, version):
    prod = world.snapshot()[f"{service}/prod"]
    return CheckResult("outcome:prod_at_version", prod["version"] == version and prod["healthy"], str(prod))
```

Pair every outcome check with a **claim check** that compares what the agent *said* with what the world *shows*. This catches premature stop:

```python
claims_prod = re.search(rf"deployed .*{re.escape(version)} to prod", run.final_text, re.I)
if claims_prod and not (prod["version"] == version and prod["healthy"]):
    fail(f"claimed {run.final_text!r}, world has {prod}")
```

### Trajectory assertions
Four families cover most needs:

| Family | Example | Function in `trajectory_checks.py` |
|---|---|---|
| Forbidden calls | Never `delete_deployment` in prod | `check_forbidden` |
| Ordering policy | Prod deploy only after a staging `get_status` shows the same version healthy | `check_promotion_order` / `promotion_allowed` |
| Retry discipline | After a retryable error, the next same-tool call reuses the `request_id` | `check_retry_reuses_request_id` |
| Budgets | At most N steps, and the run must end with `end_turn`, not the step cap | `check_step_budget` |

Write ordering checks as **"X must be preceded by Y since the last Z"**, not as "the sequence equals [...]". `promotion_allowed` resets verification on every new staging rollout. That is the agent version of "a read must observe the latest write".

### Process checks on a coding agent's trace
The same idea works on a real coding agent's event stream. `codex exec --json` emits JSONL events such as `item.started` and `item.completed` (with items of type `command_execution` and `agent_message`) and `turn.completed` with token usage ([Codex non-interactive docs](https://developers.openai.com/codex/noninteractive), event names checked 2026-10-19). `codex_trace.py` turns those into the same four families:

```python
def commands(events):
    return [e["item"]["command"] for e in events
            if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "command_execution"]

checks = [
    Check("no_forbidden_commands", not any(re.search(r"kubectl\b(?=.*\bprod\b).*\bdelete\b", c) for c in cmds)),
    Check("efficiency:command_count", len(cmds) <= 8),
    Check("process:staging_verified_before_prod", stg_rollout_status_idx < first_prod_change_idx),
]
```

The OpenAI post keeps the eval cases in a CSV with an `id,should_trigger,prompt` header. Rows with `should_trigger=false` are **negative controls**: prompts where the skill must *not* fire. For an ops skill, the check on a negative-control row is "zero mutating commands". `data/skill_eval_prompts.csv` has one. The agent was asked a read-only question and "helpfully" ran `kubectl set image` anyway, so the check fails.

### The transition failure matrix
A pass rate tells you how often runs fail. The **transition failure matrix** tells you where. Hamel Husain and Shreya Shankar describe it this way: rows are the last successful state, and columns are the state where the first failure occurred. In their text-to-SQL example, one transition accounted for 12 failures and another for 2, so you know which one to fix first ([Hamel & Shreya, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)).

`first_failure()` walks the trajectory and judges each step against the steps before it. That is what you do when you read a trace by hand and note the *first* thing that went wrong:

```python
for i, s in enumerate(run.steps):
    bad = forbidden(s) or premature_promotion(s, prev) or third_identical_status(s, prev) or retry_with_new_id(s, prev)
    if bad:
        return last_good, state_of(s)
    last_good = state_of(s)
if run.stop_reason == "step_budget": return last_good, "budget"
if not claim_matches_state(...):     return last_good, "report"
```

## Worked example: 40 runs of a noisy agent
`flaky.py` runs the deploy task 40 times. Each seed fixes the world's faults (15% transient, 15% lost acks, 2% infra crashes) and the "model's" behavior for that run (the noisy policy occasionally skips verification, stops early, or mints a new request ID on retry). With infra errors retried on a fresh environment:

```text
trials: 40  pass: 35  fail: 5  infra_error (excluded): 0
failing checks: claim_matches_state x2, outcome:prod_at_version x2,
                staging_verified_before_prod x2, retry_reuses_request_id x1
transition failure matrix:
last good \ first fail  deploy:prod   report
deploy:prod             1
deploy:staging          2             2
```

How to read it:
- `deploy:staging -> deploy:prod` (2): the agent went straight from a staging rollout to prod without a `get_status`. That's an ordering failure, so the fix belongs in the harness: make `deploy(env="prod")` refuse unless staging is verified ([Module 14](../14-steering-and-guardrails/README.md)). Don't add another sentence to the prompt.
- `deploy:staging -> report` (2): premature stop. The fix is a claim-vs-state gate before the agent may end its turn (a Stop-hook style check, [Module 07](../07-loops/README.md)).
- `deploy:prod -> deploy:prod` (1): a retry with a new request ID. The fix is a tool contract that derives the idempotency key from the intent, so the model never picks it.

Compare that with the bad version of this analysis: "pass rate 87.5%, let's tweak the prompt." The matrix turns the pass rate into a ranked list of transitions to harden, and each one points to the cheapest layer that can fix it.

## Pitfalls
- **Over-specified trajectories.** `assert tools == ["get_status", "deploy", ...]` fails on harmless reorderings and trains you to ignore red builds. *Detect:* if a trajectory test fails and the outcome was right and no invariant was broken, the test is too strict.
- **Under-specified outcomes.** Checking `version == v2.4.0` without `healthy` passes a crash-looping deploy. *Detect:* write the outcome check from the incident postmortem template ("what would the on-call need to see to close the ticket?").
- **Trajectory checks that read the model's prose.** "The agent said it checked staging" is not a check. *Detect:* every trajectory check should read tool calls and results only.
- **No negative-control rows.** A skill that over-triggers looks perfect on a suite of should-trigger prompts. *Detect:* make sure at least 20% of rows are `should_trigger=false` with a zero-side-effect check (the OpenAI post includes negative controls in its starter CSV).
- **Matrix states that are too coarse or too fine.** "tool_call" as a single state tells you nothing. A state per argument value spreads the counts too thin. *Detect:* if one cell holds more than 60% of failures and still points to several different fixes, split the state.

## In your day job
- For each agent, write down its 3–5 trajectory invariants as code, not prose: forbidden calls, required orderings, retry rules, and budget.
- Add a claim-vs-state check wherever an agent ends with a natural-language summary of what it did.
- Run your existing agent traces (Claude Code `stream-json`, `codex exec --json`, or your own tracer) through a first-failure classifier and build the transition matrix before your next prompt change.
- Add negative-control rows to every skill or tool eval: requests where the agent must do nothing destructive.
