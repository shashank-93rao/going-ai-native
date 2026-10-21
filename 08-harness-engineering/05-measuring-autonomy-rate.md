# 05: Measuring agent-readiness: the autonomy rate

## The idea
"Is our harness good enough for agents to work independently?" is an empirical question, so measure it.

**Autonomy rate**: the fraction of tasks, drawn from a seeded suite of realistic features, bugs and production-style incidents, that an agent completes with **no human input**. Completion is judged by checks the agent could not see or modify.

Report it **per task class**, **with a confidence interval**, and for a stated **model + agent product + harness version**. Then improve it by changing **only the harness**, one component at a time, and re-measure. That makes "agent-readiness" a number you can hill-climb, the same way you would hill-climb p99 latency with a fixed load test.

## Why it matters
- **Teams overestimate.** METR's 2025 study found experienced developers were slower with AI tools on their own repos while believing they were faster ([00-orientation](../00-orientation/README.md)). Your sense of how well agents work in your codebase is a perception. The autonomy rate is a measurement.
- **Naive scoring is badly inflated.** In this module's suite, a do-nothing agent that changes no files passes the visible tests on **7 of 8 tasks**. Most seeded bugs are not caught by existing tests; if they were, they would not have shipped. Adding the invariant lint still leaves **5 of 8**. Only hidden tests drop it to **0 of 8**. Those are real numbers from `autonomy_eval.py --agent "... --policy noop"`. "CI is green" is not a completion signal for bug and incident tasks.
- **Small suites are noise.** At 7/8 the 95% Wilson interval is 53%–98%. At 36/40 it is 77%–96%. Anthropic measured a 6-point swing on Terminal-Bench 2.0 from infrastructure configuration alone, and advises distrusting gaps under about 3 points without matched setups ([Anthropic, "Quantifying infrastructure noise"](https://www.anthropic.com/engineering/infrastructure-noise)).
- **Integrity failures are real.** Anthropic reports that Claude once used git history from earlier trials in an eval, and that "0% pass@100 is most often a signal of a broken task" ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).

## How to do it

### 1. Seed the suite from your own history
Aim for **20–50 tasks** to start, the range Anthropic recommends for a first agent eval, drawn from real work. Expand later.

| Kind | Source | How to build it |
|---|---|---|
| **Bug** | A past bug-fix commit | Revert the fix as the `inject` edit. The fix's regression test becomes the hidden test. The prompt is the original ticket text. |
| **Incident** | A postmortem | Inject the root cause. Generate logs by running the buggy code under the incident's traffic pattern (`tasks/gen_incident_logs.py`). The prompt is the alert text plus on-call context. |
| **Feature** | A recent feature PR | Start from the parent commit. The PR's tests, plus invariant tests the PR author *should* have written, become hidden tests. The prompt is the ticket. |

This is a scaled-up version of Hashimoto's step 2, "reproduce your own past commits with an agent" ([Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey)). Write prompts as the real requester would: alert text, not a diagnosis. Writing the root cause into an incident prompt measures reading comprehension, not diagnosis.

### 2. Task anatomy and validity
Each task in [`code/tasks/`](code/tasks/) has:

```text
tasks/inc-stats-drift/
  task.toml          id, kind, prompt, needs, inject (the bug), solution/naive edits
  hidden_checks.py   copied in as _hidden_tests/test_hidden.py only after the agent exits
  incident.jsonl     real logs produced by the buggy code (incidents only)
```

Validate every task before trusting any score. `test_every_task_oracle_can_fail_and_can_pass` does this for the whole suite:
1. **The oracle can fail**: the hidden tests fail on the injected state. Otherwise the task is free.
2. **The oracle can pass**: the reference fix passes the hidden tests, the original visible tests and the lint. Otherwise the task is broken. This is Anthropic's "0% pass@100" warning, caught before you run.
3. **The oracle discriminates**: the `naive` fix fails. Without a plausible wrong answer, you do not know whether your hidden tests test the invariant or just the happy path.
4. **The oracle does not over-fit to one fix.** Write a second, differently shaped correct fix and confirm it passes. Hidden tests that assert implementation details (a specific function name, a specific SQL string) reject valid solutions and depress the rate for the wrong reason.

### 3. Isolation and integrity
- **Fresh copy per trial.** No shared state and no `.git` history, so there is no fix to find in `git log`. `build_workspace` copies the service tree only.
- **Graders outside reach.** Hidden tests are copied in after the agent exits. The original visible tests and `conftest.py` are restored over whatever the agent left. The lint runs from the pristine checkout. `tampered` records any protected file the agent changed.
- **Sandbox the agent** so it cannot read `tasks/`, where the hidden tests and reference fixes live, or reach the network beyond what the task needs ([16-security-and-containment](../16-security-and-containment/README.md)).

### 4. Scoring and statistics
Success = hidden tests pass **and** original visible tests pass **and** the original lint passes **and** no timeout.

```text
autonomy rate: 7/8 = 88%  (95% Wilson CI 53%-98%)
  feature   3/3  CI 44%-100%
  bug       1/2  CI 10%-90%
  incident  3/3  CI 44%-100%
tasks passing every trial (pass^k): 7/8
```
- Use **Wilson** intervals rather than the normal approximation. At small n and near-extreme rates, the normal approximation produces intervals that cross 100%.
- **Trials are not independent.** Three trials of the same task are correlated. Wilson over all trials overstates precision, so for decisions, bootstrap over *tasks* or use clustered standard errors ([12-hill-climbing](../12-hill-climbing/README.md)).
- **Report pass^k alongside the mean.** If you want to hand a task class to agents unattended, you care whether it works *every time*: at 75% per trial, pass^3 is about 42% ([10-evals-fundamentals](../10-evals-fundamentals/README.md)).
- **Per-class rates drive decisions.** "Features 85%, incidents 30%" means you let agents run on features with risk-tiered review, and that your next harness work is Diagnose.

### 5. Hill-climb the harness only
Freeze the model, the effort setting and the agent product version. Change one harness component per round:

1. **Noise check first.** Run the baseline twice. If the two runs differ by more than the smallest gain you would act on, add tasks or trials before you start.
2. **Split** tasks into a working set and a held-out set. Iterate on the working set.
3. **One root-cause change per round**, from reading failing transcripts. Examples: a lint for a pattern the agent kept getting wrong, a diagnose subcommand, an INVARIANTS.md "typical break" line.
4. **Revert rules**, from Anthropic's hill-climbing guidance: working set up but held-out flat means revert, because you overfit. Any regression means revert. Both up means keep ([Anthropic, "Automating eval design and hillclimbing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).
5. **Never paste the task into the harness.** "If the hillclimber reads the failing transcripts, it should never paste the failure content into the prompt" (same source). An AGENTS.md line that says "the 409 bug is in request_hash" is overfitting. A lint against clocks in request hashes is a harness improvement. LangChain's version of the warning: "Changes that overfit to a task are bad for generalization and can lead to regressions in other Tasks" ([LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)).

### 6. Ablate on every model upgrade
Each harness component encodes an assumption about what the model cannot do on its own ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps)). When the model changes, re-run the suite with each component removed:

