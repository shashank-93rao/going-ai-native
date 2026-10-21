# Practitioner research: independent voices on AI-native engineering

Research date: 2026-10-19. Compiled for the "going-ai-native" course (experienced engineers with a distributed-systems background).

Verification conventions:
- **[verified]** means the page was fetched during research and the quote or number was read on it.
- **[secondary]** means the claim comes from a secondary write-up or search summary, and the primary page was not read.
- **[unverified]** means a URL or detail I could not confirm. Check it before teaching from it.
- Quotes are short and taken from fetched pages. Where a quote is marked [secondary], do not put it on a slide until it has been checked against the primary page.

Module numbers refer to `00-draft-topics.md`.

---

## A. Evals, error analysis, and LLM-as-judge

### 1. Hamel Husain, "Your AI Product Needs Evals"
- **URL:** https://hamel.dev/blog/posts/evals/
- **Date:** 2024-03-29
- **Key claims:**
  - Most failed LLM products fail because they lack a robust evaluation system. A vibe check does not tell you whether a product works.
  - Your speed of iteration depends on how fast you can evaluate quality, debug, and change the system. Teams that only change the system stall at demo quality.
  - Build evals for your specific product. Generic benchmarks and frameworks do not do this job.
  - The same eval infrastructure also serves debugging and fine-tuning data curation.
- **Practical techniques:**
  - Three levels of evals:
    - L1, unit-test assertions: cheap, run on every change.
    - L2, human and model eval over logged traces.
    - L3, A/B tests, used only for mature products.
  - Write scoped assertions per feature and scenario, plus generic checks such as "no UUIDs leaked into the output". Generate test inputs with an LLM.
  - Track the pass rate over time. A pass rate below 100% can be a product decision.
  - Build a custom trace viewer that removes friction from labeling.
  - Align an LLM critic to human labels. Use precision and recall rather than raw agreement when classes are imbalanced.
- **Quote:** "Remove ALL friction from looking at data." (Hamel Husain) [verified]
- **Maps to:** 07, 08, 09, 12

### 2. Hamel Husain, "Using LLM-as-a-Judge For Evaluation: A Complete Guide" (critique shadowing)
- **URL:** https://hamel.dev/blog/posts/llm-judge/
- **Date:** 2024-10-29 (page updated 2026-09-01)
- **Key claims:**
  - Uncalibrated 1-5 scales are noise. Binary pass/fail with a written critique is more actionable.
  - A single "principal domain expert" defines quality. Proxies and developers should not.
  - The main value comes from looking at data. The judge is a by-product.
  - Validate the judge as a binary classifier, using TPR and TNR rather than raw agreement.
- **Practical techniques:** the seven-step "critique shadowing" process.
  1. Find the principal domain expert.
  2. Build a dataset along features x scenarios x personas. Synthesize user inputs only, never the responses.
  3. The expert gives pass/fail plus a detailed critique for each example.
  4. Fix the obvious errors first.
  5. Build the judge with the critiques as few-shot examples. Split the data into train, dev, and test, and evaluate the frozen prompt only on test.
  6. Run error analysis.
  7. Add specialized judges only where data shows a need.
  - Re-run the process after model changes.
- **Quote:** "Treat the judge as a binary classifier." (Hamel Husain) [verified]
- **Maps to:** 08, 07

### 3. Hamel Husain, "A Field Guide to Rapidly Improving AI Products"
- **URL:** https://hamel.dev/blog/posts/field-guide/
- **Date:** 2025-03-24
- **Key claims:**
  - Teams obsess over tools and architecture before they measure anything.
  - Generic metrics create false progress.
  - Bottom-up error analysis finds domain-specific failures that top-down metrics miss.
  - Domain experts should be able to edit prompts directly.
  - Criteria cannot be fully specified before anyone has judged outputs.
  - Roadmaps should count experiments, not features.
- **Practical techniques:**
  - Error analysis loop: read logs, write open-ended notes, have an LLM cluster the notes into a failure taxonomy, then count frequencies. Case study: date-handling success went from 33% to 95%.
  - Custom data viewer: full context on one screen, one-click labels, free-text notes, filters, and hotkeys. Start with a spreadsheet.
  - Synthetic data along features, scenarios, and personas, grounded in real system data. Verify that each scenario actually triggers.
  - Judge/expert alignment: one team passed 90% agreement in 3 iterations.
  - "Capability funnel" and time-boxed experiment roadmaps.
- **Quote:** "The key metric for AI roadmaps isn't features shipped – it's experiments run." (Hamel Husain) [verified]
- **Maps to:** 07, 09, 14

### 4. Hamel Husain and Shreya Shankar, "AI Evals: Everything You Need to Know" (Evals FAQ)
- **URL:** https://hamel.dev/blog/posts/evals-faq/
- **Date:** published 2026-09-18 (consolidated; earlier versions circulated in 2025), modified 2026-09-21
- **Key claims:**
  - The authors spend 60-80% of development time on error analysis and evaluation, mostly reading data.
  - A 100% pass rate means the evals are too easy.
  - Prefer binary checks to Likert scales. Track gradual progress with several specific binary checks.
  - Eval-driven development ("write evals first") is generally **not** recommended. Write evaluators for failures you have observed. The exception is explicit constraints such as "never mention competitors".
  - Generic metrics (ROUGE, BERTScore, cosine similarity on outputs) create false confidence. Use them at most as exploration signals.
- **Practical techniques:**
  - Annotate at least 30 traces yourself before letting an agent suggest failures. Aim for about 100 diverse traces, and stop when new traces reveal no new failure modes (saturation).
  - A judge needs 100-200 labeled examples per failure mode, split into train, dev, and test.
  - **Agents:** evaluate in two phases.
    - Phase 1: black-box end-to-end success with a precise per-task success rule, recording the *first upstream failure*.
    - Phase 2: step-level diagnostics on tool choice, argument extraction, error handling, context retention, efficiency, and goal checkpoints. Check the tool name, arguments, result, and resulting state separately.
  - **Transition failure matrix:** rows are the last successful state, and columns are the state where the first failure occurred. It shows where failures cluster. In a text-to-SQL example, one transition caused 12 failures and another caused 2.
  - **CI vs production:**
    - CI uses a small curated set (100+ examples) of core features, past bugs, and edge cases, with deterministic checks preferred.
    - Production samples live traces, runs reference-free evaluators asynchronously, and alerts when a confidence-interval lower bound crosses a threshold.
    - New production failures get added to the CI set.
- **Quotes:**
  - "Start with error analysis, not infrastructure." [verified]
  - "Transition matrices show where failures cluster." [verified]
- **Maps to:** 07, 08, 09, 10, 12

### 5. Shreya Shankar et al., "Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences" (EvalGen)
- **URL:** https://arxiv.org/abs/2404.12272
- **Date:** 2024-04-18 (UIST 2024)
- **Key claims:**
  - LLM-generated evaluators inherit the flaws of the LLMs they grade, so they need human checking.
  - **Criteria drift:** you need criteria to grade outputs, and grading outputs changes your criteria. Some criteria only emerge after you have seen outputs.
- **Practical techniques:**
  - EvalGen workflow: an LLM proposes criteria and candidate implementations (code assertions or LLM-grader prompts). A human grades a small sample. The system keeps the implementations that best agree with the human grades.
  - Teach this as "the evaluator is itself a model that needs a test set."
- **Quote:** "users need criteria to grade outputs, but grading outputs helps users define criteria" (Shankar et al.) [verified]
- **Maps to:** 08, 07

### 6. Shreya Shankar, DocETL and agentic query optimization
- **URL:** https://github.com/ucbepic/docetl (project); related papers https://arxiv.org/abs/2509.02896 and https://arxiv.org/abs/2512.02289 (URLs listed on her homepage, https://www.sh-reya.com/)
- **Date:** 2024 onward; colloquium talks in 2026 [secondary]
- **Key claims:**
  - LLM pipelines over unstructured data can be optimized like database queries. An agent rewrites the pipeline into logically equivalent plans (rewrite directives) and searches for the best accuracy/cost trade-off.
  - Reported adoption: 3.5k+ GitHub stars and 4.1k+ hosted pipelines [secondary, from a 2026 colloquium abstract].
- **Practical techniques:**
  - Decompose a hard LLM task into map, reduce, and resolve operators.
  - Let an optimizer agent propose rewrites (chunking, gleaning or self-refine, model cascades) and score each candidate on a labeled sample.
  - This is a concrete, data-engineering-friendly example of hill-climbing a pipeline against an eval.
- **Quote:** none verified from a primary page. Do not quote.
- **Maps to:** 09, 06, 12
- **Note:** The DocETL GitHub URL is from memory and was not fetched in this session. [unverified URL]

### 7. Eugene Yan, "Evaluating the Effectiveness of LLM-Evaluators (aka LLM-as-Judge)"
- **URL:** https://eugeneyan.com/writing/llm-evaluators/
- **Date:** 2024-08
- **Key claims:**
  - Use direct scoring for objective criteria (faithfulness, toxicity), and pairwise comparison for subjective ones (tone, persuasiveness). Pairwise aligns better with humans.
  - Binary outputs with precision and recall are easier to operate than correlation metrics. Use Cohen's kappa because it corrects for chance agreement.
  - LLM-human agreement often trails human-human agreement. In one summarization study GPT-3.5 caught only 30-60% of inconsistent summaries.
  - Known judge biases: position, verbosity, and self-enhancement. Fine-tuned judges generalize poorly.
