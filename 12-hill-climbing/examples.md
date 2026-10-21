# Examples: hill-climbing on a Monday morning

Five scenarios from a platform team's week. Numbers marked *(illustrative)* are invented to show the shape of a decision. Numbers marked *(simulated)* come from this module's code.

---

## 1. "+3 points, ship it": the Friday prompt PR

**Situation.** A teammate opens a PR against the Kafka consumer-lag **log summarizer**. That is the LLM step that turns a lag alert plus 2,000 lines of consumer logs into a three-bullet summary for the on-call engineer. The PR description reads: "Reworded the instructions to emphasize root cause. Eval: 71.0% → 74.0%." The eval has 150 incidents, and a binary judge checks whether the summary names the actual root cause.

**Naive approach and what happens.** Two single runs, one per branch, compared by point estimate. It merges. Two weeks later a second "improvement" reports 74 → 72 and is blamed on judge noise. Nobody knows whether either change did anything.

**AI-native approach.**
1. Run the noise check on `main`'s config before looking at the PR:
   ```bash
   python noise_check.py --config configs/summarizer-main.json --runs 6 --repeats 3 --min-effect 0.03
   ```
   ```text
   | SE of one run: naive / clustered | 3.7 / 4.6 pts |
   | minimum detectable effect (80% power) | 5.9 pts |
   | smallest effect you'd act on | 3.0 pts |
   Verdict: TOO NOISY: raise repeats to ~12 or add items/clusters before round 1.
   ```
   *(illustrative)*. The eval cannot see a 3-point change at all. Concept 02 says to treat even that MDE as optimistic for targeted changes.
2. Re-run both configs on the same 150 incidents with 3 repeats and compare them paired and clustered (clustered by consumer group, because 40 of the incidents come from the same three groups):
   ```text
   paired, clustered Δ = +1.3 [-2.9, 5.5] pts   McNemar (repeat 0): b01=14, b10=11, p=0.69
   ```
   *(illustrative)*.
3. Log the row as `revert: within noise`, keep the hypothesis, and open a ticket to grow the eval to about 400 incidents across at least 60 consumer groups (`required_n_paired` with the measured SD of differences).

**What to check.** Did the PR report a CI at all? Is the eval clustered, and was the clustered SE used? Was the MDE computed before anyone looked at the delta?

---

## 2. A new model ships: the upgrade drill on the incident router

**Situation.** A new model lands, cheaper per token and reportedly better at reasoning. Product asks: "Can we switch the incident router this week and cut the bill?"

**Naive approach and what happens.** Swap the model ID in prod config, eyeball 20 alerts, ship. Accuracy is about the same, cost is lower, everyone is happy. Three months later someone notices the tie-break prompt section, the verification retry, and an "IMPORTANT: always consider timestamps" line, all written for the old model, are still there. Nobody knows if they help, and one of them is causing over-long outputs on the new model.

**AI-native approach.**
1. The frontier configs are already committed. Run the drill:
   ```bash
   python pareto.py --drill candidate-model-x
   ```
2. Read the drill table *(simulated)*. At low effort the new model matches the current production config:
   ```text
   | sonnet-5-5/high | 89.2 | 89.7 | +0.5 [-0.7, 1.6] | 8.58 | 4.29 |
   | haiku-5-5/low   | 77.5 | 89.5 | +11.9 [8.4, 15.4] | 0.07 | 0.71 |
   ```
3. Ablate on the cheap new point:
   ```text
   | -section:queue_definitions | -9.1 [-12.5, -5.7] | still load-bearing |
   | -section:tiebreak          | -0.5 [-1.8, 0.8]   | no measurable value: candidate to delete |
   | -tool:lookup_owner         | -6.0 [-9.3, -2.7]  | still load-bearing |
   ```
4. Build the candidate config (new model, low effort, tie-break section deleted). Compare it paired on test against production: −0.8 [−2.1, 0.6] at $0.64 vs $8.58 per 1k *(simulated)*. Non-inferior within the gate's 2-point max-drop.
5. Regenerate `ci/baseline_real_results.json` for the new config on `main`, then ship behind a canary ([Module 15](../15-observability-and-production/README.md)).

**What to check.** Were configs compared at explicit, equal-footing effort settings? Did the ablation delete anything, or does the scaffolding only ever grow? Did the baseline for the CI gate move with the switch?