```bash
for c in agents_md invariants architecture lint diagnose repro skills; do
  python autonomy_eval.py --agent "$AGENT" --ablate "$c" --trials 3 --json "ablate-$c.json"
done
```
Read the results as a table, component by delta:
- if removing it does not hurt, it is a candidate for deletion;
- if removing it *helps*, delete it now. Opus 5's over-verification is the canonical case ([06](06-entropy-and-harness-decay.md));
- if removing it hurts a lot, keep it, and ask whether it can become a check instead of prose.

### 7. Pointing it at a real agent
The eval takes any command template. Run real agents inside a container or VM with network egress limited and `tasks/` not mounted:
```bash
# Claude Code, print mode, inside a sandbox (flags as of Claude Code 2.x; check `claude --help`)
python autonomy_eval.py --jobs 2 --trials 3 --timeout 1200 \
  --agent 'sh -c "claude -p \"$(cat {prompt})\" --dangerously-skip-permissions"'   # cwd is already {workdir}

# This module's minimal agent on the real API (needs ANTHROPIC_API_KEY)
python autonomy_eval.py --agent "{python} {here}/mini_agent.py {workdir} {prompt} --max-turns 40"
```
`--dangerously-skip-permissions` is only acceptable inside a disposable sandbox. That is the whole reason the workspace is a throwaway copy.

