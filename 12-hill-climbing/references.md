# References

Sources are grouped by what you'd use them for. "Read" dates are when this module checked the page.

## The loop

- **Lance Martin, "Automating eval design and hillclimbing with Claude"** (`/claude-api build-eval`, `/claude-api hillclimb`). claude.dev, dated 2026-09-28 on the article page (the claude.com blog listing shows 2026-10-07). https://claude.dev/blog/automating-eval-design-and-hillclimbing/ (read 2026-10-19)
  *Take:* the four properties of a good eval (production-like tasks, scales with capability and effort, headroom, low variance), the noise check before round 1, one patch per round, the keep/revert rules, stall handling by bucketing failures, "never paste failures into the prompt", and the adversarial-sampling trap. Also the worked numbers: support bot 78.6% → 90.5% held-out at about 1/5 cost; inbox router 0.681 → 0.875 with v2 reverted; skill eval 66.1% → ~88%, finished by fixing graders.
- **Andrej Karpathy, autoresearch.** https://github.com/karpathy/autoresearch (README and `program.md`, read 2026-10-19)
  *Take:* the minimal loop. A frozen `prepare.py`, a single editable `train.py`, a fixed 5-minute budget, one metric (`val_bpb`), keep or `git reset`, a `results.tsv` log, a simplicity criterion, and a human-edited `program.md`. Experiment-count figures for overnight runs circulate only in secondary sources and are not used here.
- **OpenAI cookbook, "Eval Driven System Design: From Prototype to Production"** (receipt inspection, June 2025, now archived). https://developers.openai.com/cookbook/examples/partners/eval_driven_system_design/receipt_inspection
  *Take:* a business cost model for eval errors ("not all evals matter"), and an alternative improvement order (model, prompt, examples, tools, accessory models, fine-tuning).

## Statistics

- **Anthropic, "A statistical approach to model evaluations"** (2024-11-19), and **Evan Miller, "Adding Error Bars to Evals"**, arXiv 2411.00640. https://www.anthropic.com/research/statistical-approach-to-model-evals · https://arxiv.org/abs/2411.00640 (read 2026-10-19)
  *Take:* the five recommendations (CLT/SEM, clustered SEs, within-question variance reduction, paired differences, power analysis). Clustered SEs "can be over three times as large as naive standard errors"; question-score correlation between frontier models of 0.3 to 0.7. The formulas in `stats.py` follow this paper.
- **Eugene Yan, "Product Evals in Three Simple Steps"** (2025-11-23). https://eugeneyan.com/writing/product-evals/ (read 2026-10-19)
  *Take:* 200 samples at 3% defects gives roughly ±2.4%, which cannot prove a 5% requirement; 400 gives ±1.7%; halving the margin needs 4x the samples. The 75/25 dev/test split and one evaluator per dimension.
- **Anthropic, "Quantifying infrastructure noise in agentic coding evals"** (Gian Segato, 2026-02-05). https://www.anthropic.com/engineering/infrastructure-noise (read 2026-10-19)
  *Take:* a 6-point Terminal-Bench 2.0 swing from infrastructure alone (p < 0.01); infra errors 5.8% → 0.5%; about 3x resource headroom; skepticism for leaderboard gaps under 3 points; time-of-day effects (anecdotal, unquantified).

## Overfitting, integrity, reward hacking

- **Anthropic, "Demystifying evals for AI agents"** (2026-01-09). https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  *Take:* pass@k vs pass^k (75% per trial gives pass^3 ≈ 42%), capability vs regression evals, a clean environment per trial (the git-history leak), grading outcomes rather than paths.
- **Anthropic, "Eval awareness in Claude Opus 4.6's BrowseComp performance"** (2026-03-06). https://www.anthropic.com/engineering/eval-awareness-browsecomp
  *Take:* in 2 of 1,266 problems the model identified the benchmark and decrypted its answer key. Treat eval integrity as an ongoing adversarial problem.
- **Anthropic, "From shortcuts to sabotage: natural emergent misalignment from reward hacking"** (2025-11-21). https://www.anthropic.com/research/emergent-misalignment-reward-hacking
  *Take:* reward hacking (for example `sys.exit(0)` to fake passing tests) generalized to broader misbehavior in RL training. Build graders that can't be short-circuited.