- **Practical techniques:**
  - Score one dimension per prompt, and use chain-of-thought.
  - Use a panel of small judges (PoLL): reportedly about the quality of one GPT-4 judge at roughly 1/7 the cost.
  - Use SelfCheckGPT-style consistency sampling.
  - Paraphrase or swap the order in pairwise prompts to cancel position bias.
- **Quote:** "The LLM-evaluators had high variance in correlation with human judgments across the datasets." (Eugene Yan) [verified]
- **Maps to:** 08

### 8. Eugene Yan, "Product Evals in Three Simple Steps"
- **URL:** https://eugeneyan.com/writing/product-evals/
- **Date:** 2025-11-23
- **Key claims:**
  - (1) Label a small, balanced dataset. (2) Align one LLM evaluator per criterion. (3) Run the harness on every change.
  - Human annotators often reach a kappa of only 0.2-0.3 and miss defects when tired. A judge that beats human recall and consistency counts as a success.
- **Practical techniques:**
  - Collect 50-100 *fail* cases inside 200+ samples. Source failures organically from weaker models, because synthetic defects from strong models are exaggerated or too subtle.
  - Split 75/25 between prompt iteration and held-out test.
  - Keep one evaluator per dimension. Combine them with rules, and label each as a guardrail (blocks ship) or a north-star metric.
  - Correct pairwise position bias by running both orders and recording a tie if the verdict flips.
  - Kappa of 0.4-0.6 is substantial agreement, and above 0.7 is excellent.
  - The harness emits a single-row summary for a spreadsheet with conditional formatting.
  - **Error bars:** with 200 samples and 3% observed defects, the 95% CI is about ±2.4%, too wide to prove a 5% requirement. With 400 samples it is about ±1.7%. Halving the margin needs 4x the samples.
- **Quote:** none taken. The numbers above are the teachable part. [verified]
- **Maps to:** 07, 08, 09 (error bars)

### 9. Eugene Yan, "An LLM-as-Judge Won't Save The Product—Fixing Your Process Will"
- **URL:** https://eugeneyan.com/writing/eval-process/
- **Date:** 2025-04-20
- **Key claims:**
  - Evals are a practice, not a tool.
  - Evals are the scientific method: observe, annotate, hypothesize, experiment, measure.
  - Eugene advocates eval-driven development (EDD): write evals first, then build to pass them. This is in mild tension with the Hamel/Shreya FAQ.
- **Practical techniques:**
  - Continuous sampling and annotation.
  - Calibrate judges with precision and recall (binary) or correlation (pairwise).
  - Use component metrics: retrieval recall and generation faithfulness.
  - Mix implicit and explicit user feedback.
- **Quotes:**
  - "Building product evals is simply the scientific method in disguise." [verified]
  - "First, write some evals; then, build systems that pass those evals." [verified]
- **Maps to:** 07, 09

### 10. Eugene Yan, "Patterns for Building LLM-based Systems & Products"
- **URL:** https://eugeneyan.com/writing/llm-patterns/
- **Date:** 2023-07 (the page shows no date; July 2023 is from memory [unverified date])
- **Key claims:** seven patterns:
  1. Evals
  2. RAG
  3. Fine-tuning
  4. Caching
  5. Guardrails
  6. Defensive UX
  7. Collecting user feedback
- **Practical techniques:** use it as the system-design checklist for an LLM feature. Defensive UX and the feedback flywheel are often missing from engineers' designs.
- **Quote:** "Evals enable us to measure how well our system or product is doing and detect any regressions." [verified]
- **Maps to:** 01, 12, 11

### 11. Jason Liu, "There Are Only 6 RAG Evals" (and the RAG and context-engineering series)
- **URL:** https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/ ; series index https://jxnl.co/writing/2025/09/11/rag-series-index/ ; context engineering index https://jxnl.co/writing/2025/08/28/context-engineering-index/
- **Date:** 2025-05-19 (the series runs 2024-2025)
- **Key claims:**
  - RAG has three objects: Question, Context, Answer. Their six conditional relationships cover the whole eval space:
    1. C|Q, context relevance
    2. A|C, faithfulness
    3. A|Q, answer relevance
    4. C|A, support coverage
    5. Q|C, answerability
    6. Q|A, self-containment
  - Diagnose by symptom: a wrong answer points to faithfulness, an irrelevant answer to answer relevance, and a missing answer to retrieval.
  - Tier the evals: retrieval precision and recall first (cheap, deterministic), then the three primary relationships, then the advanced ones.
  - His September 2025 coding-agent series reports that grep and agentic search beat embeddings for coding agents (Augment, Cline talks).
- **Practical techniques:**
  - Start with retrieval metrics (precision, recall, MRR) on synthetic question sets before judging generation.
  - Weight relationships by domain: medical RAG needs faithfulness, and technical docs need answerability.
- **Quote:** "If your retriever pulls irrelevant context, your generator is doomed from the start." (Jason Liu) [verified]
- **Maps to:** 07, 03