## Worked example: three ways to score the same runs
Run the same agent over the 8-task suite and score it three ways. The agent here is the `noop` fake, which does nothing, so any score above zero is pure inflation. The outputs are real.

**Bad: "the agent said it was done" or "CI is green".** A do-nothing run passes the visible tests on 7 of 8 tasks. Only `bug-double-cancel` has a visible failing test, because it was seeded as "CI is red on main".

**Better: visible tests plus the invariant lint, run from pristine.** 5 of 8. The lint catches the two injected bugs it has rules for (INV003 and INV005).

**Right: hidden tests + original visible tests + original lint.**
```text
$ python autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy noop {workdir} {prompt}"
task                       kind      ok   hidden  visible  lint  tamper  secs
bug-double-cancel          bug       FAIL False   False    True  -       1.33
bug-relay-skips-failure    bug       FAIL False   True     False -       1.35
feat-cancel-stats          feature   FAIL False   True     True  -       1.34
...
autonomy rate: 0/8 = 0%  (95% Wilson CI 0%-32%)
```

Now the harness ablation, using the `harness-aware` fake agent. **These numbers are simulated by construction.** The fake applies the reference fix only if the files listed in the task's `needs` exist, and otherwise applies its naive fix or gives up. They demonstrate the *mechanics* of an ablation study, not a finding about real agents:

| Ablated | Autonomy rate | Tasks lost |
|---|---|---|
| none | 8/8 | |
| `lint` | 7/8 | bug-relay-skips-failure |
| `agents_md` | 6/8 | feat-list-orders, bug-double-cancel (tampers with the test) |
| `invariants` | 5/8 | feat-currency (forgets the hash), feat-cancel-stats, inc-stats-drift |
| `diagnose` | 5/8 | all three incidents |
| all | 0/8 | |

The real experiment is Exercise 6: run the same table with Claude Code or `mini_agent.py` on the real API, three trials each, and see which components a current model actually needs.

## Pitfalls
- **Reporting one number.** A blended rate hides that incidents are at 20%. *Detect it* when the report has no per-class breakdown. Always split by kind.
- **Leaky tasks.** The reference fix is findable in git history, a sibling directory, or the prompt itself. *Detect it* by grepping agent transcripts for paths outside the workdir, and by checking whether success correlates with transcript length suspiciously.
- **Brittle hidden tests.** *Detect it* with the second-valid-fix check. If a correct alternative fails, the test checks implementation, not behavior.
- **Hill-climbing on the reporting set.** *Detect it* when the working set improves and the held-out set does not. Revert.
- **Infrastructure noise read as signal.** Timeouts, OOMs and rate limits show up as failures. *Detect it* by tracking infra errors separately (`timed_out`, agent exit codes) and re-running them, not counting them.
- **A suite that never changes.** As the harness improves, tasks saturate. Anthropic's advice is to graduate saturated capability tasks into a regression set and add harder ones. *Detect it* when a class sits at or above 95% for several runs.

## In your day job
- Seed ten tasks this month: three reverted bug fixes, three features from recent PRs, and four incidents from postmortems. Write the hidden tests to assert invariants, not symptoms.
- Run your current agent setup over them, three trials each, and publish the per-class autonomy rate with intervals to your team. Expect it to be lower than anyone's guess.
- Pick the worst class and make one harness change. Re-run. Keep it only if held-out improves.
- Put "run the ablation" on the checklist for adopting a new model, next to "run the effort sweep".
