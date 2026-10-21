# References

The capstone reuses sources from every module. These are the ones the milestones cite directly, with what to take from each.

## Evals, judges and statistics
- [Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (2026-01-09). Grade outcomes (environment state), not paths or claims; capability vs regression suites; pass@k vs pass^k (75% per trial gives pass^3 ≈ 42%); "0% pass@100 is most often a signal of a broken task"; the CORE-Bench 42% to 95% grader-bug story. Used in A-M1, A-M3, A-M4, B-M3.
- [Anthropic, "Automating eval design and hillclimbing with Claude"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) (Lance Martin; the article page and the blog listing show different dates, 2026-09-28 and 2026-10-07). Headroom, noise check before round 1, train/test split, keep/revert rules, the reverted worked-examples variant, "never paste failures into the prompt", adversarial-sampling trap. Used in A-M4, A-M5, B-M4.
- [Evan Miller / Anthropic, "A statistical approach to model evaluations"](https://www.anthropic.com/research/statistical-approach-to-model-evals) (2024-11-19; arXiv 2411.00640). Clustered SEs, paired differences, power analysis. `grade.clustered_se` implements the clustered formula. Used in A-M5.
- [Anthropic, "Quantifying infrastructure noise in agentic coding evals"](https://www.anthropic.com/engineering/infrastructure-noise) (2026-02-05). A 6-point swing from infrastructure configuration alone; why the noise check matters. Used in A-M5.
- [Hamel Husain and Shreya Shankar, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/). Error analysis before evaluators; open and axial coding. Used in A-M3.
- [Hamel Husain, "Using LLM-as-a-judge"](https://hamel.dev/blog/posts/llm-judge/). Binary rubrics, critique shadowing, TPR/TNR. Used in A-M4, B-M5.
- [Shankar et al., "Who Validates the Validators?"](https://arxiv.org/abs/2404.12272) (UIST 2024). Criteria drift; the evaluator needs its own test set. Used in A-M4, B-M1, B-M5.
- [Eugene Yan, "Product evals"](https://eugeneyan.com/writing/product-evals/). Sample-size intuition (the ±2.4% / ±1.7% example at 200 / 400 samples), cited via the course research notes. Used in B-M2.

## Loops, scheduled agents, inbox
- [Anthropic, "Building effective agent automations"](https://claude.dev/blog/building-effective-agent-automations/) (2026-10-08). Bookmarks not time windows, ledgers with stable ids, idempotency and "maybe posted", unreadable is not quiet, budgets at 3–5x a normal run, "assert it or drop it". Used in A-M7.
- [Harrison Chase, "Introducing ambient agents"](https://www.langchain.com/blog/introducing-ambient-agents) (2025-01-14). Notify / question / review; the agent inbox. Used in A-M7.
- [Claude Code scheduled tasks docs](https://code.claude.com/docs/en/scheduled-tasks) (living doc, read 2026-10-19 by the research pass). `/loop`, desktop tasks, routines; 7-day expiry of recurring tasks. Used in A-M7.
- [Claude Code hooks guide](https://code.claude.com/docs/en/hooks-guide) (living doc). `PreToolUse` blocking with exit 2; Stop-hook loop guard. Used in A-M6.

## Security and containment
- [Simon Willison, "The lethal trifecta for AI agents"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) and ["Design patterns for securing LLM agents against prompt injections"](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/) (June 2025). The audit table and the structural defenses (plan-then-execute, dual LLM, context minimization). Used in A-M6.
- [Anthropic, "How we contain Claude across products"](https://www.anthropic.com/engineering/how-we-contain-claude) (2026-05-25). Risk = likelihood × blast radius; containment over filtering. Used in A-M6.
- [Anthropic, "How we built Claude Code auto mode"](https://www.anthropic.com/engineering/claude-code-auto-mode) (2026-03-25). Reasoning-blind action classifier; FPR/FNR reporting. Used in A-M6.

## LLM data pipelines
- [DocETL repository](https://github.com/ucbepic/docetl) (fetched 2026-10-19). Operators (map, reduce, filter, resolve, split, gather, extract and others); the optimizer swaps models, rewrites prompts, decomposes operations and replaces parts with code. Used in B README and B-M4.
- [Shankar et al., "DocETL: Agentic Query Rewriting and Evaluation for Complex Document Processing"](https://arxiv.org/abs/2410.12189) (VLDB 2025, as listed on the repo).
- ["Multi-Objective Agentic Rewrites for Unstructured Data Processing"](https://arxiv.org/abs/2512.02289) (listed on the DocETL repo as VLDB 2026). The cost-accuracy optimizer.

## Course modules most used
[07-loops](../07-loops/README.md), [10-evals-fundamentals](../10-evals-fundamentals/README.md), [11-llm-as-judge](../11-llm-as-judge/README.md), [12-hill-climbing](../12-hill-climbing/README.md), [13-testing-agentic-systems](../13-testing-agentic-systems/README.md), [14-steering-and-guardrails](../14-steering-and-guardrails/README.md), [16-security-and-containment](../16-security-and-containment/README.md).
