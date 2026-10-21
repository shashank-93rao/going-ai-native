# Examples: LLM-as-judge on a Monday morning

Each scenario follows the same shape: situation, the naive approach and what happens, the AI-native approach with artifacts, and what to check. Model outputs marked *(illustrative output)* were not produced by a real run.

---

## 1. Gating status-page incident summaries

**Situation.** Your incident tool drafts the customer-facing summary from the incident record. The SRE lead wants a check that blocks a draft from being published when it gets customer impact wrong. Two bad drafts have already gone out: one said "data loss" for a delay, and one said "all regions" for a single-region outage.

**Naive approach.** Add a prompt: "Rate this summary 1-10 for accuracy. Block below 7." It ships in an hour. A week later someone notices it gave 9/10 to a draft that said 9,870 customers were double-charged, when the facts say nobody was. The draft was long, specific, and confidently wrong, which is exactly what a quality scale rewards (`compare_judges.py` shows the same pattern offline: 11 of 25 wrong summaries scored 5/5).

**AI-native approach.**
1. **Split by grader** ([01](01-when-you-need-a-judge.md)). A regex blocks internal hostnames. A timestamp extractor checks the window against the facts. A code check requires a count, a percentage, or "no customer impact". The judge handles one question only: *are the impact claims correct?*
2. **Write the rubric as claims** ([02](02-binary-rubrics-and-critiques.md)). Use `INCIDENT_IMPACT` in `code/judge.py`: severity must match ("delayed is not lost, slow is not failed, partial is not total"), scope must match, and fair rounding is fine.
3. **Label 200 drafts** from the last quarter: the on-call lead gives a verdict plus one sentence of critique for each. Split them by hashing the id: 15/40/45.
4. **Iterate on dev**, reading critiques for every disagreement. Freeze. Read test once:
   ```text
   TPR 0.88  95% CI [0.79, 0.93]   TNR 0.80  95% CI [0.70, 0.87]   kappa 0.68
   ```
   *(illustrative output)*
5. **Decide the operating point.** Publishing a wrong impact statement costs far more than holding back a correct one for human review. So a judge FAIL routes the draft to a human; it doesn't block the incident. Lower TPR is acceptable here, and low TNR is not.
6. **Report the corrected pass rate** weekly, with its CI, using `calibrate.py`.

**What to check.**
- The few-shot ids are all from train (`test_few_shot_uses_train_split_only_and_is_balanced`).
- TNR's CI lower bound is above the rate the SRE lead signed off on.
- A random 20% of judge PASSes go to the annotation queue, so you keep measuring false passes ([06](06-who-validates-the-validators.md)).

---

## 2. Measuring an AI code reviewer: "did it find a real bug?"

**Situation.** Your team runs an AI reviewer on every PR. Leadership wants to know whether it's worth the noise. You need its precision on bug claims: of the comments that claim a defect, how many are real?

**Naive approach.** Count thumbs-up reactions on review comments. Engineers react to comments that sound smart, and ignore ones they didn't read. The thumbs-up rate goes up after a prompt change that makes comments longer and more confident.

**AI-native approach.**
1. **Narrow the population.** A code check classifies comments into "claims a defect" and "style/question" by looking for a defect claim in a structured field the reviewer emits. Only defect claims go to the judge.
2. **Prefer reference-based where you can** ([04](04-pairwise-reference-and-summary-evaluators.md)). Build a seeded suite: take 50 merged PRs, inject one known bug each (drop a `defer cancel()`, remove jitter from backoff, swap commit and write order), and store the reference defect. For seeded PRs, the judge answers "same defect as the reference?" It is cheap to calibrate and has high TNR.
3. **Use reference-free for organic PRs**, with the `CODE_REVIEW_BUG` rubric ("Trace the code; do not take the comment's word for it").
4. **Calibrate on hard negatives.** `code/data/code_review_comments.jsonl` has the shapes to include: CR-006 (claims `ConcurrentHashMap.merge` is not atomic: false), CR-013 (Python int overflow: false), CR-014 (claims the closure captures the loop var, when the diff fixes that). These confident wrong claims are where a lenient judge fails.
5. **Use a judge from a different model family** than the reviewer bot, because self-preference would inflate exactly the metric you're reporting ([05](05-judge-biases.md)).

**What to check.**
- Judge TNR on the hard-negative slice specifically, not just overall.
- CR-009-style items, where the comment relies on context the judge can't see ("our Postgres 10 primary"). Decide explicitly whether the judge gets deployment context as an input.
- Whether any defect class is caught more reliably by a linter (`go vet` lostcancel for CR-018). If so, take it out of the judge's scope.