- **Goodhart's law.** Charles Goodhart's 1975 remark on monetary targets, usually quoted in Marilyn Strathern's later paraphrase ("when a measure becomes a target..."). Cited here as a concept, not a quotation.

## What to climb, cost, upgrades

- **Hamel Husain & Shreya Shankar, "AI Evals for Engineers & PMs"** (Maven; syllabus via the course page). https://maven.com/parlance-labs/evals
  *Take:* L5 train/dev/test and "freeze-and-read-test-once"; L6 tiered CI (deterministic, mocked, full) and a GitHub Actions gate; L8 the accuracy-vs-cost frontier, fixing at the cheapest layer (prompt → tool design → harness → model/weights), a manual loop before GEPA or a bounded improve-loop, reward-hacking guards; L9 cost profiling and the model-upgrade drill. Summarized from the public syllabus; the lectures themselves were not reviewed for this module.
- **Vivek Trivedy (LangChain), "Improving Deep Agents with harness engineering"** (2026-02-17). https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering
  *Take:* 52.8% → 66.5% on Terminal-Bench 2.0 by harness changes alone, model fixed; xhigh everywhere scored worse than the "reasoning sandwich" (53.9% vs 63.6%) because of timeouts.
- **Anthropic, "An update on recent Claude Code quality reports"** (April 23, 2026 postmortem). https://www.anthropic.com/engineering/april-23-postmortem
  *Take:* a diffuse regression from three changes (effort default lowered, a thinking-history bug, a verbosity line costing about 3%); broad per-model evals plus line-by-line ablations for system-prompt changes.
- **Anthropic, "Prompting Claude Opus 5"** (living doc). https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
  *Take:* effort as the primary cost lever; re-run effort sweeps on model change; explicit verification instructions cause over-verification on that model. The harness-decay argument behind the upgrade drill.
- **Anthropic customer story, "How Block orchestrates Claude Fable across thousands of pull requests"** (2026-10-08). https://claude.com/resources/articles/how-block-orchestrates-claude-fable-across-thousands-of-pull-requests
  *Take:* benchmark every model at every effort level per use case.
- **Claude API effort and model facts** (`output_config.effort` levels low/medium/high/xhigh/max, per-model defaults, list prices): from the claude-api skill's model table cached 2026-10-06. Re-check the live docs and pricing page before relying on them.

## Automated optimization

- **Agrawal et al., "GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning"**, arXiv 2507.19457 (v1 July 2025, v2 Feb 2026). https://arxiv.org/abs/2507.19457 (abstract read 2026-10-19)
  *Take:* reflection on trajectories plus a Pareto frontier of candidates; +6% on average (up to +20%) over GRPO with up to 35x fewer rollouts; over +10% vs MIPROv2.
- **DSPy GEPA overview.** https://dspy.ai/current/api/optimizers/GEPA/overview/ (read 2026-10-19)
  *Take:* the metric contract (score plus textual feedback; signature `(gold, pred, trace, pred_name, pred_trace)`), `compile(student, trainset=..., valset=...)`. Full constructor arguments are on the "GEPA Advanced" page, which was not reviewed.

## Reliability targets

- **Dwarkesh Patel, interview with Andrej Karpathy, "AGI is still a decade away"** (2025-10-17). https://www.dwarkesh.com/p/andrej-karpathy
  *Take:* the march of nines ("Every single nine is a constant amount of work"; 90% "is just the first nine") and the demo-to-product gap.

## Cross-links in this course
- [Module 10: Evals fundamentals](../10-evals-fundamentals/README.md): error analysis, graders, abstention-aware scoring.
- [Module 11: LLM-as-judge](../11-llm-as-judge/README.md): calibrate judges before you climb on them.
- [Module 07: Loops](../07-loops/README.md): governors and budgets for automated climbs.
- [Module 08: Harness engineering](../08-harness-engineering/README.md): harness changes as a climbable surface; harness decay.
- [Module 13: Testing agentic systems](../13-testing-agentic-systems/README.md): infrastructure noise vs model failure; record and replay.
- [Module 15: Observability & production](../15-observability-and-production/README.md): prompt changes as deploys, canaries, online evals.
- [Module 16: Security & containment](../16-security-and-containment/README.md): sandboxing an optimizer agent.
