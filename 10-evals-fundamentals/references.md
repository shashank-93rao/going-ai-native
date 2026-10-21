# References

Grouped by concept. "Take" says what to get from each source. Items marked *as reported* could not be read directly when this module was written (October 2026).

## Core: process and vocabulary
- **Anthropic, "Demystifying evals for AI agents"** (2026-01-09). https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  Take: the vocabulary (task, trial, grader, transcript, outcome, eval harness vs agent harness); code, model and human graders; pass@k vs pass^k with the 75% → 42% example; "20-50 simple tasks drawn from real failures"; balanced should/shouldn't sets; capability vs regression suites; "grade what the agent produced, not the path"; the CORE-Bench 42% → 95% grader-and-scaffold story; git history leaking between trials; 0% pass@100 usually means a broken task.
- **Hamel Husain and Shreya Shankar, "AI Evals FAQ"**. https://hamel.dev/blog/posts/evals-faq/
  Take: annotate at least 30 traces yourself and about 100 overall, stop at saturation; open coding of the first failure, then axial coding ("the most important step"); the benevolent dictator; dimension tuples with a separate tuple-to-query step; "generally no" to writing evals first, except known constraints; binary over Likert; the two-phase agent eval; the transition failure matrix (GenSQL → ExecSQL 12 vs DecideTool → PlanCal 2); CI sets of 100+ examples with deterministic checks.
- **Hamel Husain and Shreya Shankar, "AI Evals for Engineers & PMs" (Maven course syllabus)**. https://maven.com/parlance-labs/evals
  Take: lecture 2, designing for evaluability with a trace data model (nested spans, model and tool calls, permission denials, prompt hashes); lecture 3, synthetic scenarios; lecture 4, open and axial coding into 5 to 8 binary modes over 60+ traces; freeze-and-read-test-once; pass^k for reliability vs pass@k for capability.
- **Hamel Husain, "Your AI Product Needs Evals"** (2024-03-29). https://hamel.dev/blog/posts/evals/
  Take: why teams without evals stall; three levels of evals; "Remove ALL friction from looking at data."
- **Hamel Husain, "A Field Guide to Rapidly Improving AI Products"** (2025-03-24). https://hamel.dev/blog/posts/field-guide/
  Take: bottom-up error analysis vs generic metrics; the reported date-handling case (33% → 95%); a spreadsheet is a fine first trace viewer; verify that synthetic scenarios trigger.
- **Hamel Husain, "Using LLM-as-a-Judge For Evaluation"**. https://hamel.dev/blog/posts/llm-judge/
  Take: synthesize inputs only, never responses; the principal domain expert. (Main use is in [Module 11](../11-llm-as-judge/README.md).)
- **Shreya Shankar et al., "Who Validates the Validators?" (EvalGen, UIST 2024)**. https://arxiv.org/abs/2404.12272
  Take: criteria drift, "users need criteria to grade outputs, but grading outputs helps users define criteria".

## The EDD debate
- **Eugene Yan, "An LLM-as-Judge Won't Save The Product—Fixing Your Process Will"** (2025-04-20). https://eugeneyan.com/writing/eval-process/
  Take: the case for eval-driven development, "First, write some evals; then, build systems that pass those evals."
- **OpenAI, "Evaluation best practices"** (living doc). https://developers.openai.com/api/docs/guides/evaluation-best-practices
  Take: "Adopt eval-driven development"; what to evaluate per architecture (single-turn, workflow, agent, multi-agent); anti-patterns including synthetic data that doesn't match production.
- Course stance: [research/01-gap-analysis.md](../research/01-gap-analysis.md), "Eval-driven development first vs evals for observed failures".

## Datasets and graders
- **Lance Martin, "Automating eval design and hillclimbing with Claude"** (claude.dev blog, 2026). https://claude.dev/blog/automating-eval-design-and-hillclimbing/
  Take: example sources in priority order; the adversarial-sampling trap; "A good task is one where two domain experts would reach the same verdict and everything the grader checks is stated in the task"; cheapest grader that fits; never paste failure content into the prompt; the claude-api skill eval whose last gain came from fixing graders.
- **Anthropic docs, "Define success criteria" and "Create strong empirical evaluations"**. https://platform.claude.com/docs/en/test-and-evaluate/define-success, https://platform.claude.com/docs/en/test-and-evaluate/develop-tests
  Take: measurable, multi-dimensional criteria; "prioritize volume over quality" for cheap single-turn tasks.
- **OpenAI, "Graders"** (API guide). https://developers.openai.com/api/docs/guides/graders
  Take: the grader ladder (string check, Python, model grader); brittle string checks such as `1` vs `1.0`; grader hacking.
- **OpenAI, "Testing Agent Skills Systematically with Evals"** (2026). https://developers.openai.com/blog/eval-skills
  Take: small prompt sets with negative controls; deterministic checks on JSONL traces; process and efficiency checks; "Let real failures drive coverage."
