# 03: Pillar 2, Verify: checks the agent can run, read and trust

## The idea
An agent working without you needs something other than its own judgment to tell it whether a change is right. Pillar 2 is that something. A good verifier for an agent has five properties:

1. **Fast**: seconds, so it runs after every edit and not once at the end.
2. **Local and hermetic**: no shared staging and no network, so results do not depend on who else is running.
3. **Deterministic**: the same code gives the same verdict. A flaky check teaches the agent that red can be ignored.
4. **Explanatory**: the failure output says what is wrong *and what to do about it*, because that text is the agent's next prompt.
5. **Out of reach**: the agent cannot weaken the check to pass it, or at least cannot do so without you noticing.

The core artifacts:
- one "done" command;
- lints that carry remediation;
- fakes that model your dependencies' *failure* semantics;
- an ephemeral environment per worktree;
- contract tests on your interfaces;
- a gate that refuses to let the agent stop until done is green.

## Why it matters
- **Agents solve whatever the verifier checks.** Carlini's 16-agent C compiler project found that most of the effort went into tests and oracles, which had to be near-perfect because the agents would satisfy exactly what was checked. The harness was built for agents to read: a few lines of output with the rest in log files, `ERROR` on the same line as the reason so grep finds it, and a `--fast` mode that runs a deterministic sample ([Anthropic, "Building a C compiler with a team of parallel Claudes"](https://www.anthropic.com/engineering/building-c-compiler)).
- **Self-assessment is not verification.** In Anthropic's long-running harness work, Claude marked features done after unit tests or a curl even when they failed end to end. The fix was browser automation that tested as a user would ([Anthropic, "Effective harnesses for long-running agents"](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)). A later post puts it bluntly: "agents reliably skew positive when grading their own work" ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)).
- **Shift left, and cap the loop.** Stripe runs a local lint subset on each push in under five seconds and allows at most two CI rounds per agent run ([Stripe, "Minions"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)). Spotify exposes its verifiers as a single tool and runs them all in a Claude Code Stop hook, so that no PR opens if any of them fails ([Spotify, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)).

There is also a course stance from a real tension. Anthropic's Opus 5 guide says explicit verification instructions in the prompt cause over-verification, and that "the same applies to legacy harness scaffolding that adds separate verification steps" ([Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). The resolution: **put the check in the environment, not in the prompt.** A test the agent can run is information. "Remember to double-check" is noise for a model that already checks.

## How to do it

### 1. One "done" command, with a latency budget
```text
python tools/check.py   ->   check: PASS lint=ok docs=ok tests=(11 passed in 0.06s) in 0.4s
```
Give each tier a budget and keep the inner loop inside it:

| Tier | Budget | Runs | In this module |
|---|---|---|---|
| Lint and type checks | under 5 s | every edit | `lint_invariants.py`, `check_docs.py` |
| Unit and hermetic tests | under 30 s | every edit | `tests/` against `FakeBroker` and in-memory SQLite |
| Integration against real deps | under 5 min | before PR | (exercise) Testcontainers Kafka and Postgres |
| E2E or canary | longer | CI and post-merge | out of scope here |

Print only failures and one summary line, so passing output does not flood the context. `check.py` does this.

