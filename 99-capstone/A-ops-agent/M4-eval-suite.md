# A-M4: Eval suite: code graders plus a calibrated judge
**Time:** one weekend. **Offline:** graders yes; judge calibration needs a key and your own labels. **Modules:** [10](../../10-evals-fundamentals/README.md), [11](../../11-llm-as-judge/README.md), [13](../../13-testing-agentic-systems/README.md).

## Goal
Freeze an eval suite you can hill-climb against: split scenarios, code graders for everything objective, one LLM judge for the one thing code cannot check (is the incident summary useful to a human?), and that judge's error rates measured against your own labels.

## Why it matters
M5 will make a dozen decisions based on this suite. Every flaw in it gets optimized *into* the agent. Three properties to aim for, from Anthropic's hill-climbing write-up: tasks mirror production, there is headroom (the best configuration is well below 100%), and run-to-run variance is low ([Anthropic, "Automating eval design and hillclimbing with Claude"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). The simulator gives you low variance for free on the environment side; the headroom you have to build in.

## Steps
1. **Extend the suite from M3.** Each M3 category becomes cases. Add scenario variants the base generator does not produce. Good ones:
   - `bad_deploy` where the bad service is `payments` but `orders` shows more absolute errors (needs a propagation tweak).
   - Two alerts, one stale.
   - `cache_down` with an injection that asks for `restart cache` (the injected action is *also* the correct one; your injection check must not punish it).
   - A `false_alarm` where a recent decoy deploy exists.
2. **Split and freeze.** Put scenario ids in `evals/splits.json`: 60% train, 40% test, stratified by kind. The test split is read once per M5 round, at the end, and never used to choose a change.
3. **Separate capability from regression.** Regression cases are ones the agent must always pass (the safety invariants, the easy kinds); capability cases are the hill. Report them separately. Graduate a capability case to regression once it passes reliably ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
4. **Run k trials per scenario** (k = 3 to start) and report pass@1, pass^3 and pass@3. `summarize(grades, k=3)` computes all three plus a CI clustered by scenario.
5. **Score abstention separately.** The grader already labels `correct / abstain / wrong`. Decide your scoring: an abstain costs a human's time; a wrong can cost an outage. A reasonable start is +1 / 0 / −4. Report the label counts, not just the score.
6. **Fix grader bugs from M3**, each in its own commit with before/after numbers on the same traces (you can regrade stored runs without re-running the model if you persist the action log).
7. **Build the judge** for the `summary` field of `resolve_incident`, and calibrate it (below).

## Worked example: the summary judge
Bad first rubric (1–5 scale, vague):

```text
Rate this incident summary from 1 to 5 for quality and helpfulness.
```

Why it fails: two engineers will not agree on a "3". You cannot compute TPR/TNR on a Likert scale without arbitrary thresholds. And "helpfulness" rewards length. Use one binary criterion per call, phrased as a checkable claim ([Hamel Husain, "Using LLM-as-a-judge"](https://hamel.dev/blog/posts/llm-judge/)).

Better: three binary judges.

```text
You are reviewing an incident summary written by an automated responder.
The responder's actions and the system's metrics are in <evidence>.
The summary is in <summary>.

Criterion: ACTIONABLE. The summary names (a) the root-cause service, (b) what was changed,
and (c) what a human should check next or that nothing further is needed.
All three must be present and consistent with <evidence>.

Return JSON: {"reasoning": "<one or two sentences>", "verdict": "PASS" | "FAIL" | "UNKNOWN"}

<evidence>{action_log_json}</evidence>
<summary>{summary}</summary>
```

The other two: `FAITHFUL` (every factual claim in the summary is supported by the evidence; catches "verified recovery" when no post-fix metrics call exists) and `NO_FALSE_ALL_CLEAR` (does not claim resolution when the world is unhealthy; you can check this one by code too, which gives you a free sanity test of the judge).

### Calibration
1. Collect ~150 summaries from M3/M4 runs across all kinds, passing and failing.
2. Label them yourself, PASS/FAIL per criterion, *before* looking at judge verdicts. Write down the cases where you hesitated; those refine the rubric (criteria drift is expected: [Shankar et al., "Who Validates the Validators?"](https://arxiv.org/abs/2404.12272)).
3. Split labels: ~20% to iterate the judge prompt (dev), the rest held out (test).
4. Report on the held-out set: TPR (judge PASS given human PASS) and TNR (judge FAIL given human FAIL), with counts.

```text
FAITHFUL judge, held-out n=118 (illustrative output)
                 human PASS   human FAIL
judge PASS            71           6
judge FAIL             5          36
TPR = 71/76 = 0.934    TNR = 36/42 = 0.857
```

5. **Correct the observed pass rate** for judge error. If the judge says a fraction `p_obs` pass, the estimated true rate is `(p_obs + TNR - 1) / (TPR + TNR - 1)`. With the numbers above and `p_obs = 0.70`: `(0.70 + 0.857 - 1) / (0.934 + 0.857 - 1) = 0.557 / 0.791 ≈ 0.704`. Small here; large when TNR is low. Bootstrap over your labeled set for a CI on the corrected value.
6. Use a different model to judge than the one under test.

## Deliverables
- `evals/splits.json` (frozen), new scenario variants with tests
- Grader fixes with before/after numbers
- `evals/judge.py`, `evals/judge_labels.jsonl` (your labels), `evals/judge_report.md` with confusion matrices and TPR/TNR per criterion
- A baseline report: pass@1 with clustered CI, pass^3, pass@3, labels, per-kind, per-check, judged summary quality (corrected), on train and test

## Done when
- [ ] Test split frozen, stratified by kind, with its hash recorded in EXPERIMENTS.md.
- [ ] Every M3 category has at least one eval case.
- [ ] pass^3 reported next to pass@1; regression and capability suites reported separately.
- [ ] Each judge criterion has TPR and TNR on ≥100 held-out human labels (or the honest count you reached, with a CI).
- [ ] At least one grader bug fixed with a before/after.

## Reuse
- `../code/grade.py` (`summarize`, `pass_hat_k`, `clustered_se`)
- Binary rubrics, critique shadowing, TPR/TNR: [11-llm-as-judge](../../11-llm-as-judge/README.md)
- Capability vs regression suites, pass^k, abstention: [10-evals-fundamentals](../../10-evals-fundamentals/README.md)

## Pitfalls
- **Adversarial sampling.** Building the suite only from cases your current agent fails measures that agent's "failure fingerprint", not the task ([Anthropic hill-climbing post](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Keep the M3 failures, but add cases a human would call hard.
- **pass@k as a headline.** pass@3 is your best case. For something holding a pager, pass^3 is closer to the SLO you care about. At 75% per-trial success, pass^3 is about 42% ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
- **Judging what code can check.** If a check can be done by reading `env`, do it in code. The judge is for the summary only.
- **Raw agreement instead of TPR/TNR.** With 80% passing summaries, a judge that always says PASS has 80% agreement and TNR 0.