- **OpenAI Cookbook, "Eval Driven System Design: From Prototype to Production"** (2025, archived). https://developers.openai.com/cookbook/examples/partners/eval_driven_system_design/receipt_inspection
  Take: a cost model that weights eval errors by business impact.
- **Anthropic, "From shortcuts to sabotage: natural emergent misalignment from reward hacking"** (2025-11-21). https://www.anthropic.com/research/emergent-misalignment-reward-hacking
  Take: why graders must be hack-resistant (`sys.exit(0)` to fake passing tests).

## Metrics
- **Yao et al., "τ-bench"** (2024). https://arxiv.org/abs/2406.12045 and **Barres et al., "τ²-bench"** (2025). https://arxiv.org/abs/2506.07982
  Take: pass^k as a reliability metric; grading by final database state; gpt-4o under 50% task success in retail, with pass^8 under 25%.
- **Anthropic, "The think tool"** (2025-03-20, updated 2025-12). https://www.anthropic.com/engineering/claude-think-tool
  Take: τ-bench airline pass^1 0.584 vs 0.332 baseline, pass^5 0.340 vs 0.100, as an example of reporting both. (The post's update recommends extended thinking over the think tool in most cases.)
- **Chen et al., "Evaluating Large Language Models Trained on Code"** (2021). https://arxiv.org/abs/2107.03374
  Take: the unbiased pass@k estimator.
- **Kalai, Nachum, Vempala and Zhang, "Why Language Models Hallucinate"** (2025). https://arxiv.org/abs/2509.04664, and **OpenAI's post**: https://openai.com/index/why-language-models-hallucinate/
  Take: evaluation that rewards guessing; explicit confidence targets, "Answer only if you are >t confident, since mistakes are penalized t/(1-t) points". The SimpleQA table (gpt-5-thinking-mini 52% abstain / 22% accurate / 26% wrong vs o4-mini 1% / 24% / 75%) is *as reported* in OpenAI's post, which returned 403 when fetched.
- **Eugene Yan, "Product Evals in Three Simple Steps"** (2025-11-23). https://eugeneyan.com/writing/product-evals/
  Take: the worked confidence-interval example for small defect rates.
- **Anthropic, "A statistical approach to model evaluations"** (2024-11-19). https://www.anthropic.com/research/statistical-approach-to-model-evals
  Take: error bars, clustered standard errors, paired tests. Used in depth in [Module 12](../12-hill-climbing/README.md).

## Integrity and benchmark literacy
- **Anthropic, "Eval awareness in Claude Opus 4.6's BrowseComp performance"** (2026-03-06). https://www.anthropic.com/engineering/eval-awareness-browsecomp
  Take: 2 of 1,266 problems solved by finding and decrypting the answer key; 9 contamination cases; 3.7x higher rate in multi-agent setups; blocking search results naming the benchmark worked where URL blocklists didn't.
- **Anthropic, "Quantifying infrastructure noise in agentic coding evals"** (2026-02-05). https://www.anthropic.com/engineering/infrastructure-noise
  Take: 6-point swings on Terminal-Bench 2.0 from infrastructure alone; distrust gaps under about 3 points without matched configurations; specify allocation and kill thresholds.
- **Anthropic, "Investigating unintended model actions in evaluations and internal use"** (2026-10-09). https://www.anthropic.com/research/investigating-unintended-model-actions
  Take: real-world side effects during evals; live internet access turned off for all internal evals.
- **Anthropic, "Raising the bar on SWE-bench Verified with Claude 3.5 Sonnet"** (2025-01-06). https://www.anthropic.com/engineering/swe-bench-sonnet
  Take: scaffold effects (a minimal scaffold at 49% vs a prior 45% state of the art); hidden tests mean the model can believe it succeeded when it hasn't.
- **Jimenez et al., "SWE-bench"** (ICLR 2024). https://arxiv.org/abs/2310.06770
  Take: the benchmark's design (2,294 issues, 12 repos, hidden tests) and starting point ("a mere 1.96% of the issues").
- **OpenAI, "Why we no longer evaluate SWE-bench Verified"** (2026-02-23). https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
  Take, *as reported* (the page returned 403): flawed tests in an audited subset (59.4% reported), contamination, saturation, and a recommendation to use SWE-bench Pro. Do not quote figures from this module as if read from the post.

## Related modules
- [Module 11](../11-llm-as-judge/README.md): model-based graders, calibration against human labels.
- [Module 12](../12-hill-climbing/README.md): error bars, paired tests, train/test discipline, noise checks.
- [Module 13](../13-testing-agentic-systems/README.md): trajectory evals, simulated users, record and replay.
- [Module 15](../15-observability-and-production/README.md): production tracing, online evals, CI gates.
