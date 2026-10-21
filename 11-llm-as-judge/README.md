# 11: LLM-as-judge
> After this module you can build a binary LLM judge for one failure mode, measure it against human labels with TPR/TNR, report a corrected pass rate with an honest confidence interval, and notice when the judge stops being trustworthy.

## Why this matters

[Module 10](../10-evals-fundamentals/README.md) left you with a failure taxonomy from error analysis and a rule: use a code check wherever one works. Some failure modes have no code check. "Did the incident summary state the customer impact correctly?" depends on reading two documents and comparing claims: that 3,412 merchants had *delayed* webhooks, not *lost* ones, and only in us-east-1. "Did this review comment find a real bug?" means tracing the diff. For these you use a model as the grader. Everything downstream depends on that grader: the CI gate, the hill-climbing loop in [Module 12](../12-hill-climbing/README.md), the production dashboard in [Module 15](../15-observability-and-production/README.md).

An unvalidated judge fails quietly. It never throws an exception. It returns a number, the number goes on a dashboard, and people make decisions with it. In this module's own data, a 1-5 "quality and accuracy" judge gives 11 of 25 wrong incident summaries the top score of 5, which is more than it gives to correct ones (`code/compare_judges.py`, run offline). A judge that always says PASS reaches 95% agreement on a dataset with a 5% failure rate and catches none of the failures ([Hamel Husain, "Using LLM-as-a-Judge"](https://hamel.dev/blog/posts/llm-judge/)). Spotify's background coding agent uses an LLM judge that vetoes about a quarter of sessions, and the team says openly that it has no evals for that judge yet ([Spotify, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). That isn't a criticism of Spotify. It is the normal state of most teams, and it is the gap this module closes.

The course thesis is that autonomy should scale with verifiability. A judge is how you make a fuzzy property verifiable. It only counts as verification once you have measured the verifier.

## The distributed-systems anchor

**A judge is an alert rule, and calibrating it is validating your monitoring.** You would never trust a new alert just because its query looks right. You backtest it against known incidents, count the pages it would have missed (false negatives) and the ones it would have fired for nothing (false positives), and only then let it page anyone. A judge works the same way. Human labels are your incident ground truth. TPR and TNR are the alert's two error rates. A dev/test split is the difference between tuning the threshold on last month's incidents and checking it on this month's.

The **Rogan-Gladen correction** is the step most teams skip. It is like correcting a counter that you know drops a fixed fraction of events: if you know the sensor's error rates, you can recover the true rate from the observed one. Epidemiologists use it to estimate prevalence from an imperfect screening test ([Rogan & Gladen 1978](https://pubmed.ncbi.nlm.nih.gov/623091/)).

**Where the analogy breaks:**
- *The sensor is not stationary.* A Prometheus rule means the same thing tomorrow. A judge changes when the provider ships a new model version, when you edit one sentence of its prompt, and when the distribution of outputs it reads shifts. Calibration has a shelf life.
- *Errors correlate with the thing being measured.* A judge from the same model family as the generator can share its blind spots, and may prefer its own style ([Panickssery et al. 2024](https://arxiv.org/abs/2404.13076)). That is like monitoring a service with a probe that runs the same buggy client library.
- *The ground truth moves too.* Grading outputs changes what the humans think the criteria are ([Shankar et al., "Who Validates the Validators?"](https://arxiv.org/abs/2404.12272)). Your incident definitions never rewrote themselves because you looked at the incidents. Rubrics do.

## Learning goals
- [ ] Decide, for a given failure mode, whether a code check suffices or a judge is needed, and write that decision down
- [ ] Write a binary, single-failure-mode rubric as checkable claims, with critique-then-verdict structured output
- [ ] Explain with a confusion matrix why a Likert judge with an arbitrary threshold is worse than a binary judge
- [ ] Split 100-200 human labels into train/dev/test, iterate on dev only, and read test once
- [ ] Report TPR and TNR with confidence intervals, and correct an observed pass rate with Rogan-Gladen plus a bootstrap CI
- [ ] Run a position-swapped pairwise comparison and interpret ties and position flips
- [ ] Probe a judge for position, verbosity and run-to-run inconsistency, and say how you would measure self-preference
- [ ] Set up a labeling workflow (annotation queue) that keeps a judge calibrated as criteria and models drift

## Reading order
1. [01-when-you-need-a-judge](01-when-you-need-a-judge.md): the grader ladder; when code is enough; one failure mode per judge
2. [02-binary-rubrics-and-critiques](02-binary-rubrics-and-critiques.md): why binary beats Likert; rubrics as checkable claims; critique-then-verdict output
3. [03-calibration](03-calibration.md): TPR/TNR, the dev/test split, Rogan-Gladen correction with a bootstrap CI
4. [04-pairwise-reference-and-summary-evaluators](04-pairwise-reference-and-summary-evaluators.md): the other evaluator shapes and when each fits
5. [05-judge-biases](05-judge-biases.md): position, verbosity, self-preference, run-to-run noise; Anthropic's three mitigations
6. [06-who-validates-the-validators](06-who-validates-the-validators.md): criteria drift, annotation queues, drift monitoring and re-calibration on model change
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
- [Module 10: Evals fundamentals](../10-evals-fundamentals/README.md): error analysis, failure taxonomies, code graders. Your judge targets one failure mode from that taxonomy.
- [Module 02: Prompting as specification](../02-prompting-as-specification/README.md): a judge prompt is a spec and should be versioned like one.
- Helpful: [Module 14: Steering and guardrails](../14-steering-and-guardrails/README.md) for structured output and validators.

## Key takeaways
- Use a judge only where no code check works. Each judge covers exactly one failure mode, and its rubric is a list of claims a careful human could check.
- Use binary PASS/FAIL with a written critique, generated before the verdict. A 1-5 scale hides an uncalibrated threshold and makes the labels impossible to act on.
- Treat the judge as a binary classifier. Report TPR and TNR with confidence intervals on a held-out test set, never raw agreement. On most products TNR (catching bad outputs) is the number that matters.
- Label 100-200 examples per failure mode, with enough of each class. Put 10-20% in train (few-shot examples), 40-45% in dev (iterate here) and 40-45% in test (read once, at the end).
- An observed judge pass rate is biased. Correct it with Rogan-Gladen, `(p_obs + TNR - 1) / (TPR + TNR - 1)`, and bootstrap the CI over both the labels and the production sample.
- For comparisons, run pairwise both ways round, keep the judge blind to which output is the baseline, use a different model from the one under test, and count a flipped verdict as a tie.
- A judge has a shelf life. Re-calibrate when the judge model, the judge prompt, the generator, or the input distribution changes, and keep a stream of fresh human labels coming in through an annotation queue.