---

## 3. The overnight agent climb that reported 94%

**Situation.** You point a coding agent at the log summarizer with a `program.md` and leave it running overnight. In the morning its summary says: "Raised accuracy from 74% to 94% in 11 rounds."

**Naive approach and what happens.** You read the agent's summary, glance at the diff, and merge. The production complaint rate does not move.

**AI-native approach.**
1. Ignore the narrative. Open `runs/overnight/experiments.md` and the config diff. The log shows round 7 kept with Δdev +14.2 and Δtest +1.1. That kept row should have been reverted under the 0.5 ratio rule, so the agent was running an older copy of the rules.
2. Diff the prompt. The kept "summary template" section contains the literal consumer-group names and lag numbers from 23 dev incidents *(illustrative)*. That is a paraphrase leak. A verbatim check misses it because the agent reformatted the numbers.
3. Fix the environment, not the prompt: mount `eval/` read-only, run `decide()` from a pinned copy the agent cannot edit, and add an n-gram overlap check (5-grams shared with any eval item) next to `leaked_items`.
4. Re-run from the last clean config with the guards on. Read the lockbox once at the end: 78.4 [74.0, 82.8] against test 79.1 *(illustrative)*. A real 5-point gain, not 20.

**What to check.** Does the log's decision column match the rules in the repo's `decide()`? Can the agent write anywhere under the eval directory? Was the final number a lockbox read, or the agent's own report?

---

## 4. Scores swing 6 points between runs: infra noise in an agentic eval

**Situation.** You run a coding-agent eval, "fix the flaky integration test in this Java service", in containers on CI runners. Monday's run says 58%, Tuesday's says 52%, with no code change. Someone proposes reverting Monday's harness change.

**Naive approach and what happens.** Treat the 6-point swing as a regression and revert. Wednesday's run says 57% and the team stops trusting the eval.

**AI-native approach.**
1. Recall the reference point. Anthropic measured a 6-point Terminal-Bench 2.0 spread from infrastructure configuration alone ([infra-noise post](https://www.anthropic.com/engineering/infrastructure-noise)).
2. Split failures into *task* failures and *infra* failures: OOM-killed containers, Maven download timeouts, pod evictions. Tuesday shows 9% infra errors against Monday's 2% *(illustrative)*, all on the spot-instance runner pool.
3. Pin the resource spec per task with a guaranteed allocation and a separate kill threshold (roughly 3x headroom, per the same post). Pin the runner pool, and record both in the run metadata.
4. Run baseline and candidate **interleaved** in the same window on the same pool, with 3 repeats, and compare them paired. Report infra errors as their own column in `experiments.md`.

**What to check.** Is "infra error" a distinct outcome in your grader, or does it count as a wrong answer? Are baseline and candidate ever run on different days or pools? Is the resource configuration in the log?

---

## 5. The eval is saturated: climb cost instead

**Situation.** A schema-migration reviewer flags unsafe Postgres migrations (a table rewrite under lock, a missing `CONCURRENTLY`). It sits at 96% on its eval, on the largest model at high effort, and costs more than the rest of the team's LLM spend combined.

**Naive approach and what happens.** "It's at 96%, there's nothing to climb." The bill keeps growing with PR volume.

**AI-native approach.**
1. Anthropic's build-eval diagnostics suggest that at a baseline of about 95% or higher you should optimize cost or latency instead of quality, and that "cost reduction at performance parity" is a strong objective even on a saturated eval ([Lance Martin, claude.dev](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).
2. Change the objective in the variants file: rounds are model and effort steps *down*. The rule becomes **non-inferiority**: keep if the paired test Δ has a lower bound above −1.5 points and cost falls.
3. Sweep. The mid-tier model at medium effort comes in at −0.4 [−1.2, 0.5] on test at 0.3x cost *(illustrative)*. Keep.
4. Because the eval is saturated, add headroom before the next quality climb: harvest the 2% of production migrations that reviewers overrode, and add human-judged hard cases (multi-statement migrations, partitioned tables). Avoid filling it only with the current model's failures (concept 03's adversarial-sampling trap).

**What to check.** Is the non-inferiority margin written down before the sweep? Does the cost gate in CI move to the new baseline? Is anyone adding hard cases, or is the eval left saturated forever?
