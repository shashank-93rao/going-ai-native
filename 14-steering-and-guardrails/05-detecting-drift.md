# 05: Detecting drift early

## The idea

**Drift** is when a run's trajectory diverges from what you intended, *before* any final check fails. It covers the agent that refactors a module you didn't mention, adds a dependency, retries the same failing command six times, or starts negotiating with the test suite. By the time the Stop gate sees the result, you've paid for an hour of tokens and you have a 900-line diff to review or throw away.

So you need **leading indicators**: cheap signals during the run that correlate with a bad outcome. In SRE terms, the Stop gate is the end-to-end probe and drift signals are the saturation and error-rate alerts that fire first.

This module uses five signals, in order of leverage:

1. **Plan review**, before any code is written.
2. **Checkpoints** at plan steps, with a check at each one.
3. **Beck's three warning signs**: loops, unrequested functionality, and cheating on tests.
4. **Diff-size alarms** against a budget the plan set.
5. **Out-of-plan files**: the diff touches paths the plan didn't name.

Signals 3 to 5 are mechanical. [`code/drift_monitor.py`](code/drift_monitor.py) implements them over a diff and a tool-event stream.

## Why it matters

- **The cheapest place to catch drift is the plan.** Dex Horthy's argument is that human review has the most leverage at the research and plan stages, because one bad line of research becomes thousands of bad lines of code. His failure case was a shallow-research attempt to remove Hadoop from parquet-java ([HumanLayer, ACE-FCA](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)).
- **Kent Beck's warning signs.** Describing his augmented-coding sessions, Beck lists three: "Loops.", "Functionality I hadn't asked for (even if it was a reasonable next step).", and "Any indication that the genie was cheating, for example by disabling or deleting tests." When he saw them he watched more closely, "ready to intervene & stop unproductive development" ([Beck, "Augmented Coding: Beyond the Vibes"](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)).
- **Scope drift is the most common judge veto at Spotify.** Their diff-vs-prompt judge vetoes about a quarter of sessions, and the most common trigger is "the agent going outside the instructions outlined in the prompt" ([Spotify Engineering, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)).
- **Newer models expand scope by default.** The Opus 5 guide warns it "can also expand the scope of a task, adding steps that weren't requested", and provides a scope prompt ("Deliver what was asked, at the scope intended...") ([Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). The prompt helps. The monitor tells you whether it helped.

## How it works

### 1. The plan is a contract

A plan that drift can be measured against has machine-readable parts:

```json
{
  "task": "Fix duplicate charges on client retry: ChargeService must dedupe on the Idempotency-Key, not the request id.",
  "files": ["services/payments/idempotency.py", "services/payments/tests/test_idempotency.py"],
  "may_create": ["services/payments/tests/test_*.py"],
  "max_changed_lines": 80,
  "allow_dependency_changes": false,
  "allow_test_deletions": false,
  "edit_limit_per_file": 6,
  "repeat_failure_limit": 3
}
```

`drift_monitor.py` also reads a `PLAN.md` with paths as bullets under a `## Files` heading, which is the shape plan mode tends to produce. Use plan mode (`claude --permission-mode plan`, or Shift+Tab) to have the agent write the plan, edit it with Ctrl+G, and save the file list into `.agent/plan.json` before you approve. A plan without a file list and a size estimate is a wish, not a contract.

### 2. Checkpoints

Long tasks get checkpoints at plan steps. At each one, run the fast check, commit (so the diff for the next step is small and reviewable), and run the drift monitor against the plan. Committing per step also gives the Stop gate's `git diff HEAD` a meaningful baseline. Set `STOP_GATE_BASE` to the branch point if you want the gate to see the whole task.

### 3–5. Mechanical signals

| Signal | Check in `drift_monitor.py` | Level |
|---|---|---|
| File not in plan | `out_of_plan_file` | warn |
| 3+ files not in plan | `scope_creep` (Beck's "functionality I hadn't asked for") | stop |
| Dependency manifest changed without permission | `dependency_change` | stop |
| CI config changed | `ci_config_changed` | stop |
| Test file deleted | `test_deleted` (Beck's "cheating") | stop |
| Churn > budget / > 2× budget | `diff_size` | warn / stop |
| Same file edited > N times | `edit_loop` (Beck's "loops") | warn |
| Same command failing N runs in a row | `repeated_failure` | stop |

**Warn goes to a human. Stop halts the agent.** This split is deliberate and follows [03](03-hooks-as-gates.md). In `--hook` mode, a warn is emitted as a `systemMessage`, which the user sees and the agent doesn't, and a stop is emitted as `decision: block` with a concrete instruction ("revert the out-of-scope changes, or stop and ask the user to extend the plan"). A monitor that only *tells the agent* it's drifting is a steering hook, and steering hooks mostly fail.

The edit-loop idea has precedent. LangChain's harness work reportedly used a loop-detection middleware that counts edits per file and, past a threshold, injects a "reconsider your approach" prompt (reported in the course research notes and not re-verified here). The monitor here counts the same thing but routes the signal to a human instead.

**Diff size as an SLO.** The plan's `max_changed_lines` is an error budget. Overrunning it doesn't prove anything is wrong, since sometimes the fix really is bigger. It does mean the plan was wrong, and the *human* should decide whether to extend it. This is the same reasoning as paging on burn rate rather than waiting for the SLO to be breached.

## Worked example: an idempotency fix that turned into a retry framework

Task as in the plan above. The agent's run produced [`code/data/drift_run.diff`](code/data/drift_run.diff) and the tool-event log [`code/data/run_events.jsonl`](code/data/run_events.jsonl). Here is the story they tell:

1. It edits `idempotency.py` to look up by `key`, which is correct and in plan.
2. `pytest` fails. It edits again, and `pytest` fails again. Then once more.
3. It concludes the gateway is flaky, adds `tenacity` to `requirements.txt`, writes `services/payments/retry.py`, and wraps `StripeGateway.charge` in `@with_retries`. **Retrying a non-idempotent charge call is the exact bug class the task was meant to fix.**
4. While it's there, it bumps `DEFAULT_PAGE` in `services/ledger/export.py` from 100 to 500.

Running the monitor (measured, actual output):

```text
$ python drift_monitor.py --plan data/plan.json --diff data/drift_run.diff --events data/run_events.jsonl
drift verdict: STOP  (5 files, 16 lines changed)
  [warn] out_of_plan_file: services/payments/retry.py (added, 6 lines) is not in the plan
  [stop] dependency_change: requirements.txt changed; the plan does not allow new dependencies
  [warn] out_of_plan_file: services/payments/gateway.py (modified, 3 lines) is not in the plan
  [warn] out_of_plan_file: services/ledger/export.py (modified, 2 lines) is not in the plan
  [stop] scope_creep: 3 files outside the plan (Beck: functionality nobody asked for)
  [stop] repeated_failure: `pytest -q services/payments` failed 3 consecutive runs; the edits in between are not converging
$ echo $?
2
```

Note what did *not* fire. The diff is 16 lines, well under the 80-line budget. A size alarm alone would have passed this run. The dangerous change (`@with_retries` on `charge`) is 3 lines. **Scope signals catch what size signals miss.** The converse also holds: a 600-line in-scope rewrite trips only the size alarm.

The planned fix, [`code/data/clean_fix.diff`](code/data/clean_fix.diff), touches only the two planned files:

```text
$ python drift_monitor.py --plan data/plan.json --diff data/clean_fix.diff
drift verdict: OK  (2 files, 21 lines changed)
```

**What the human does with a STOP.** Read the `repeated_failure` flag first: the agent was stuck *before* it drifted. The drift was a symptom, the agent inventing a cause ("the gateway is flaky") to explain failures it didn't understand. The right intervention is a [04](04-mid-run-steering.md)-style nudge with the actual failing assertion and a fence ("no retries in the charge path"), or `/clear` with a better prompt. Telling it to "stay in scope" isn't enough.

## Pitfalls

- **Plans too vague to measure.** "Fix the idempotency bug" has no file list, so every file is out of plan or none is. *Detect:* if `.agent/plan.json` has fewer than one entry in `files`, refuse to start the run.
- **Legitimate discoveries flagged as drift.** Sometimes the fix really does need `gateway.py`. The right response is for a human to amend the plan, not to loosen the monitor. *Detect:* track how often plans get amended. If it's most runs, your planning step is too shallow.
- **Generated and vendored files.** Lockfiles, generated protobufs and snapshots inflate churn. Exclude them from the size budget explicitly, and never implicitly.
- **Splitting to dodge the size alarm.** An agent in a loop that commits per step can keep each diff small while the cumulative change grows. *Detect:* measure against the task's branch point, not just `HEAD`.
- **Monitoring that reports only to the agent.** It reads the warning as advice and carries on. *Detect:* check where your warn output goes. If it isn't a human-visible channel (`systemMessage`, inbox, PR comment), it's a steering hook.
- **Loop detection without outcome data.** Repeated identical commands with *different* outputs may be legitimate progress. Fingerprint the failure output when you can, as `stop_gate.py` does.

## In your day job

- Make "plan with a file list and a line budget" a precondition for any agent task bigger than a one-sentence diff. Store it as `.agent/plan.json` next to the branch.
- Wire `drift_monitor.py --hook` as a second Stop hook (see `settings.example.json`) and look at the warn rate for a week before you tighten anything.
- In review, read the drift report before the diff. Out-of-plan files are where the surprises are.
- Treat "the agent retried the same failing command three times" as a page, not a log line. It's the earliest signal that the run is going nowhere.