### 12. Chip Huyen, "Agents" (and the book *AI Engineering*)
- **URL:** https://huyenchip.com/2025/01/07/agents.html ; book: https://www.oreilly.com/library/view/ai-engineering/9781098166298/
- **Date:** 2025-01-07 (the book was published around Dec 2024 / Jan 2025)
- **Key claims:**
  - An agent is defined by its environment and its action space. Tools are read actions (perception) or write actions (which need extra security care).
  - Errors compound over steps, so agents need stronger models.
  - Separate planning from execution: generate a plan, validate it, then execute.
  - Evaluate agents by failure type: planning failures (invalid tool, bad parameters, goal or time-constraint failure), tool failures, and inefficiency (steps, cost, latency).
  - Chapter 3 of the book is "Evaluation", covering AI-as-a-judge [secondary, from the publisher's TOC].
- **Practical techniques:**
  - Plan validators: reject plans that call nonexistent tools or exceed a step limit.
  - Generate several candidate plans and pick one with a judge.
  - Use intent classification for routing and rejecting out-of-scope requests.
  - Run tool ablations, and track the tool-call distribution to spot misused tools.
  - Write plans in natural language so they survive tool API changes.
  - Use ReAct or Reflexion reflection.
- **Quotes:**
  - "Planning, at its core, is a search problem" (Chip Huyen) [verified]
  - "An agent is anything that can perceive its environment and act upon that environment." [verified]
- **Maps to:** 06, 10, 01

---

## B. Agent loops from scratch, and long-running loops (PRIORITY)

### 13. Thorsten Ball (Amp), "How to Build an Agent" ("The Emperor Has No Clothes")
- **URL:** https://ampcode.com/how-to-build-an-agent
- **Date:** 2025-04-15
- **Key claims:**
  - A code-editing agent is "an LLM, a loop, and enough tokens".
  - It fits in under 400 lines of Go, mostly boilerplate.
  - The model decides when to call a tool. Your program runs the tool and appends the result. The API is stateless, so you resend the whole conversation every turn.
  - Product polish comes from engineering, not from a secret breakthrough.
- **Practical techniques:**
  - The loop:
    1. Read user input and append it.
    2. Send the messages and tool schemas to the model.
    3. Print the text.
    4. If there is a tool_use, run it and append the tool_result.
    5. Repeat until no tool calls, then wait for the human.
  - Three tools: `read_file`, `list_files`, and `edit_file` (string replace, or create the file). Each tool is a name, a description, an input schema, and a function.
  - Line counts: about 90 lines for the chat loop, about 190 with read/list, about 300 final.
  - Ideal for the module 06b lab: students build this, then add stop conditions.
- **Quote:** "It's an LLM, a loop, and enough tokens." (Thorsten Ball) [verified]
- **Maps to:** 06b, 05, 06
- **Related:** Amp's "Raising An Agent" podcast with Quinn Slack, episode 9 (Jan 2026): "the assistant is dead, long live the factory". Amp removed its editor extension in Feb 2026 to go CLI/agent-first. [secondary]

### 14. Geoffrey Huntley, "how to build a coding agent: free workshop"
- **URL:** https://ghuntley.com/agent/
- **Date:** 2025-08-24
- **Key claims:**
  - Every coding agent (Cursor, Claude Code, Amp) is roughly "300 lines of code running in a loop with LLM tokens".
  - Some models are more "agentic", biased toward action and tool calls, than others.
  - The context window is like scarce memory (malloc). The harness and system prompt eat part of it, and quality degrades as it fills.
- **Practical techniques:**
  - Build up the agent in stages: a stub tool (weather), then read_file, list_files, bash, edit, and code_search (ripgrep).
  - Use **one context window per activity**, and keep the toolset small, since MCP tool descriptions consume context.
  - The **Oracle pattern:** wire a stronger reasoning model in as a *tool* the main agent calls for planning and checking.
- **Quote:** "The more you allocate to a context window, the worse the performance of the context window will be" (Geoffrey Huntley) [verified]
- **Maps to:** 06b, 03, 05

### 15. Geoffrey Huntley, "Ralph Wiggum as a 'software engineer'"
- **URL:** https://ghuntley.com/ralph/
- **Date:** 2025-07-14
- **Key claims:**
  - In its purest form, Ralph is a bash loop: `while :; do cat PROMPT.md | claude-code ; done`.
  - It works best for greenfield bootstrapping, not legacy code.
  - Ralph's defects are fixable by tuning prompts, "like a guitar". An engineer is still required.
  - Huntley built the CURSED programming language with it.
- **Practical techniques (directly teachable as "loop design"):**
  - **Deterministic context each iteration:** load the same `specs/*` (one spec per file) and a prioritized `fix_plan.md`.
  - **One item per loop:** Ralph picks the most important item, does it, updates the plan, and exits. Regenerate the plan when it goes stale.
  - **State lives outside the context:** the plan, specs, and AGENT.md (learned build and test commands) persist between iterations. Commit and tag after every green build.
  - **Backpressure:** tests, type checkers, and static analysis reject bad work. Ask Ralph to document *why* each test exists.
  - **Subagents as the context firewall:** the main context acts as a scheduler. Fan out search to many subagents, but allow only one subagent for build/test, to avoid backpressure chaos.
  - Explicit anti-placeholder instruction, quoted from his prompt: "DO NOT IMPLEMENT PLACEHOLDER OR SIMPLE IMPLEMENTATIONS. WE WANT FULL IMPLEMENTATIONS." [verified]
  - **Failure modes to teach:**
    - ripgrep misses cause "it's not implemented" conclusions, which lead to duplicate implementations.
    - Placeholder code.
    - Dynamic languages without a type checker.
    - Broken trees that need a reset or a rescue prompt.
    - Context degrading as it fills (he budgets about 170k).
- **Quotes:**
  - "the technique is deterministically bad in an undeterministic world." [verified]
  - "To get good outcomes with Ralph, you need to ask Ralph to do one thing per loop." [verified]
- **Anecdote:** Huntley shared a message reporting a "$50k USD contract, delivered, MVP, tested + reviewed with @ampcode" for "$297 USD" in cost. [verified as quoted on the page; this is the client's claim, not audited]
- **Maps to:** 06b, 11, 03

### 16. Dex Horthy (HumanLayer), "A Brief History of Ralph"
- **URL:** https://humanlayer.dev/blog/brief-history-of-ralph
- **Date:** 2026-01-06
- **Key claims:**
  - Timeline:
    - Jun 2025: first meetup demo.
    - Jul 2025: Ralph post.
    - Aug 2025: repomirror.
    - Sep 2025: CURSED launch.
    - Dec 2025: Anthropic ships an official ralph-wiggum Claude Code plugin.
  - The plugin misses the point. It focuses on "run forever" through a Stop hook that re-feeds the prompt *inside the same session*. The real idea is fresh context per unit of work.
  - Specific complaints:
    - It fails without `--dangerously-skip-permissions`.
    - It installs a stop hook that applies to every session in the directory.
    - Its state lives in a markdown file, and deleting that file can break Claude in the repo.
- **Practical techniques:**
  - Know the end state and how you will test it *before* you loop. Ralph is bad for exploratory work.
  - Code is cheap: rerun the loop on fresh code rather than rebasing a stale PR. A 6-hour React refactor run hit merge conflicts and was never merged.
  - On existing codebases, prefer one small change per night over 50 or none.
- **Quote:** "carve off small bits of work into independent context windows" (Dex Horthy) [verified]
- **Maps to:** 06b, 03

### 17. repomirror team (YC Agents hackathon), "We Put a Coding Agent in a While Loop and It Shipped 6 Repos Overnight"
- **URL:** https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md
- **Date:** around 2025-08-25 (from a screenshot date on the page)
- **Key claims:**
  - Headless Claude Code in a while loop ported six codebases overnight:
    - assistant-ui, React to Vue
    - Browser Use, Python to TypeScript
    - Vercel AI SDK, TypeScript to Python
    - spec-based recreations of Convex and Dedalus
  - Numbers: about 1,100 commits, under $800 in inference, about $10.50/hour per Sonnet agent.
- **Practical techniques:**
  - Loop: `cat prompt.md | claude -p --dangerously-skip-permissions`.
  - The prompt asks for a commit and push after every file edit, keeps plans and TODOs in a scratch dir, and splits effort roughly 80% porting / 20% tests.
  - **Short prompts beat long ones:** a 1,500-word "improved" prompt made the agent slower and worse. They cut it back to 103 words.
  - **Runaway/stuck behaviour observed:**
    - One agent used `pkill` to terminate itself after realizing it was stuck in an infinite loop.
    - Agents over-reached, for example adding Flask/FastAPI integrations that had no JS counterpart.
    - Output reached about 90% complete and needed manual work for the last 10%.
- **Quote:** "Make a commit and push your changes after every single file edit." (prompt text) [verified]
- **Maps to:** 06b, 11, 10

### 18. Geoffrey Huntley, "nobody should type code by hand anymore. here's what's left."
- **URL:** https://ghuntley.com/agency/
- **Date:** 2026-10-13
- **Key claims:**
  - The model is no longer the bottleneck. What matters is the operator's vision, verification, and agency.
  - Human code review does not scale to agent output, so verification must be automated (backpressure).
  - Skill packs and AGENTS.md are probabilistic. Test them against runs without them.
- **Practical techniques:**
  - **Pre-commit hooks that inspect the diff** and reject architectural violations (for example direct observability calls that bypass internal modules), feeding corrective prompts back to the agent. Danger-style CI rules do the same.
  - **Property-based tests** for invariants, for example "a customer is charged only once", using Hypothesis under fault injection.
  - Nix to put the whole system, including the OS, under test.
  - **Stuck-loop recovery:** prompt the agent to introspect on its own tool-call trace and replan.
  - Every few months, delete skills and AGENTS.md and re-test, since a new model can make old tuning counterproductive.
  - Stick with one model rather than switching weekly.
- **Quote:** "If humans eyeballing code were sufficient engineering to stop bugs, we'd never have had any defects." (Geoffrey Huntley) [verified]
- **Maps to:** 06b, 10, 11, 14

### 19. Simon Willison, "Designing agentic loops"
- **URL:** https://simonwillison.net/2025/Sep/30/designing-agentic-loops/
- **Date:** 2025-09-30
- **Key claims:**
  - Coding agents are brute-force solvers. They shine when there is a clear goal plus tools to iterate toward it.
  - The skill is designing the tools and the loop.
  - YOLO mode (auto-approve everything) is risky but far more productive.
- **Practical techniques:**
  - Sandbox YOLO runs: Docker, Apple `container`, or GitHub Codespaces. Restrict files, secrets, and network, with an allowlist of trusted hosts.
  - Prefer shell commands to MCP, documented in AGENTS.md with one example each.
  - Use scoped credentials against staging only. Give any credential that can spend money a dedicated org with a hard budget, for example a $5 cap.
  - Good loop problems have clear success criteria plus trial and error:
    - debugging
    - query performance tuning
    - dependency upgrades
    - shrinking container images
  - Automated tests multiply the value of a loop.
- **Quote:** "An AI agent is an LLM wrecking its environment in a loop." (Simon Willison) [verified]
- **Maps to:** 06b, 11, 13

### 20. Armin Ronacher, "The Coming Loop"
- **URL:** https://lucumr.pocoo.org/2026/6/23/the-coming-loop/
- **Date:** 2026-06-23
- **Key claims:**
  - The next stage is harness loops: work is queued, an agent attempts it, and an *outer harness* decides whether it is really done, even after the model says it is finished.
  - Loops have worked poorly for code he cares about. They amplify defensive, over-complex code and erode understanding.
  - Loops work well for ports, performance experiments, security scanning, and research.
  - The future is inevitable because attackers and competitors loop too.
- **Practical techniques:**
  - When the agent stops, the harness can:
    - continue the same session
    - inject a new message
    - start a fresh session with modified context
    - route the task to another machine
  - Use benchmarks as the keep/discard signal for experiments, and an LLM judge where no binary test exists.
  - Example: his MiniJinja-to-Go port.
- **Quote:** "The harness just needs some signal that lets it continue." (Armin Ronacher) [verified]
- **Maps to:** 06b, 09, 14

### 21. Dex Horthy / HumanLayer, "12-Factor Agents"
- **URL:** https://github.com/humanlayer/12-factor-agents (factor 8: `content/factor-08-own-your-control-flow.md`; factor 9: `content/factor-09-compact-errors.md`)
- **Date:** 2025 (first published around April 2025 [unverified date])
- **Key claims:**
  - Good production agents are "mostly just software" with LLM steps.
  - The 12 factors:
    1. Natural language to tool calls
    2. Own your prompts
    3. Own your context window
    4. Tools are just structured outputs
    5. Unify execution and business state
    6. Launch/pause/resume APIs
    7. Contact humans via tool calls
    8. Own your control flow
    9. Compact errors into context
    10. Small, focused agents
    11. Trigger from anywhere
    12. Agent as a stateless reducer
  - Honourable mention: pre-fetch context.
- **Practical techniques:**
  - **Factor 8:** some tool calls *break the loop*: clarification requests, high-stakes actions such as deploys, and long-running jobs. Others *continue* it, such as data fetches.
    - The most-requested framework feature is an interrupt *between tool selection and tool invocation*, for approval.
    - Save the thread state and resume it via webhook.
  - **Factor 9:** append tool errors to the context so the model can self-heal. Keep a `consecutive_errors` counter that resets on success. After about 3, break the loop, reset the context, or escalate to a human.
  - **Factor 12:** model the agent as a reducer `(state, event) -> state`. This maps directly to the Kubernetes reconciler analogy in module 06b.
- **Quotes:**
  - "Rather, they are comprised of mostly just software." [verified]
  - "you can do JUST THIS without doing any of the other 11 factors" (factor 9) [verified]
- **Maps to:** 06, 06b, 06c, 11

### 22. Dex Horthy / HumanLayer, "Getting AI to Work in Complex Codebases" (Advanced Context Engineering for Coding Agents; research-plan-implement)
- **URL:** https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md
- **Date:** around late Aug/Sep 2025 (references Aug 2025 events; the page shows no explicit date)
- **Key claims:**
  - "Frequent intentional compaction": design the whole workflow around keeping the context lean.
  - Human review has the most leverage at the research and plan stages. One bad line of research becomes thousands of bad lines of code.
  - Includes a failure case: removing Hadoop from parquet-java failed because the research was shallow.
- **Practical techniques:**
  - **Research, then Plan, then Implement** as separate sessions, each starting fresh from a markdown artifact.
  - Keep context utilization in the **40-60%** range.
  - Use subagents for search and summarization, so the main context stays clean.
  - Throw away wrong research and rerun it with more steering.
  - Specs and plans are the primary review artifact. Review tests closely rather than every generated line.
- **Quotes:**
  - "the contents of your context window are the ONLY lever you have to affect the quality of your output." [verified]
  - "keeping utilization in the 40%-60% range" [verified]
- **Maps to:** 03, 04, 06b

### 23. Kent Beck, "Augmented Coding: Beyond the Vibes"
- **URL:** https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes (redirected from tidyfirst.substack.com)
- **Date:** 2025-06-25
- **Key claims:**
  - Augmented coding is not vibe coding. You still care about code quality, tests, and coverage, and the AI writes most of the code.
  - AI removes yak-shaving and shifts human effort to consequential design decisions.
  - The resulting B+ tree was correct and performant, but had more accidental complexity than he liked.
- **Practical techniques:**
  - **Three warning signs that the "genie" is going off track:**
    1. Loops (repeating itself)
    2. Functionality nobody requested
    3. Cheating, such as disabling or deleting tests
  - These are a ready-made stuck/runaway rubric for module 06b/11.
  - **His system prompt:**
    - Follow `plan.md`. On "go", implement the next unmarked test and only enough code to pass it.
    - Use Red-Green-Refactor.
    - Separate structural commits from behavioral commits (Tidy First).
    - Commit only when all tests and lint pass.
  - Recovery strategy: when Rust plus the ownership model got stuck in complexity, he had the AI write Python first, then transliterate to Rust.
- **Quotes:**
  - "In vibe coding you don't care about the code, just the behavior of the system." [verified]
  - "Yak shaving mostly goes away." [verified]
- **Related:** "Augmented Coding: Copy/Paste Detector" (2025-06-09, https://newsletter.kentbeck.com/p/augmented-coding-copypaste-detector) describes building tooling to "help the genie make up for its lack of design sense" [secondary, paywalled teaser].
- **Maps to:** 04, 06b, 11, 00

---

## C. Agentic coding practice

### 24. Simon Willison, "Vibe engineering" (and the *Agentic Engineering Patterns* guide)
- **URL:** https://simonwillison.net/2025/Oct/7/vibe-engineering/ ; guide: https://simonwillison.net/guides/agentic-engineering-patterns/ ; red/green TDD chapter: https://simonwillison.net/guides/agentic-engineering-patterns/red-green-tdd/
- **Date:** 2025-10-07 (post). The guide started around Feb 2026 and is updated continuously.
- **Key claims:**
  - Vibe coding means not caring how the code works. Vibe engineering, now usually called "agentic engineering", means experienced engineers using agents while staying accountable for the result.
  - Working this way demands *more* skill. AI amplifies existing expertise.
- **Practical techniques:**
  - What makes agents effective:
    - automated tests
    - planning up front
    - good documentation
    - version control discipline
    - CI, formatting, linting, and preview deploys
    - a code review culture
    - managing the agent like a collaborator
    - manual QA
    - research skills
    - judgment about what to delegate
    - re-estimation
  - Guide chapters to reuse:
    - "Red/green TDD": write the tests, *confirm they fail*, then implement.
    - "First run the tests": a four-word opener that loads the testing discipline.
    - "Agentic manual testing": the agent drives the browser.
    - "Linear walkthroughs" for understanding code.
    - "Anti-patterns", for example handing unreviewed agent code to collaborators.
- **Quote:** "Test-first development is particularly effective with agents that can iterate in a loop." (Simon Willison) [verified]
- **Maps to:** 00, 04, 10, 14

### 25. Simon Willison, "Embracing the parallel coding agent lifestyle"
- **URL:** https://simonwillison.net/2025/Oct/5/parallel-coding-agents/
- **Date:** 2025-10-05
- **Key claims:**
  - Running several agents in parallel is useful even though *review* is the bottleneck.
  - Code you specified yourself is far easier to review than surprise code.
- **Practical techniques:** four parallel-safe task types, plus scouting.
  1. Research and proof-of-concept builds, which are throwaway. Agents can learn new libraries by reading the dependency source.
  2. Codebase explanations, written to notes for reuse as later context.
  3. Small maintenance chores, such as deprecation warnings.
  4. Carefully pre-specified work.
  - "Send out a scout": give an agent a hard task you don't intend to merge, just to learn where the sticky bits are.
  - Use cloud async agents for riskier work, and local YOLO only where injection is unlikely.
- **Quote:** "I can only focus on reviewing and landing one significant change at a time" (Simon Willison) [verified]
- **Maps to:** 04, 14

### 26. Simon Willison, "The lethal trifecta for AI agents" and "Design Patterns for Securing LLM Agents against Prompt Injections"
- **URL:** https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ ; https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/
- **Date:** 2025-06-16 and 2025-06-13
- **Key claims:**
  - Private data + untrusted content + external communication = exfiltration risk.
  - LLMs cannot reliably tell trusted instructions from untrusted ones.
  - In web security terms, 95% guardrail detection is a failing grade.
  - Users who mix MCP tools assemble the trifecta themselves, and no vendor can fix that.
  - The paper argues general-purpose agents cannot offer meaningful safety guarantees. You trade flexibility for security.
- **Practical techniques:**
  - Remove one leg of the trifecta, especially the outbound channels: HTTP, image loading, and links.
  - Six patterns:
    1. **Action-Selector:** the agent never sees tool outputs.
    2. **Plan-Then-Execute:** the tool sequence is fixed before untrusted data is seen.
    3. **LLM Map-Reduce:** isolated sub-agents return constrained outputs.
    4. **Dual LLM:** a privileged LLM handles symbolic references, and a quarantined LLM reads the untrusted data.
    5. **Code-Then-Execute:** CaMeL-style taint tracking.
    6. **Context-Minimization.**
- **Quotes:**
  - "LLMs are unable to reliably distinguish the importance of instructions based on where they came from." [verified]
  - (from the paper, via Simon) "we believe it is unlikely that general-purpose agents can provide meaningful and reliable safety guarantees" [verified]
- **Maps to:** 13, 05, 11

### 27. Armin Ronacher, "Agentic Coding Recommendations" and "Agentic Coding Things That Didn't Work"
- **URL:** https://lucumr.pocoo.org/2025/6/12/agentic-coding/ ; https://lucumr.pocoo.org/2025/7/30/things-that-didnt-work/
- **Date:** 2025-06-12 and 2025-07-30
- **Key claims:**
  - Tool quality and codebase simplicity matter more than model choice.
  - Go suits agents for new backends: explicit context, fast tests, and less magic than Python.
  - The July post covers what didn't work for him:
    - most slash commands
    - hooks, which can't change what executes, and denies don't work in YOLO mode
    - print mode, which is slow and flaky
    - sub-agents that mix reads and writes, which create chaos
  - Fresh sessions plus markdown notes often beat sub-agents.
- **Practical techniques:**
  - Every script, log, or service is a tool. Make tools fast, give them clear errors, and make them misuse-proof.
  - Use a Makefile with `make dev` guarded against double launch, with output tee'd to a log file.
  - Route emails to logs so the agent can complete sign-in flows on its own.
  - Write plain SQL and plain functions, with permission checks local to the route.
  - Put override scripts on PATH to steer the agent toward the right tools.
  - Only automate tasks you actually do regularly, and delete unused automation.
- **Quotes:**
  - "the dumbest possible thing that will work" [verified]
  - "I only automate things that I do regularly." [verified]
- **Related 2026 posts:**
  - "Pi: The Minimal Agent Within OpenClaw" (2026-01-31, https://lucumr.pocoo.org/2026/1/31/pi/): he moved to a minimal agent.
  - "A Year of Vibes" (2025-12-22, https://lucumr.pocoo.org/2025/12/22/a-year-of-vibes/). [secondary]
- **Maps to:** 04, 05, 06b

### 28. Mitchell Hashimoto, "My AI Adoption Journey" and "Vibing a Non-Trivial Ghostty Feature"
- **URL:** https://mitchellh.com/writing/my-ai-adoption-journey ; https://mitchellh.com/writing/non-trivial-vibing
- **Date:** 2026-02-05 and 2025-10-11
- **Key claims:**
  - Tool adoption goes through inefficiency, then adequacy, then workflow-altering discovery.
  - Real value starts when you leave the chatbot for an agent that can read files, run programs, and make HTTP requests.
  - Never ship AI-written code without thorough manual review.
- **Practical techniques:**
  - Six steps:
    1. Drop the chatbot.
    2. **Reproduce your own past commits** with an agent to build skill.
    3. **End-of-day agents:** spend the last 30 minutes launching research, exploration, and triage agents that only write reports.
    4. Outsource the "slam dunks" to a background agent, **with notifications off**.
    5. **Engineer the harness:** every agent mistake becomes either an AGENTS.md line or a purpose-built tool, such as a screenshot script or a filtered test runner.
    6. Always have an agent running, but only on useful work. For him that is about 10-20% of the day.
  - The Ghostty feature:
    - 16 sessions, $15.98 in Amp tokens, about 8 hours.
    - A hand-written plan, refined by a read-only planning subagent and saved as a spec.
    - UI-only prototypes first.
    - A few "hail mary" prompts on a stubborn bug, then research it by hand and delete any fix he didn't understand.
    - Cleanup sessions: docs and dead-code removal.
    - Stub functions with TODOs for the agent to fill in.
    - Finish by asking the agent what he might be missing.
- **Quotes:**
  - "Immediately cease trying to perform meaningful work via a chatbot" [verified]
  - "Please don't ever ship AI-written code without a thorough manual review." [verified]
- **Maps to:** 04, 06b (end-of-day/overnight agents), 11, 14

### 29. Eugene Yan, "How to Work and Compound with AI"
- **URL:** https://eugeneyan.com/writing/working-with-ai/
- **Date:** 2026-05-03
- **Key claims:**
  - Context is infrastructure. Onboard every session like a new hire.
  - Encode taste as layered config files.
  - You can't delegate what you can't verify.
- **Practical techniques:**
  - Organize files so they are greppable, with a per-project index of docs, owners, and when to read each.
  - Turn repeated work into skills. Refine a skill from correction transcripts rather than by editing it by hand.
  - Verify in layers: deterministic checks on write, then tests, then evals, then review.
  - **Models watching models:** a fresh-context second session checks a long run against the original spec, catching both execution drift and direction drift.
  - Run 3-6 parallel sessions in git worktrees, with status lines and sounds for observability.
  - Mine past transcripts for repeated corrections, and prune rules so each lives in one place.
- **Quote:** "You can't delegate what you can't verify, so this requires first defining success criteria and metrics." (Eugene Yan) [verified]
- **Maps to:** 03, 04, 11, 14

### 30. Steve Yegge, Beads and Gas Town (and the *Vibe Coding* book with Gene Kim)
- **URL:** https://github.com/steveyegge/beads ; https://github.com/steveyegge/gastown ; book: *Vibe Coding: Building Production-Grade Software With GenAI, Chat, Agents, and Beyond* (IT Revolution)
- **Date:**
  - Beads: Oct 2025 [secondary].
  - Gas Town: released 2026-01-01 [secondary: Wikipedia and trade press].
  - Book: Oct 2025 [secondary; the date was not confirmed].
- **Key claims:**
  - **Beads** is a dependency-aware, git/Dolt-backed issue graph that acts as persistent agent memory. It replaces stale markdown TODO files that bloat context.
  - **Gas Town** orchestrates 20-30 parallel Claude Code instances with roles [secondary]:
    - Mayor: coordinator
    - Polecats: workers
    - Witness: detects stuck agents and triggers recovery
    - Refinery: merge queue that runs verification
  - Work state lives in git-backed "hooks" so agents survive crashes.
  - Yegge has said newer models did *not* reduce the need for orchestration [secondary].
- **Practical techniques:**
  - Use `bd ready` to list unblocked work and `bd update <id> --claim` to claim a task atomically. Use `bd dep add` to link tasks, and compact old closed tasks to save context.
  - Hash IDs avoid merge collisions across agents.
  - Gas Town's health state "GUPP Violation" flags hooked work with no progress. It is an explicit **stuck-loop detector** in an orchestrator, and a good example for module 06b.
  - Use it as the extreme pro-multi-agent counterpoint to Cognition.
- **Quote:** "Beads provides a persistent, structured memory for coding agents." (Beads README) [verified]
- **Note:** Yegge's Medium posts were not readable (403):
  - "Welcome to Gas Town" (Jan 2026) [unverified URL/title]
  - "Welcome to the Wasteland: A Thousand Gas Towns" (2026-03-04) [secondary]
  - "Gas Town: from Clown Show to v1.0" (2026-04-03) [secondary]
  - "Revenge of the Junior Developer" (Sourcegraph, Mar 2025) [secondary]
  - The book's "FAAFO" framework (fast, ambitious, autonomous, fun, optionality) [secondary]
- **Maps to:** 06, 06b, 00

### 31. Cognition (Walden Yan), "Don't Build Multi-Agents" and "Multi-Agents: What's Actually Working"
- **URL:** https://cognition.com/blog/dont-build-multi-agents ; https://cognition.com/blog/multi-agents-working
- **Date:** 2025-06-12 and 2026-04-22
- **Key claims:**
  - 2025, two principles:
    1. Share full context: whole agent traces, not just messages.
    2. Actions carry implicit decisions, and conflicting decisions produce bad results.
  - 2025 example: in a Flappy Bird clone split into subtasks, one subagent built a Super Mario background and another built a non-Flappy bird.
  - 2025 recommendation: default to a single-threaded linear agent, plus a compression model for very long tasks.
  - 2026 update: multi-agent now works *when writes stay single-threaded and the other agents contribute intelligence*:
    - **Clean-context review agent:** about 2 bugs caught per PR, most of them severe.
    - **"Smart friend" escalation** to a stronger model: works only when the primary model is also strong.
    - **Manager/child agents:** live in Devin.
  - Parallel writers and unstructured swarms still fail.
  - Demos that run many agents usually have simple, verifiable success criteria, which real software lacks.
- **Practical techniques:**
  - Review agents get a *fresh* context, reasoning only from the diff, which avoids long-context degradation.
  - Use parallelism only for read and research work.
  - Cognition's other relevant 2026 posts:
    - "Closing the Agent Loop: Devin Autofixes Review Comments" (2026-02-10)
    - "Devin can now Schedule Devins" (2026-03-20, recurring sessions that keep state)
    - "What We Learned Building Cloud Agents" (2026-04-23)
    - These URLs are from the cognition.com/blog index. [secondary: titles seen, bodies not read]
- **Quotes:**
  - "the simple architecture will get you very far" (2025) [verified]
  - "writes stay single-threaded and the additional agents contribute intelligence rather than actions" (2026) [verified]
- **Maps to:** 06, 06b, 10

---

## D. Frameworks, context engineering, and ambient agents

### 32. LangChain team, "Context Engineering" (for agents)
- **URL:** https://www.langchain.com/blog/context-engineering-for-agents
- **Date:** 2025-07-02
- **Key claims:**
  - Context engineering is "filling the context window with just the right information for the next step" (attributed to Karpathy).
  - It has four strategies:
    1. **Write:** scratchpads and memories outside the window.
    2. **Select:** CLAUDE.md and rules files, RAG over tool descriptions, grep plus knowledge graphs for code.
    3. **Compress:** auto-compaction, summarizing token-heavy tool results, trimming.
    4. **Isolate:** sub-agents, sandboxed code environments, and state-schema fields hidden from the LLM.
- **Practical techniques:**
  - Map each LangGraph feature to a strategy, which suits the module 06c lab.
  - Teach Drew Breunig's four failure types (poisoning, distraction, confusion, clash) alongside.
- **Quote:** (Cognition, quoted in the post) "Context engineering" ... is effectively the #1 job of engineers building AI agents. [verified as quoted]
- **Maps to:** 03, 06c

### 33. Drew Breunig, "How Long Contexts Fail"
- **URL:** https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html
- **Date:** 2025-06-22
- **Key claims:** four failure modes.
  - **Poisoning:** in Gemini's Pokémon run, a hallucinated goal kept being referenced.
  - **Distraction:** the Pokémon agent began repeating past actions past about 100k tokens. A Databricks study saw Llama 3.1 405B correctness drop around 32k.
  - **Confusion:**
    - On the Berkeley Function-Calling Leaderboard, every model did worse with more than one tool.
    - A quantized Llama 3.1 8B failed with 46 tools and succeeded with 19.
  - **Clash:** prompts sharded across turns dropped performance 39% on average. o3 went from 98.1 to 64.1.
- **Practical techniques:** use these as diagnostic categories when an agent loop degrades. "Repeating past actions" is the signature of a stuck loop caused by context distraction.
- **Quote:** "when LLMs take a wrong turn in a conversation, they get lost and do not recover." (quoted research finding) [verified]
- **Maps to:** 03, 06b, 01

### 34. Harrison Chase, "Deep Agents"
- **URL:** https://www.langchain.com/blog/deep-agents
- **Date:** 2025-07-30
- **Key claims:**
  - A simple LLM-calls-tools loop makes "shallow" agents.
  - "Deep" agents add four things:
    1. a detailed system prompt
    2. a planning (to-do) tool
    3. sub-agents
    4. a file system
  - Claude Code's to-do tool is a no-op that still keeps the agent on track. It works purely as a context strategy.
  - Released alongside the `deepagents` package.
- **Practical techniques:** in the module 06c lab, build the raw-SDK agent, then add the four components one at a time and measure the effect of each against an eval.
- **Quote:** "Funnily enough - this doesn't do anything! It's basically a no-op." (Harrison Chase, on the to-do tool) [verified]
- **Maps to:** 06c, 06b, 03

### 35. Vivek Trivedy (LangChain), "Improving Deep Agents with harness engineering"
- **URL:** https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering
- **Date:** 2026-02-17
- **Key claims:**
  - Harness changes alone took deepagents-cli from 52.8% to 66.5% on Terminal Bench 2.0, with the model fixed (gpt-5.2-codex). That moved it from outside the top 30 to the top 5.
  - Common failures: reasoning errors, ignoring instructions, skipping tests, and timeouts.
- **Practical techniques (excellent for module 06b and module 09):**
  - **PreCompletionChecklistMiddleware:** blocks the agent from exiting before a verification pass against the spec. This is a stop condition enforced by the harness.
  - **LoopDetectionMiddleware:** counts edits per file and, after N edits, injects a "reconsider your approach" prompt. This is a stuck-loop detector.
  - **Trace-analysis skill:** fetch the traces, run parallel error-analysis agents, then make targeted harness changes. The post warns about overfitting.
  - **Reasoning sandwich:** xhigh effort to plan, high to implement, xhigh to verify. Using xhigh throughout scored worse (53.9% vs 63.6%) because of timeouts.
  - Inject the directory map and time-budget warnings at start.
- **Quote:** "Models are biased towards their first plausible solution." [verified]
- **Maps to:** 06b, 09, 10, 06c
- **Related:** "The Anatomy of an Agent Harness" (2026-03-10) and "Autonomous context compression" (2026-03-11). A March 2026 LangChain post on how they eval Deep Agents argues that more evals do not make better agents [secondary; not read].

### 36. Harrison Chase, "Introducing ambient agents"
- **URL:** https://www.langchain.com/blog/introducing-ambient-agents
- **Date:** 2025-01-14
- **Key claims:**
  - Ambient agents react to event streams in the background and run many tasks concurrently.
  - They should not be fully autonomous. Human-in-the-loop design is the core of them.
- **Practical techniques:**
  - Three human-in-the-loop patterns:
    - **Notify:** flag without acting.
    - **Question:** ask instead of guessing.
    - **Review:** approve, edit, or give feedback on a planned action.
  - An "Agent Inbox" UI built on ticket-queue metaphors, because Slack notifications got lost.
  - LangGraph persistence, interrupts, and cron.
- **Quote:** "Ambient agents listen to an event stream and act on it accordingly, potentially acting on multiple events at a time" [verified]
- **Maps to:** 06c, 11, 06b (scheduled agents)

### 37. Lilian Weng, "LLM Powered Autonomous Agents"
- **URL:** https://lilianweng.github.io/posts/2023-06-23-agent/
- **Date:** 2023-06-23
- **Key claims:**
  - An agent is planning plus memory plus tool use:
    - Planning: CoT, ToT, LLM+P, ReAct, Reflexion, Chain of Hindsight.
    - Memory: sensory, short-term, and long-term, with MIPS indexes such as HNSW and FAISS.
    - Tool use: MRKL, Toolformer, HuggingGPT, API-Bank.
  - Open challenges:
    - finite context
    - long-horizon planning and replanning after errors
    - an unreliable natural-language interface
- **Practical techniques:** the canonical taxonomy for the module 06 lecture. Its 2023 "challenges" list is a good "what has and hasn't changed by 2026" exercise.
- **Quote:** "The agent learns to call external APIs for extra information that is missing from the model weights" [verified]
- **Maps to:** 06, 01

### 38. swyx (Latent Space), "The Rise of the AI Engineer" and "Why Agent Engineering"
- **URL:** https://www.latent.space/p/ai-engineer ; talk: https://ai.engineer/talks/why-agent-engineering
- **Date:** 2023-06-30 (essay); AI Engineer Summit 2025 (talk) [secondary]
- **Key claims:**
  - A "shift right" of applied AI toward product engineers. The AI engineer becomes a distinct specialty, like SRE.
  - The 2025 talk frames agent engineering as a discipline distinct from ML and conventional software engineering [secondary].
- **Practical techniques:** framing material for module 00 and module 14 (career positioning).
- **Quote:** "When it comes to shipping AI products, you want engineers, not researchers" [verified]
- **Maps to:** 00, 14

### 39. Andrej Karpathy, "Software Is Changing (Again)" / Software 3.0 (YC AI Startup School)
- **URL:** coverage at https://www.latent.space/p/s3 [secondary]. The original is a YouTube recording; no URL was verified.
- **Date:** around 2025-06-17/18 [secondary; sources differ]
- **Key claims:**
  - Software 3.0 means prompts are programs.
  - Build "Iron Man suits" (augmentation) rather than "Iron Man robots" (full autonomy).
  - Give products an "autonomy slider", partial autonomy, and fast generate-verify loops with a human.
- **Practical techniques:** use the autonomy slider as the organizing idea for module 11 (how much human-in-the-loop) and module 00.
- **Quote:** [secondary] "Iron Man suits" vs "Iron Man robots". Verify the exact wording against the recording before using it.
- **Maps to:** 00, 11

---

## E. Evidence: productivity studies and benchmarks

### 40. METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity" and the Feb 2026 update
- **URL:** https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ ; update: https://metr.org/blog/2026-02-24-uplift-update/
- **Date:** 2025-07-10 and 2026-02-24
- **Key claims (2025):**
  - Design: an RCT with 16 experienced OSS developers and 246 real issues in repos they had maintained for years. The tools were mostly Cursor Pro with Claude 3.5/3.7 Sonnet. Developers were paid $150/hr.
  - Developers took **19% longer** with AI allowed.
  - They forecast a 24% speedup beforehand and *still believed* afterwards that AI had sped them up about 20%.
  - The perception gap is the most teachable finding.
- **Caveats METR states:**
  - The result doesn't generalize to most developers or repos.
  - It doesn't rule out better usage patterns.
  - Learning effects beyond about 50 hours are unknown.
  - METR now marks the 2025 results as out of date.
- **Key claims (2026 update):**
  - The follow-up design broke down because of selection effects:
    - Developers refused to work without AI.
    - 30-50% of developers withheld tasks they didn't want to do without AI.
    - Pay dropped to $50/hr.
    - Concurrent agents made time tracking hard.
  - Late-2025 point estimates showed a speedup:
    - original developers: -18% time, CI -38% to +9%
    - new recruits: -4%, CI -15% to +9%
  - METR calls these numbers only very weak evidence of the size of the effect.
- **Practical techniques:**
  - Teach *measurement*: self-reports are unreliable, so instrument your own workflow, for example time-to-merged-PR on randomized tasks.
  - Connect this to module 09: confidence intervals, and selection bias in eval sets.
- **Quotes:**
  - "a significant slowdown that goes against developer beliefs and expert forecasts" (2025) [verified]
  - "we believe it is likely that developers are more sped up from AI tools now" (2026) [verified]
- **Maps to:** 00, 09, 14

### 41. SWE-bench (Jimenez et al.) and the 2026 retirement of SWE-bench Verified
- **URL:** https://arxiv.org/abs/2310.06770 ; OpenAI post: https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ (returned 403 when fetched [secondary])
- **Date:** 2023-10-10 (ICLR 2024); OpenAI post around 2026-02-23 [secondary]
- **Key claims:**
  - The benchmark has 2,294 real GitHub issue/PR pairs from 12 Python repos. The agent must edit the codebase so that hidden tests pass. At launch Claude 2 solved 1.96%.
  - 2026 [secondary]:
    - OpenAI stopped reporting SWE-bench Verified. Frontier models could reproduce gold patches verbatim for some tasks, and an audit found 59.4% of 138 hard tasks broken.
    - It recommends SWE-bench Pro.
    - The same model scored about 80.9% on Verified and about 45.9% on Pro.
  - Scaffolding differences also move scores significantly.
- **Practical techniques:**
  - Teach the full life cycle of a benchmark: creation, then saturation, then contamination, then retirement.
  - Hidden-test grading equals code-graded outcome evals.
  - Contamination is why a team needs *private* eval sets built from its own traces (link back to Hamel).
- **Quote:** "a mere 1.96% of the issues" (SWE-bench abstract) [verified]
- **Maps to:** 07, 09, 10

### 42. τ-bench (Yao et al., Sierra) and τ²-bench (Barres et al.)
- **URL:** https://arxiv.org/abs/2406.12045 ; https://arxiv.org/abs/2506.07982
- **Date:** 2024-06-17 and 2025-06-09
- **Key claims:**
  - τ-bench: an LLM-simulated user talks to an agent that has domain API tools and a policy document (retail, airline).
  - Grading compares the final database state to an annotated goal state.
  - It introduces **pass^k**: the probability that *all* k independent trials succeed. It measures reliability, not capability. GPT-4o got under 50% task success, and pass^8 was under 25% in retail.
  - τ²-bench adds a **dual-control** telecom domain, modelled as a Dec-POMDP, where the *user* also has tools and shared state.
  - It uses compositional task generation and separates reasoning errors from communication errors.
  - Performance drops sharply when the agent has to guide a user.
- **Practical techniques:**
  - State-based grading: diff the DB, not the transcript.
  - LLM user simulators driven by persona and goal.
  - Report pass^k alongside pass@k.
  - Separate reasoning failures from coordination failures.
  - This is the template for module 10's "simulated users and sandboxed environments".
- **Quotes:**
  - "even state-of-the-art function calling agents (like gpt-4o) succeed on <50% of the tasks" [verified]
  - "significant performance drops when agents shift from no-user to dual-control" [verified]
- **Maps to:** 07, 10

---

## F. Company practice

### 43. Stripe (Alistair Gray), "Minions: Stripe's one-shot, end-to-end coding agents"
- **URL:** https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents ; part 2 (blueprints): https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2 [part 2 not read]
- **Date:** 2026-02-09
- **Key claims:**
  - More than 1,000 PRs merged per week are fully minion-produced. They are human-reviewed but contain no human-written code. InfoQ later reported 1,300+ per week [secondary].
  - It is built on a fork of Block's Goose.
  - Isolated, pre-warmed devboxes spin up in about 10s, cut off from production and the internet. That isolation lets minions run without per-action permission prompts and run in parallel without worktrees.
- **Practical techniques:**
  - **Interleave deterministic steps** (git, lint, tests) with agent loops. Part 2 calls these "blueprints", which are agent skills woven into code [secondary].
  - **Shift feedback left:** a local lint subset runs on each push in under 5 seconds.
  - **Hard loop budget:** at most **two CI rounds** per minion, because each round costs tokens, compute, and time, with diminishing returns.
  - The "Toolshed" internal MCP server hosts 400+ tools, and each minion gets a curated subset.
- **Quotes:**
  - "often one, at most two, CI runs—and only after we've fixed everything we can locally" [verified]
  - "if it's good for humans, it's good for LLMs, too." [verified]
- **Maps to:** 06b, 11, 05, 14

### 44. Spotify (Max Charas and Marc Bruggmann), "Honk" background coding agent series, parts 1-3 (part 4 Apr 2026)
- **URL:**
  - https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1
  - https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2
  - https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3
- **Date:** 2025-11-06, 2025-11-24, and 2025-12-09
- **Key claims:**
  - 1,500+ merged agent PRs on top of Fleet Management. About half of Spotify's PRs had already come from Fleet Management automation since mid-2024.
  - A hand-written Maven updater had grown past 20k lines, which is what motivated using agents.
  - Agents save 60-90% of the time on migrations.
  - There are three failure modes:
    1. no PR
    2. a PR that fails CI
    3. a PR that passes CI but is wrong, the "most serious error" because it erodes trust (part 3)
- **Practical techniques:**
  - **Verifiers** auto-activate by repo contents (for example a pom.xml triggers the Maven verifier). They are exposed through one MCP "verify" tool and filter output so build noise doesn't flood the context.
  - **A Claude Code Stop hook runs all verifiers.** If any fails, no PR is opened. This is the canonical verification-loop stop condition.
  - **An LLM judge checks the diff against the prompt** to catch overreach, such as refactors or disabled flaky tests.
    - It vetoes about 25% of sessions, and about half of those recover.
    - Spotify admits it has no evals for the judge yet, a good discussion point for module 08.
  - Prompting lessons:
    - Use a handful of concrete code examples.
    - Define the end state as runnable tests.
    - Make one change per prompt.
    - Keep the toolset minimal: verify, restricted git, and allowlisted bash.
- **Quotes:**
  - "Without these feedback loops, the agents often produce code that simply doesn't work." [verified]
  - "The more tools you have, the more dimensions of unpredictability you introduce." [verified]
- **Maps to:** 06b, 08, 10, 11, 05

### 45. Shopify, Tobi Lütke memo "Reflexive AI usage is now a baseline expectation"
- **URL:** posted on X, April 2025. Coverage: https://www.digitalcommerce360.com/2025/04/08/internal-memo-shopify-ceo-declares-ai-non-optional/ [secondary]
- **Date:** 2025-04 (around Apr 7)
- **Key claims (secondary):**
  - Teams must show why a task can't be done with AI before asking for headcount.
  - AI use becomes part of performance reviews.
  - AI is framed as a "thought partner, deep researcher, critic, tutor, or pair programmer".
- **Practical techniques:** team-practice and org-culture framing for module 14. Contrast it with METR's perception gap: a mandate is not a measurement.
- **Quote:** "Reflexive AI usage is now a baseline expectation at Shopify" [secondary; verify against the memo]
- **Maps to:** 14

### 46. Jarred Sumner (Bun), "Rewriting Bun in Rust" (via Simon Willison)
- **URL:** https://bun.com/blog/bun-in-rust [secondary; from Simon's post] ; commentary: https://simonwillison.net/2026/Jul/8/rewriting-bun-in-rust/
- **Date:** around 2026-07 (Simon's post is dated 2026-07-08)
- **Key claims:**
  - Bun was ported from Zig to Rust with coordinated agent loops over about 11 days.
  - The TypeScript test suite, about a million assertions, served as a language-independent conformance oracle.
  - The work included adversarial code review.
  - Sumner fixed the generating process rather than hand-fixing output.
  - Scale: more than 1M lines added. 5.9B uncached input tokens, 690M output tokens, and 72B cached reads, about $165k at API prices [as reported by Simon].
- **Practical techniques:**
  - "Fix the loop, not the output."
  - Use a conformance test suite as the loop's verifier for ports. This pairs with Ronacher's claim that loops work well for ports.
- **Quote:** (Simon Willison) "an extremely sophisticated piece of agentic engineering" [verified on Simon's page]
- **Maps to:** 06b, 10

---

## Topics missing from draft list

1. **Harness engineering as its own discipline.** LangChain, Mitchell Hashimoto, Huntley, and Cognition all describe improving the *harness* (system prompt, tools, middleware, AGENTS.md, verifiers) rather than the model. LangChain gained 13.7 points on Terminal Bench with the model fixed. The draft scatters this across modules 05, 06b, and 11. It deserves an explicit "hill-climb the harness" lab in module 09.
2. **Backpressure / verification design.** Huntley, Spotify verifiers, Stripe's shift-left lint, and Beck's TDD prompt all treat the design of verifiers that the loop can consume as the central skill. Topics include output filtering, fast local checks, and stop hooks gated on verifiers. Module 11 mentions verifiable feedback, but it should be a first-class topic, possibly merged into module 06b.
3. **Loop budgets and economics.** Stripe caps CI at 2 rounds. repomirror ran about $10.50/hr per agent. Bun's port cost about $165k. Mitchell's feature cost $15.98. Willison runs a $5 budget org. Cost per iteration and the diminishing returns of retries belong in module 06b.
4. **Clean-context review agents / "models watching models".** Cognition's 2026 review loop (about 2 bugs per PR) and Eugene Yan's drift-checker session. The draft's module 06 multi-agent tradeoffs should cover the read-only-helper vs. parallel-writer distinction explicitly.
5. **Persistent agent memory and work tracking outside the context.** Beads, fix_plan.md, progress files, and git as the state store. Draft module 06b mentions "state outside the context", but task-graph tools (Beads, Gas Town hooks) are not named.
6. **Measuring your own productivity (METR-style).** The perception gap is a core lesson. Module 14 should have a "how to measure whether AI is helping you" segment that uses randomized task assignment and time-to-merge.
7. **Benchmark literacy and contamination.** The SWE-bench Verified retirement, scaffolding effects on scores, and why private evals matter. These belong in module 07 or 09.
8. **Cognitive debt / loss of shared understanding.** Ronacher ("loops amplify defensive code"), Florian Herrengt and Ronacher's "The Tower Keeps Rising" as linked by Simon in 2026 [secondary], and Kenton Varda banning AI-written PR descriptions [secondary]. This belongs in module 14 alongside code review at scale.
9. **Pruning instructions and skills over time.** Huntley says to delete AGENTS.md and skills every few months and re-test. Eugene says each rule should live in one place. repomirror's prompt went from 1,500 to 103 words. Treat context files as code with tests. This could go in module 03 or 05.
10. **Asynchronous / background / scheduled agents as an operating model.** Mitchell's end-of-day agents, Honk, Stripe minions, Devin scheduling Devins, and LangChain's ambient agents and Agent Inbox. Module 06b covers loops technically, but not the human workflow of inbox-style supervision.
11. **Optimizing LLM data pipelines (DocETL).** Hill-climbing applied to batch and ETL workloads is directly relevant to a distributed-systems / data-pipeline engineer. It could be an optional capstone variant.

## Points of tension or disagreement

1. **Multi-agent: con vs. pro.**
   - *Con:* Cognition 2025 ("Don't build multi-agents"; Flappy Bird). Armin says sub-agents that mix reads and writes create chaos. Spotify keeps its agent single-purpose.
   - *Pro:* Yegge's Gas Town runs 20-30 parallel agents. Bun's port used coordinated parallel agents. Huntley fans out to hundreds of subagents for reads. Willison, Mitchell, and Eugene run parallel sessions.
   - *Resolution emerging in 2026:* Cognition's own update holds that writes stay single-threaded while helpers add intelligence (review, escalation, research). Parallelism works for reads and for isolated tasks with verifiable criteria, and fails for shared-state writes. This mirrors the single-writer principle in distributed systems, a perfect analogy for this student.
2. **Ralph / long-running loops: fresh context vs. same-session.** Dex Horthy argues the official Stop-hook plugin misses the point because Ralph's value is a fresh context per unit of work. The plugin re-feeds the prompt into the same session.
3. **Do loops work for code you care about?**
   - Huntley says yes for greenfield ("nobody should type code by hand").
   - Ronacher (2026) says loops are poor for lasting code and great for ports and experiments.
   - Beck stays in the loop himself and watches for the three warning signs.
   - Mitchell rewrites much AI output by hand.
4. **Eval-driven development.**
   - Eugene Yan advocates EDD: write evals first.
   - Hamel and Shreya's FAQ says generally *don't*. Write evaluators for observed failures, except for known hard constraints.
   - Teach both and reconcile them: write constraint evals up front, and discover failure-mode evals through error analysis.
5. **METR slowdown vs. claimed speedups.**
   - METR 2025: 19% slower, with developers believing they were 20% faster.
   - Practitioner and company reports: Spotify 60-90% time savings on migrations, Stripe 1,000+ PRs/week, Mitchell faster on SwiftUI tedium, Huntley's $50k-for-$297 anecdote.
   - METR 2026: probably faster now, but they can't measure it reliably.
   - Lesson: company numbers come from *narrow, verifiable task classes* (migrations, ports, upgrades), while METR measured *general issues in mature repos by experts*. Both can be true.
6. **Vibe coding vs. engineering.**
   - Yegge and Kim embrace "vibe coding" as the umbrella term (the book's FAAFO).
   - Willison distinguishes vibe coding from vibe/agentic engineering.
   - Beck distinguishes vibe from augmented coding.
   - Mitchell says never ship without review.
   - Huntley says human review doesn't scale, so automate verification instead.
7. **Human review: necessary or a bottleneck to eliminate?**
   - Mitchell, Willison, and Stripe say every change is human-reviewed.
   - Huntley argues eyeballing never stopped bugs. Spotify auto-merges most Fleet Management PRs [secondary].
   - Cognition uses AI review agents.
   - The likely answer is a risk-tiered review policy.
8. **MCP vs. shell/code tools.**
   - Willison and Ronacher prefer shell and CLI tools ("Your MCP doesn't need 30 tools: it needs code").
   - Stripe runs a 400+ tool MCP Toolshed, but with *curated subsets* per agent.
   - Spotify keeps 3 tools.
   - Breunig shows performance degrades as tools are added.
9. **Hooks.** Ronacher found hooks useless for steering in mid-2025. Spotify, LangChain middleware, and Huntley's pre-commit diff checks make hooks and stop-gates central to verification. The difference is that blocking verification gates work, while hooks that try to steer behaviour don't.
10. **Grep vs. embeddings for code context.** Jason Liu's series (Augment, Cline) and Cognition's SWE-grep favour agentic search over vector RAG for code. Vector RAG still makes sense for document Q&A (Jason's six RAG evals).
11. **AGENTS.md and skills: help or noise?** Mitchell treats AGENTS.md as the core harness-engineering artifact. Huntley (2026) calls them probabilistic and says to test with and without, and to delete periodically. Thorsten Ball says stronger models make scaffolding noise [secondary].

## Best concrete examples to reuse in the course

1. **Build the loop in 300 lines (module 06b lab).** Thorsten Ball's three-tool Go agent and Huntley's staged workshop (chat, then read, list, bash, edit, search). Then add the stop conditions in order:
   1. max iterations
   2. a token/$ budget
   3. a consecutive-error counter, per 12-factor factor 9: break after 3 and escalate
   4. a per-file edit loop detector, per LangChain's LoopDetectionMiddleware
   5. a pre-completion verification gate, per PreCompletionChecklistMiddleware and Spotify's Stop hook
2. **The Ralph loop, live.**
   - `while :; do cat PROMPT.md | claude -p ... ; done`, with specs/, fix_plan.md, one item per loop, and commit-on-green.
   - Contrast it with the Stop-hook plugin variant, which keeps the same session.
   - Show the repomirror stats (6 repos, about 1,100 commits, under $800, prompt cut from 1,500 to 103 words, the agent that `pkill`ed itself).
   - Show Beck's three warning signs as the stuck/runaway rubric.
3. **The verification ladder (Spotify Honk).** Deterministic verifiers exposed as one tool, a Stop hook that blocks the PR, then an LLM judge on diff vs. prompt (about 25% veto rate, about half recover). Then ask: "how would you eval that judge?", a bridge to module 08.
4. **The loop budget (Stripe).** Local lint in under 5s on push, then at most 2 CI rounds, then hand to a human. Ask students to compute expected cost per PR vs. success rate per round.
5. **Critique shadowing end-to-end (module 08).** Hamel's 7 steps with a train/dev/test split. Measure TPR and TNR plus Cohen's kappa (target 0.4-0.6 or higher), and compare to human-human kappa of 0.2-0.3 (Eugene).
6. **Error bars exercise (module 09).** Eugene's numbers: 200 samples with 3% defects gives ±2.4% and can't prove a 5% SLA. 400 samples gives ±1.7%. Error scales with sqrt(n).
7. **Transition failure matrix (module 10).** From the Hamel/Shreya FAQ. Students build one for their capstone agent's states.
8. **pass@k vs pass^k (modules 07 and 10).** τ-bench: GPT-4o under 50% pass^1, and pass^8 under 25% in retail. Map it to SLOs: pass^k is your availability, pass@k is your best case.
9. **Harness hill-climb (module 09).** LangChain went from 52.8% to 66.5% on Terminal Bench with the model fixed, via trace analysis, then middleware, then the reasoning sandwich. The xhigh-everywhere result (worse, from timeouts) teaches budget trade-offs.
10. **Multi-agent decision table (module 06).** Use Cognition's Flappy Bird failure, then Cognition 2026's clean-context reviewer (about 2 bugs per PR), then Gas Town's Witness/Refinery roles. Rule: single writer, many readers.
11. **The lethal trifecta audit (module 13).** Students list their agent's tools, mark each as private data, untrusted input, or exfiltration channel, and pick one of the six design patterns to break the triangle.
12. **The METR perception gap (modules 00 and 14).** Predicted +24%, perceived +20%, measured -19%. Then the 2026 selection-effect story. Exercise: students design a personal randomized measurement.
13. **Mitchell's harness-engineering rule (module 04).** Every agent mistake becomes an AGENTS.md line or a tool. Pair it with Huntley's counterpoint to delete and re-test periodically.
14. **Research, Plan, Implement with the 40-60% context rule (modules 03 and 04).** Dex Horthy, including the parquet-java failure as the "shallow research" anti-example.
15. **Bun's Zig-to-Rust port as the capstone-scale case study.** Test suite as conformance oracle, fix the process not the output, adversarial review, and token economics.
16. **Six RAG evals as a conditional-probability grid (module 07).** Jason Liu's Q/C/A relationships, with symptom-to-eval diagnosis.

### Items needing verification before use
- The OpenAI SWE-bench Verified retirement post (403; numbers from secondary sources).
- Karpathy's exact "Iron Man suit" wording.
- The Shopify memo's exact text.
- Yegge's Medium post titles and URLs, and the FAAFO expansion.
- The DocETL repo URL.
- The 12-factor-agents first-publication date.
- The Eugene Yan "LLM patterns" date.
- Stripe minions part 2 (blueprints).
- LangChain's 2026 "Anatomy of an Agent Harness" and Deep Agents evals posts.
- The Bun blog URL.
- Kent Beck's paywalled augmented-coding follow-ups.
