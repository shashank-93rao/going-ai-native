# References

## Core
- **Yao et al., "τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains"** (2024). https://arxiv.org/abs/2406.12045
  Take: the template for simulated user + domain tools + policy, graded by final database state against an annotated goal. It introduces pass^k ("reliability of agent behavior over multiple trials"). GPT-4o succeeded on under 50% of tasks, and pass^8 was under 25% in retail.
- **tau-bench user simulator source**. https://github.com/sierra-research/tau-bench/blob/main/tau_bench/envs/user.py
  Take: the simulator's rules (one line at a time, don't give away the whole instruction, don't hallucinate, emit `###STOP###` when satisfied) and its strategies (`llm`, `react`, `verify`, `reflection`). `user_sim.py` follows its stop-sentinel convention.
- **Barres et al., "τ²-bench"** (2025). https://arxiv.org/abs/2506.07982 (HTML: https://arxiv.org/html/2506.07982)
  Take: dual-control environments where the user also has tools, and the performance drop when agents must guide a user. §4.3 / Table 2 quantifies user-simulator errors: airline 47/100 conversations (13 critical), retail 20/50 (6), telecom 8/50 (3). Note: the Table 2 caption says telecom had no critical errors, which contradicts the table. We cite the table.
- **Anthropic, "Demystifying evals for AI agents"** (2026-01-09). https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  Take: outcome = the environment's final state. "Grade what the agent produced, not the path it took." The pass^k arithmetic (75% → pass^3 ≈ 42%). Isolated per-trial environments (Claude once read git history left by earlier trials). Grader bugs (CORE-Bench 42% → 95%).
- **Anthropic, "Quantifying infrastructure noise in agentic coding evals"** (2026-02-05). https://www.anthropic.com/engineering/infrastructure-noise
  Take: a 6-point swing on Terminal-Bench 2.0 from infra config alone. Infra errors 5.8% at strict 1x vs 0.5% uncapped. A guaranteed allocation plus a separate kill threshold. Distrust gaps under ~3 points without matched configs. Run at different times of day.
- **OpenAI, "Testing Agent Skills Systematically with Evals"** (Kundel & Chua, 2026-01-22). https://developers.openai.com/blog/eval-skills
  Take: `codex exec --json` traces plus deterministic checks (e.g. "did `npm install` run"). A CSV with `id,should_trigger,prompt` and negative controls. A second read-only `codex exec --output-schema` run for rubric grading (`overall_pass`, `score`, `checks`). Outcome, process, style and efficiency goals.
- **Codex non-interactive mode docs**. https://developers.openai.com/codex/noninteractive (redirected to https://learn.chatgpt.com/docs/non-interactive-mode when checked on 2026-10-19)
  Take: the JSONL event types (`thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.*`, `error`) and sample `command_execution` / `agent_message` items. The traces in `code/data/` are hand-written in this shape. Fields such as an exit code were not confirmed on that page, so `codex_trace.py` doesn't rely on them.
- **Hamel Husain & Shreya Shankar, "AI Evals: Everything You Need to Know" (FAQ)**. https://hamel.dev/blog/posts/evals-faq/
  Take: the transition failure matrix (rows are the last successful state, columns the first failure; a text-to-SQL example with 12 vs 2 failures), two-phase agent evaluation (end-to-end, then step-level), and CI vs production eval sets.
- **FoundationDB, "Simulation and Testing"**. https://apple.github.io/foundationdb/testing.html
  Take: deterministic simulation of a whole cluster in one single-threaded process. Simulated machines, disks and network. Swizzle-clogging. Tens of thousands of simulations nightly, and an estimated trillion CPU-hours. The model for `world.py`.

## Practitioners and company practice
- **Geoffrey Huntley, "nobody should type code by hand anymore. here's what's left."** (2026-10-13). https://ghuntley.com/agency/
  Take: property-based tests for invariants ("charged only once") with Hypothesis under fault injection, as backpressure for agent-written systems.
- **Simon Willison, "Designing agentic loops"** (2025-09-30). https://simonwillison.net/2025/Sep/30/designing-agentic-loops/
  Take: sandbox YOLO runs (Docker, Apple `container`, Codespaces). Restrict files, secrets and network. Scoped staging credentials with hard budgets.
- **Anthropic, "Beyond permission prompts: Claude Code sandboxing"**. https://www.anthropic.com/engineering/claude-code-sandboxing
  Take: 84% fewer permission prompts. Credentials outside the sandbox, with a proxy that checks the push target.
- **Stripe, "Minions: Stripe's one-shot, end-to-end coding agents"** (2026-02-09). https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
  Take: isolated, pre-warmed devboxes cut off from prod and the internet, which is what makes prompt-free parallel runs safe.
- **Spotify, "Feedback loops for background coding agents (Honk part 3)"** (2025-12-09). https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3
  Take: an LLM judge on the diff vs the prompt catches overreach such as disabled flaky tests. Spotify notes it had no evals for that judge yet, which is a "test the tests" gap.
- **OpenAI, "Introducing upgrades to Codex"**. https://openai.com/index/introducing-upgrades-to-codex/
  Take: sandbox defaults of workspace-only writes and network off, motivated by prompt-injection risk.
- **OpenAI prompt guidance (GPT-5.5/GPT-6 family)**. https://developers.openai.com/api/docs/guides/prompt-guidance
  Take: the warning that recent models over-test, and the guidance not to write tests that mirror the implementation for low-impact changes. Paraphrased here; the page is undated and changes often.
- **Claude blog, "Automating eval design and hillclimbing with Claude"** (Lance Martin; dated 2026-09-28 on the page, 2026-10-07 in the listing). https://claude.dev/blog/automating-eval-design-and-hillclimbing/
  Take: run the grader twice and compare verdicts, check the plumbing, and note that a late gain came from fixing broken graders.

## Tools
- **Hypothesis** (property-based testing for Python). https://hypothesis.readthedocs.io/
  Take: `@given`, `settings(derandomize=True, database=None)` for reproducible CI, `find()` for bug hunting, and `@example` to pin found counterexamples.
- **Mutation testing tools**: mutmut (https://github.com/boxed/mutmut), cosmic-ray (https://github.com/sixty-north/cosmic-ray), PIT for the JVM (https://pitest.org/).
  Take: production-grade versions of `mutation_demo.py`. Point them at your graders and check functions first.
- **Jepsen**. https://jepsen.io/
  Take: the mental model of generating histories under faults and checking them against a model, which `world.violations()` borrows.

## Related modules
- [10-evals-fundamentals](../10-evals-fundamentals/README.md): error analysis, traces, pass@k vs pass^k basics
- [11-llm-as-judge](../11-llm-as-judge/README.md): calibrating the rubric grader you would add on top of scripted checks
- [12-hill-climbing](../12-hill-climbing/README.md): paired tests, power, and noise checks before you compare variants
- [14-steering-and-guardrails](../14-steering-and-guardrails/README.md): turning trajectory invariants into blocking gates at runtime
- [16-security-and-containment](../16-security-and-containment/README.md): sandboxes, egress, and credential proxies in depth