### 2. Lints whose errors are prompts
OpenAI's harness team writes custom lints with remediation text, so that the error message becomes the fix instruction in the agent's context ([OpenAI](https://openai.com/index/harness-engineering/)). Design rules:

- **Location and rule ID** (`orders/outbox.py:30:8: INV003`), so the agent can jump straight there and you can grep the history.
- **Why**, in one sentence, in domain terms. This is what stops the agent from "fixing" the lint by restructuring the code to dodge the pattern.
- **Fix**, as an imperative that names the API to use (`call _enqueue(...) inside the same with tx(conn): block`).
- **See**: an anchor into INVARIANTS.md or an ADR (kept valid by `check_docs.py`).
- **Suppression requires a reason**: `# noqa: INV003 <reason>`. A bare noqa does not suppress. Reasons are reviewable, and a bare noqa is the agent's escape hatch.
- **Use the AST, not regex**, wherever structure matters. `lint_invariants.py` walks function bodies to check that a write to `orders` and an `_enqueue` happen in the same function.
- **Document blind spots.** The lint cannot tell `WHERE id = ?` from `WHERE aggregate_id = ?` semantically, and a consumer that dedupes on offset still inserts into `processed_events`. `test_lint_invariants.py` asserts those blind spots explicitly, so nobody assumes the lint covers them.

The rule, from the [lint](code/sample_service/tools/lint_invariants.py):
```python
"INV003": dict(
    title="publish failure swallowed inside the relay loop",
    why="skipping a failed row and publishing later rows reorders events for that key "
        "(OrderCancelled can overtake OrderPlaced).",
    fix="`break` out of the loop and leave the row unpublished so the next tick retries it in order. "
        "Never `continue` or `pass` in this handler.",
    see="INVARIANTS.md#i3-per-key-ordering"),
```

### 3. Hermetic fakes that model failure, not just success
A fake broker that always succeeds and delivers exactly once makes every relay and consumer bug untestable. [`orders/broker.py`](code/sample_service/orders/broker.py) is 70 lines, and it models the semantics your invariants depend on:
- **per-key partitioning**, so that ordering is per key, as in Kafka;
- **committed offsets per group**, so that uncommitted messages are redelivered (at-least-once);
- **fault injection**: `fail_next(n)` and `fail_when(predicate)`.

Three rules for fakes:
1. **Model the failure semantics your invariants mention.** If INVARIANTS.md says "at-least-once", the fake must be able to deliver twice.
2. **Verify the fake against the real thing.** Run a shared contract suite against both the fake and a real broker in the integration tier (Testcontainers, or a docker-compose service), so the fake cannot drift into fiction.
3. **Prefer property-based tests for invariants.** Huntley's example is "a customer is charged only once", checked with Hypothesis under fault injection ([Huntley, "nobody should type code by hand anymore"](https://ghuntley.com/agency/)). Generate interleavings of create, cancel, relay, fail and redeliver, and assert I3 and I4 on every run. Exercise 5 has you build this.

### 4. Ephemeral environments per worktree
Parallel agents in parallel worktrees need parallel, isolated environments. OpenAI boots an app instance per worktree, with an ephemeral log and metrics stack the agent can query ([OpenAI](https://openai.com/index/harness-engineering/)). Stripe's agents run on pre-warmed devboxes that spin up in about 10 seconds, isolated from production and the internet. That isolation is what lets them run without per-action permission prompts ([Stripe](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)).

A minimal version with Docker Compose:
```bash
# tools/env_up.sh: one isolated stack per worktree, derived from the worktree path
set -euo pipefail
WT=$(basename "$(git rev-parse --show-toplevel)")
export COMPOSE_PROJECT_NAME="orders-${WT}"           # isolates containers, networks, volumes
export ORDERS_LOG_PATH="$PWD/var/log/orders.jsonl"    # logs land in the worktree for diagnose.py
PORT_BASE=$(( 20000 + $(echo -n "$WT" | cksum | cut -d' ' -f1) % 10000 ))
export KAFKA_PORT=$((PORT_BASE + 1)) PG_PORT=$((PORT_BASE + 2))
docker compose up -d --wait
echo "env up: project=$COMPOSE_PROJECT_NAME kafka=localhost:$KAFKA_PORT pg=localhost:$PG_PORT"
```
Write the ports into a file the agent reads (`var/env.json`), and teardown is `docker compose down -v`. The important properties are no shared state between worktrees and logs written where the diagnose tooling looks for them.

### 5. Contract tests on every interface
The event payload is a contract with every consumer. Make additive-only a check:
- keep a schema (JSON Schema, Avro or Protobuf) per event type in the repo;
- in CI, check that the new schema is backward compatible with the last released one;
- write visible tests as **subset** assertions, so that adding a field does not break them but removing or renaming one does. The sample's `test_create_writes_order_and_event_atomically` does exactly this, which is why the currency feature can add a field without editing an existing test.

### 6. Make "done" checkable, and gate on it
"Done" should be a command with an exit code, not a judgment. Then make the agent unable to stop while it is red. With Claude Code, a Stop hook does this. As of the 2026 hooks docs, a command hook that exits with code 2 blocks the stop and feeds its stderr back to the model:
```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python tools/check.py 1>&2 || exit 2" } ] }
    ]
  }
}
```
The hook input carries a `stop_hook_active` flag, which you can use to avoid blocking forever. Combine it with a budget ([07-loops](../07-loops/README.md), [14-steering-and-guardrails](../14-steering-and-guardrails/README.md)). This is the blocking-gate kind of hook that the course says works. It does not try to steer behavior; it refuses to accept a red result.

## Worked example: the same relay bug, with a terse lint and with a lint that remediates
The `bug-relay-skips-failure` task injects one line into `relay_once`:
```python
        except BrokerError as e:
            log("relay", "publish.failed", ...)
            continue  # don't let one bad row stall the whole relay
```
Every visible test passes. The bug only shows up when a publish fails mid-batch.

### Bad: a generic linter, or no linter
```text
$ python -m pytest -q tests
...........                                                              [100%]
11 passed in 0.06s
```
An agent asked to fix "consumers see OrderCancelled before OrderPlaced" now has green tests and a symptom that lives downstream. A plausible next move is to "fix" it in the consumer by buffering unknown-order cancels. That is a real pattern, and it is wrong here, because the producer is violating I3. This suite's `naive` variant for the task does something else plausible: it retries the publish once inline. That hides a single blip in tests and still skips on a second failure. The hidden test with three consecutive failures catches it.

### Good: the gate includes the invariant lint (real output)
```text
$ python tools/check.py
orders/outbox.py:30:8: INV003 publish failure swallowed inside the relay loop
  why: skipping a failed row and publishing later rows reorders events for that key (OrderCancelled can overtake OrderPlaced).
  fix: `break` out of the loop and leave the row unpublished so the next tick retries it in order. Never `continue` or `pass` in this handler.
  see: INVARIANTS.md#i3-per-key-ordering
lint_invariants: 1 finding(s)
check: FAIL lint=FAIL docs=ok tests=(11 passed in 0.06s) in 0.4s
$ python tools/repro.py broker-blip
FAIL broker-blip: per-key order ['OrderCancelled', 'OrderPlaced']
```
The lint names the line, the invariant, the mechanism ("OrderCancelled can overtake OrderPlaced", which is exactly the bug report) and the fix. The repro confirms it in one line. The agent's job has gone from detective work to a one-word edit plus a regression test. In the autonomy eval, ablating the lint turns this task from PASS to FAIL for the harness-aware fake agent. That result is *simulated by construction* (see [05](05-measuring-autonomy-rate.md)); measuring it with a real agent is Exercise 6.

### Why the eval runs the lint from a pristine checkout
If the gate lives in the agent's repo copy, the agent can edit `lint_invariants.py`. `autonomy_eval.py` runs the lint from the original checkout against the agent's `orders/`, and restores the original visible tests before running them. In production you get the same property from CI config that agents cannot modify, and from CODEOWNERS on `tools/` and `tests/`.

## Pitfalls
- **Slow checks get skipped.** If `check` takes three minutes, the agent runs it once at the end, or never. *Detect it* by timing the gate and counting gate runs per session in traces. Split it into tiers.
- **Flaky tests train the agent to ignore red.** *Detect it* by re-running failures. If the agent's transcript shows "this test is flaky, ignoring", you have a harness bug. Quarantine the test and fix it.
- **Fakes that are too nice.** *Detect it* when a production bug cannot be reproduced against the fake. Add the missing failure mode to the fake before you fix the bug.
- **Lint false positives breed `noqa` spam.** *Detect it* by counting suppressions over time. Each false positive teaches the agent that the lint is optional. Tighten the rule, or delete it.
- **Remediation text that is wrong.** A lint telling the agent to do the wrong thing is worse than no lint, because the agent will comply. Test the fix line: apply it and confirm the lint clears. That is what `test_inv001_state_write_without_outbox` does.
- **Gate in reach of the gated.** *Detect it* when agent diffs touch `tests/` or `tools/` on bug-fix tasks. Flag such diffs for review. The eval reports them as `tamper`.

## In your day job
- Write a `make check` (or `tools/check.py`) that finishes in under 30 seconds and prints only failures. Put "done means `make check` exits 0" in AGENTS.md.
- Pick the invariant that has burned you most often and write one custom lint for it, with why, fix and see lines.
- Audit your fakes against INVARIANTS.md. For each delivery or failure semantic you listed, ask whether the fake can produce it.
- Add a Stop hook (or your agent's equivalent) that runs the gate, and remove any "please verify your work" lines from your prompts.
