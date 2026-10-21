# Exercises

Exercises 1–5 run offline. Exercises 6 and 7 use a real coding agent and your real work. All commands assume `cd 00-orientation/code` and the course venv. If you haven't run `pip install -e .` at the course root, prefix scripts that import `ainative_kit` with `PYTHONPATH=../../shared`.

---

## 1. Score five of your own tasks (30 min, offline)

**Goal.** Build the habit of scoring verifiability before choosing a mode.

**Steps.**
1. Pick five tasks from your current backlog: at least one design task, one bug, and one bulk or mechanical change.
2. For each, fill in the scorecard from [01](01-verifiability-thesis.md): resettable, efficient, rewardable, faithful. Write one line on *what artifact* gives each property, or "none".
3. For each task scoring "no" on faithful, write the check you'd build, as a concrete command or test name.

**Done when.** You have a 5-row table, every "yes" names an artifact (not "we have tests"), and at least two rows have a concrete proposed check.

**Stretch.** Build one of the proposed checks and show it failing on `main`.

---

## 2. Run the dial on your backlog (30 min, offline)

**Goal.** Use `autonomy_dial.recommend` as a decision aid, and find where you disagree with it.

**Steps.**
1. Encode your five tasks from Exercise 1 as `Task(...)` objects in a scratch script and print `recommend(t)` for each.
2. For every recommendation you disagree with, write which input you think is mislabelled, or which rule is missing.
3. Add one rule to `autonomy_dial.py` that you believe in (for example, "anything touching `auth/` caps at supervised"). Add a failing test first, then make it pass.

**Done when.** `pytest -q` passes with your new test, and you have written down one disagreement with the default rules and how you resolved it.

**Stretch.** Run `extract_features` with a real API key on three ticket descriptions, and compare its labels to yours. Where it was more aggressive than you, check whether the fallback rule should have caught it.

---

## 3. Audit a productivity claim (20 min, offline)

**Goal.** Apply the five-question audit from [04](04-honest-evidence.md).

**Steps.**
1. Find a real productivity claim: a vendor case study, an internal update, or a conference talk.
2. Fill in the audit table: which tasks, which oracle, which outcome variable, who chose, which model generation.
3. Write one sentence on what the claim *is* evidence for.

**Done when.** Every row is filled in or marked "not stated", and your one-sentence conclusion is narrower than the claim's headline.

---

## 4. Plant an effect and try to find it (30 min, offline)

**Goal.** Learn what n you need before you trust your own A/B.

**Steps.**
1. Run `python simulate_ab.py --out /tmp/sim.jsonl --tasks 20 --true-ratio 0.8` and then `python selfmeasure.py --log /tmp/sim.jsonl summary --outcome active`.
2. Repeat with `--seed 1` through `--seed 5`. Record the estimate-adjusted ratio and whether its CI excludes 1.0.
3. Repeat with `--tasks 60` and `--tasks 120`.
4. Compare the "Detectable at this n" line with your hit rate.

**Done when.** You have a table (n × seed → ratio, CI excludes 1?) and one sentence on the smallest n at which a 20% speedup was found in most seeds, and whether that matches the power line.

**Stretch.** Plant `abandon_p={"ai": 0.0, "no_ai": 0.3}` by calling `simulate()` from Python, and confirm the summary's warning fires. Then explain in two sentences which direction differential abandonment biases the estimate when the abandoned tasks are the hard ones.

---

## 5. Check the interval's coverage (40 min, offline)

**Goal.** Verify, rather than accept, the claim in [05](05-measure-yourself.md) that the bootstrap under-covers at small n.

**Steps.**
1. Write a script that runs `simulate()` for 200 seeds at `n_tasks=40, true_ratio=1.19`, then calls `summarize(..., outcome="active")` and records whether `time_adjusted.ci` contains 1.19.
2. Swap `welch_ratio_ci` for `bootstrap_ratio_ci` inside `_effect` and repeat.
3. Repeat both at `n_tasks=120`.

**Done when.** You report four coverage numbers (2 methods × 2 sizes) and say whether the gap closes at larger n. The module's own run gave about 95.5% for Welch and 92% for the bootstrap at 40 tasks. Yours should be close to those, but needn't match exactly.

---

## 6. Move one task right on the dial (60–90 min, real agent)

**Goal.** Experience the leash moving from the diff to the harness on one real task.

**Steps.**
1. Pick a task the dial places at `pair` or `supervised_agent` because its oracle is `weak` or `partial`.
2. Have the agent build the oracle first, and confirm it fails on `main`.
3. Write a Stop hook gate (see [02](02-the-leash-moved.md)) that runs the oracle and rejects out-of-scope files.
4. Run the change as a supervised agent and review only the done-when, the test names, and the check output.

**Done when.** You can show (a) the oracle failing on `main`, (b) at least one iteration where the Stop hook sent the agent back, and (c) a merged PR whose review took less of your time than your usual review for that kind of change. Record (c) in your log.

**Stretch.** Seed a bug in the agent's branch by hand and confirm your oracle catches it.

---

## 7. Start your personal A/B (setup 30 min, then 4–8 weeks)

**Goal.** Measure your own effect with randomization.

**Steps.**
1. Write and freeze your arm definition (template in [05](05-measure-yourself.md)), including the stop rule.
2. Generate and store `SELFMEASURE_SEED`. Point `SELFMEASURE_LOG` at a file you back up.
3. At each planning session, register the batch, then run `assign` once.
4. Log `start`, `merge --active`, `perceive`, and any `rework` or `abandon` as they happen.
5. At the stop rule, run `summary` for both outcomes.

**Done when.** At least 20 tasks per arm are logged with no edited lines (the fold raises on re-assignment or out-of-order events, so a clean `summary` run is the check). You have written a 5-line result: estimate, CI, perceived ratio, power line, and one surprise.

**Stretch.** Run a second A/B where both arms use AI, comparing two harness variants, such as your CLAUDE.md before and after pruning.