---

## 3. A/B testing a summary prompt with a pairwise judge

**Situation.** A teammate rewrote the summary prompt and says it is "clearly better". You want evidence before you merge.

**Naive approach.** Ask a judge, "Which is better, the current summary or the new summary?", with the current one always first and labelled. The new prompt wins 78% of the time. You merge. Two weeks later, the pointwise impact judge's corrected pass rate hasn't moved.

**AI-native approach.**
1. Use `pairwise.compare`: blinded ("Response 1/2"), both orders, flips counted as ties, and a one-sentence criterion: *Which summary states the customer impact more correctly and completely, given the facts?*
2. Use a judge model different from the generator ([Anthropic: "it should not be the model you are testing"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)).
3. Report all of these together:
   ```text
   pairs=120  B wins=41  A wins=33  ties=46  position-inconsistent=39
   B win rate (ties=0.5): 0.53   sign test p=0.42
   ```
   *(illustrative output)*
4. Read it. A 33% position-inconsistency rate means the judge mostly can't separate the two prompts on this criterion. The earlier 78% came from position and label bias. There is no evidence that B is better.

**What to check.**
- Two judge calls per pair in the trace.
- No "baseline", "current", "new" or model names in any judge prompt (`test_compare_runs_both_orders_blind`).
- Pointwise and pairwise agree in direction. If pairwise says B wins but the pointwise corrected pass rate is flat, investigate before merging.

---

## 4. The judge model upgrade drill

**Situation.** A new model snapshot is out. Platform wants every LLM call, judges included, on it by Friday.

**Naive approach.** Change the model string everywhere. Eval dashboards jump 5 points. Everyone celebrates the generator upgrade, without noticing the judges were upgraded at the same moment.

**AI-native approach.**
1. **Never upgrade the generator and the judge together.** Upgrade the generator first and keep the judge pinned. Its fingerprint, and therefore its calibration, still holds for the old distribution.
2. Label 50 fresh outputs from the *new generator* through the annotation queue's random slice. Run `drift_alarms(baseline, recent)`. If it's clean, the old judge's verdicts on the new generator can be trusted.
3. Then, separately, upgrade the judge: new fingerprint, run dev, then a new test read on the existing labels. Compare TPR/TNR with the old judge on the *same* test items, using a paired comparison.
4. Run the bias probes (`bias_probes.py`) against the new judge before it gates anything.

**What to check.**
- Every eval result row carries `judge_fingerprint`, and CI refuses fingerprints with no calibration record.
- The headline eval change is attributed: how much came from the generator (old judge, new outputs) and how much from the judge (new judge, same outputs).

---

## 5. "How would you eval that judge?" A diff-vs-prompt judge on a migration agent

**Situation.** You run a background agent that does dependency bumps across 300 services, modelled on Spotify's setup. Deterministic verifiers (build, tests) run in a Stop hook. An LLM judge then checks the diff against the task to catch overreach: unrelated refactors, disabled tests. Spotify reports that its judge vetoes about a quarter of sessions, that the agent course-corrects about half the time, and that it has "yet to invest in evals for our judge" ([Spotify, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). You're in the same position.

**Naive approach.** Trust the veto rate as a quality signal. When it drops from 25% to 12% after a prompt tweak, conclude that the agent got better.

**AI-native approach.**
1. **Name the single failure mode:** "the diff contains changes outside the task's scope". Write claims: every changed file is a manifest, a lockfile, or a file whose compile error the bump caused; no test is deleted or skipped; no unrelated renames.
2. **Move what you can to code.** "No test deleted or `@Disabled` added" is a diff grep. Do it in the Stop hook. The judge keeps only "is this source edit a necessary consequence of the bump?"
3. **Label 150 sessions:** all of last month's vetoes, plus an equal-sized random sample of the passes. Without the passes you can't measure TNR.
4. **Calibrate, then correct the veto rate.** The veto rate is 1 − p_obs. The corrected overreach rate tells you whether the 25% → 12% change was the agent improving or the judge getting more lenient.
5. **Probe for verbosity bias.** Agents that explain their changes at length in the PR description may get waved through. Run the padding probe with the PR description as the padded field.

**What to check.**
- The judge never sees the agent's own justification as evidence. It reads the diff and the task, and the description is out of scope.
- Drift alarms run on a weekly random sample of passes as well as vetoes.
- Session-level labels are clustered by repository. Bootstrap by repository when you report CIs ([03](03-calibration.md)).
