# 10: Evals fundamentals
> After this module you can take an LLM feature or an agent from "it seems fine" to a versioned eval suite: traces you can read, a failure taxonomy built from those traces, a dataset with slices and negative controls, code graders, and metrics (pass@k, pass^k, abstention-aware score) you can put in a release gate.

## Why this matters
Without evals, every prompt edit, model upgrade and tool change is a deploy with no tests and no monitoring. You find out about regressions from users, or from the on-call engineer who got paged by the wrong rotation. Teams in that position stall: they keep changing the system and have no way to tell whether a change helped. Hamel Husain's diagnosis is blunt: most failed LLM products fail because they have no robust evaluation system ([Hamel Husain, "Your AI Product Needs Evals"](https://hamel.dev/blog/posts/evals/)).

The course thesis is that **autonomy should scale with verifiability**. This module is where verifiability is built. Every later module consumes what you make here: the judge in [Module 11](../11-llm-as-judge/README.md) is calibrated against labels you collect here, the hill-climbing loop in [Module 12](../12-hill-climbing/README.md) climbs the metric you define here, and the CI gates and online evals in [Module 15](../15-observability-and-production/README.md) run the graders you write here.

The failure modes are concrete. One is a router that gets a given alert right on 75% of runs, and so gets it right on all three of three repeated runs only 42% of the time (0.75³ ≈ 0.42, the example in [Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). Another is a model that "improves" accuracy by guessing more and doubles its confident errors. A third is an agent that makes the visible tests pass by editing them. A fourth is a benchmark score that rose because the answers leaked into training data. Each of these is invisible without the right eval, and each has a specific fix that this module teaches.

## The distributed-systems anchor
**An eval suite is the test pyramid and the SLIs for a component whose behavior you cannot read from its source.**

| You know | In evals |
|---|---|
| Unit tests derived from a spec | Code graders derived from a failure taxonomy (the spec is discovered, not given) |
| Distributed tracing (spans, trace IDs) | The trace data model: one trace per trial, spans for model calls and tool calls, the prompt hash on every span |
| Postmortems and incident categories | Error analysis: open coding, then axial coding into failure modes |
| SLI = good events / valid events, per endpoint | Pass rate per slice; abstention-aware score that prices wrong answers |
| Availability across N requests | pass^k: the probability that *all* k trials succeed |
| "Works with retries" | pass@k: the probability that *at least one* of k trials succeeds |
| Golden files and regression suites | Golden sets, split into dev and test, with negative controls |
| Test pollution between runs | Eval contamination: shared state between trials, leaked answer keys |

**Where the analogy breaks.**
- There is no spec to derive tests from. You find out what "good" means by reading outputs, and reading outputs changes what you think "good" means. Shreya Shankar calls this *criteria drift* ([Shankar et al., EvalGen](https://arxiv.org/abs/2404.12272)).
- The input space is unbounded natural language, so coverage is a sampling question, not an enumeration.
- Nondeterminism is part of the system, not a flake you can quarantine. A test that passes 4 times in 5 is the measurement, not a bug in the test.
- The system under test may notice it is being tested, and may go looking for the answer key ([Anthropic, "Eval awareness in Claude Opus 4.6's BrowseComp performance"](https://www.anthropic.com/engineering/eval-awareness-browsecomp)).

## Learning goals
- [ ] Explain the difference between a unit test and an eval, and write the "definition of good" for a feature as a set of binary checks.
- [ ] Instrument a system so that every trial produces a trace with the input, output, prompt hash, model calls, tool calls and agent state.
- [ ] Run error analysis on about 100 traces: open-code them, axial-code them into 5 to 8 failure modes, count them, and decide when you have reached saturation.
- [ ] Build a transition failure matrix for an agent and use it to pick the first fix.
- [ ] Build a dataset from real failures plus dimension-tuple synthetic data, with slices, negative controls and a frozen test split.
- [ ] Write code graders for structure, exact match, ordinal partial credit, forbidden content, state and outcomes, and know when you need a judge instead.
- [ ] Report pass@k and pass^k from n trials with unbiased estimators, and explain which one your users experience.
- [ ] Score correct, abstain and wrong separately, with an explicit penalty for wrong answers.
- [ ] Audit an eval for contamination, shared state between trials, answer-key leakage and scaffold effects, and read a public benchmark claim critically.

## Reading order
1. [01-why-evals-and-when-to-write-them.md](01-why-evals-and-when-to-write-them.md): unit tests vs evals, the eval as the spec of "good", and the course stance on eval-driven development.
2. [02-instrument-first.md](02-instrument-first.md): the trace data model you need before error analysis is possible.
3. [03-error-analysis.md](03-error-analysis.md): reading traces, open and axial coding, the transition failure matrix, the benevolent dictator.
4. [04-datasets.md](04-datasets.md): golden sets, synthetic data from dimension tuples, negative controls, splits.
5. [05-graders.md](05-graders.md): code graders first, then judges and humans; grading outcomes vs transcripts.
6. [06-metrics.md](06-metrics.md): pass@k vs pass^k, abstention-aware scoring, per-slice metrics.
7. [07-eval-integrity-and-benchmarks.md](07-eval-integrity-and-benchmarks.md): contamination, eval awareness, leakage, scaffolds, the retirement of SWE-bench Verified, and why your evals should be private.
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

**Running example.** An *incident ticket router* reads one production alert and returns `{decision, team, severity, rationale}` as JSON (single-turn). A small *coding agent* fixes a token-bucket rate limiter with `read_file`, `write_file` and `run_tests` tools (agentic). The code ships with a deliberately flawed fake router and three fake agent trajectories, so you can watch every grader and metric catch something real without an API key.

## Prerequisites
- [Module 01](../01-llms-for-systems-engineers/README.md): sampling, nondeterminism, why models hallucinate.
- [Module 02](../02-prompting-as-specification/README.md): prompts as versioned specs (the prompt hash in this module is how you tell versions apart).
- [Module 07](../07-loops/README.md) is helpful but not required: the coding agent here uses the plain tool loop built there.

## Key takeaways
- An eval is the executable definition of "good" for a behavior you cannot derive from source. Write it as binary checks, not a 1 to 5 score.
- Instrument before you analyze: one trace per trial, with the input, output, prompt hash, model calls, tool calls and agent state. If you cannot read a trace in one screen, fix the viewer first.
- Read about 100 traces yourself before you write a grader. Open-code the first failure in each, group the notes into 5 to 8 binary failure modes, count them, and stop when new traces stop adding modes.
- Start a dataset with 20 to 50 tasks from real failures. Fill gaps with dimension-tuple synthetic inputs, label them yourself, and include negative controls that check what the system should *not* do.
- Use the cheapest grader that is valid: schema, exact match, regex, unit tests and state checks first. Use a judge only where interpretation is unavoidable. Grade the outcome, not the path.
- Report pass^k next to pass@k. Your users experience pass^k; your demo shows pass@k.
- Score correct, abstain and wrong separately, and make wrong cost more than abstaining. Accuracy alone rewards guessing.
- Keep your evals private, isolate every trial, and treat eval integrity as an ongoing adversarial problem. Public benchmark gaps of a few points tell you little about your workload.
