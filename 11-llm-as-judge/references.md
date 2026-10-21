# References

Grouped by use. "Take" means what this module uses from each source.

## Core method

- **Hamel Husain, "Using LLM-as-a-Judge For Evaluation: A Complete Guide"**: <https://hamel.dev/blog/posts/llm-judge/> (2024-10-29, updated 2026).
  Take: binary pass/fail with a written critique; one principal domain expert; validate the judge with TPR/TNR, not agreement (the 95%-agreement always-pass example); about 100 labels per failure mode, and CIs often too wide below about 60; train 10-20% / dev 40-45% / test 40-45%, with test read once; re-run the process when the model changes.
- **Hamel Husain and Shreya Shankar, "AI Evals: Everything You Need to Know" (Evals FAQ)**: <https://hamel.dev/blog/posts/evals-faq/>.
  Take: prefer binary checks over Likert, and use several binary checks to track gradual progress; 100-200 labeled examples per failure mode for a judge; generic metrics (ROUGE, BERTScore, cosine) as exploration signals at most; production alerting on CI lower bounds.
- **Hamel Husain, `validate-evaluator` skill (evals-skills)**: <https://tessl.io/registry/skills/github/hamelsmu/evals-skills/validate-evaluator>.
  Take: the Rogan-Gladen formula as applied to judges, and the worked example (TPR 0.92, TNR 0.88, 80% raw → 85% corrected).
- **Rogan, W. J. and Gladen, B., "Estimating prevalence from the results of a screening test"**, *Am J Epidemiol* 107(1):71-76, 1978: <https://pubmed.ncbi.nlm.nih.gov/623091/>.
  Take: the origin of the correction. The observed positive rate of an imperfect test is a biased prevalence estimate, and sensitivity and specificity correct it.
- **`judgy` (AI Evals course)**: <https://pypi.org/project/judgy/>.
  Take: a small library that does the same Rogan-Gladen-plus-bootstrap estimate as `calibrate.py`. It assumes TPR + TNR > 1. Its API was not checked for this module; read its README before using it.

## Who validates the validators

- **Shreya Shankar et al., "Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences"** (UIST 2024): <https://arxiv.org/abs/2404.12272>.
  Take: criteria drift ("users need criteria to grade outputs, but grading outputs helps users define criteria"); LLM-generated evaluators inherit LLM flaws; the EvalGen loop, where an LLM proposes evaluators, a human grades a sample, and the evaluators that agree with the human are kept.
- **Spotify Engineering, "Background coding agents" part 3 (feedback loops)**: <https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3>.
  Take: a production diff-vs-prompt judge that vetoes about a quarter of sessions, with about half recovering, and the authors' note that they have "yet to invest in evals for our judge". Used here as the motivating case for examples.md #5.

## Biases

- **Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"** (2023): <https://arxiv.org/abs/2306.05685>.
  Take: position, verbosity and self-enhancement bias, plus limited reasoning, as the named limitations; strong judges reaching over 80% agreement with humans, about the human-human level.
- **Panickssery, Bowman and Feng, "LLM Evaluators Recognize and Favor Their Own Generations"** (2024): <https://arxiv.org/abs/2404.13076>.
  Take: evaluators score their own outputs higher than humans would; self-recognition ability correlates linearly with self-preference.
- **Eugene Yan, "Evaluating the Effectiveness of LLM-Evaluators (aka LLM-as-Judge)"**: <https://eugeneyan.com/writing/llm-evaluators/>.
  Take: direct scoring for objective criteria, pairwise for subjective ones; Cohen's kappa; the bias catalogue; swapping order; panel-of-judges (PoLL) as a reported cost/quality option.
- **Eugene Yan, "Product Evals in Three Simple Steps"**: <https://eugeneyan.com/writing/product-evals/>.
  Take: one evaluator per criterion; collect 50-100 fail cases within 200+ samples from organic failures; record a tie when the pairwise verdict flips under a swap; kappa 0.4-0.6 substantial and above 0.7 excellent; human annotators often only 0.2-0.3 kappa and fatigue-prone.

## Anthropic

- **"Automating eval design and hillclimbing with Claude"**: <https://claude.dev/blog/automating-eval-design-and-hillclimbing/> (page dated 2026-09-28; blog listing shows 2026-10-07).
  Take: judge rubrics "written as checkable claims (not a 1-to-5 scale)"; blind pairwise in random order "without being told which is the baseline"; the judge "should not be the model you are testing"; run the grader twice and report whether the verdict changed; "two domain experts would reach the same verdict".
- **"Demystifying evals for AI agents"**: <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents> (2026-01-09).
  Take: code / model / human grader types; one judge per dimension; give the judge an "Unknown" option; grade outcomes rather than paths; read the transcripts.
- **Docs: "Create strong empirical evaluations"**: <https://platform.claude.com/docs/en/test-and-evaluate/develop-tests>.
  Take: the Likert tone-grader prompt, used here as the "before" example; use a different model to grade than to generate.
- **"Harness design for long-running application development"**: <https://www.anthropic.com/engineering/harness-design-long-running-apps> (2026-03-24).
  Take: "agents reliably skew positive when grading their own work"; split generator from evaluator; the evaluator prompt started lenient and was tuned by reading its logs.
- **"Building agents with the Claude Agent SDK"**: <https://claude.com/blog/building-agents-with-the-claude-agent-sdk> (2025-09-29).
  Take: use LLM-as-judge only when the gain justifies it, because it is not very robust and adds latency.
- **"A statistical approach to model evaluations"**: <https://www.anthropic.com/research/statistical-approach-to-model-evals> (2024-11-19).
  Take: clustered standard errors (more than 3x naive on popular evals), relevant to the six-summaries-per-incident structure of this module's data. Covered in depth in [Module 12](../12-hill-climbing/README.md).

## OpenAI

- **Evaluation best practices**: <https://developers.openai.com/api/docs/guides/evaluation-best-practices>.
  Take: for judges, watch position and verbosity bias, prefer pairwise or pass/fail, and validate against human labels.
- **Graders guide**: <https://developers.openai.com/api/docs/guides/graders>.
  Take: the grader ladder (string check, Python, score model, human); grader hacking, where the model-grader score is high and the expert score low, as the drift and gaming alarm.

## Tooling

- **LangSmith annotation queues**: <https://docs.langchain.com/langsmith/annotation-queues>.
  Take: single-run and pairwise queues; reviewers judge runs against a rubric.
- **LangChain, "Pairwise Evaluations with LangSmith"**: <https://blog.langchain.dev/pairwise-evaluations-with-langsmith>.
  Take: why pairwise helps when pointwise scores tie at the top; `evaluate_comparative`.
- **LangSmith, "How to define a summary evaluator"**: <https://docs.smith.langchain.com/evaluation/how_to_guides/summary>.
  Take: experiment-level metrics computed from lists of inputs/outputs/reference outputs, returned as `{key, score}`. Parameter details were not re-checked against the latest SDK; the summary evaluator in [04](04-pairwise-reference-and-summary-evaluators.md) is a sketch of the shape.
- **Hamel Husain, "A Field Guide to Rapidly Improving AI Products"**: <https://hamel.dev/blog/posts/field-guide/>.
  Take: build a low-friction data viewer for labelling (full context, one-click labels, notes), and start with a spreadsheet.
- **Andrej Karpathy on the Dwarkesh Podcast** (2025-10-17): <https://www.dwarkesh.com/p/andrej-karpathy>.
  Take: LLM judges used as rewards get gamed by adversarial examples, which is why the rubric is kept out of the generator's loop.
