# 99: Capstone
> Take one AI system from "it works on my laptop" to "I can show you the error bars, the guardrails, and the rollout plan", using every tool in this course on a single artifact.

## Why this matters
Each module before this one taught a check in isolation: a judge here, a governor there, a CI gate somewhere else. Real systems fail at the seams between them. A judge calibrated on one distribution drifts when the agent's prompt changes. A hill-climb that moves the pass rate by 4 points means nothing if the noise floor is 6. A guardrail that blocks prompt injection also blocks the legitimate remediation it looks like. You only meet these interactions when you run the whole loop on one system and own the result.

The capstone is that loop. You build a system, make it checkable, use the checks to improve it, and then decide whether it has earned more autonomy. The deliverable is not "an agent that works". It is an **evidence pack**: the specs, traces, eval suite, experiment log and readiness review that would let a skeptical senior engineer sign off on giving it the pager, or on putting it in the nightly batch.

There are two variants. Do one, or do both. The second one goes faster because the eval and statistics machinery carries over.

| | **A: On-call ops agent** | **B: LLM data pipeline** |
|---|---|---|
| What you build | A tool-using agent that diagnoses and remediates incidents in a deterministic simulated backend | A DocETL-style map/reduce pipeline that extracts structured incident facts from postmortem documents |
| Oracle | World state of the simulator (is it healthy?), plus the action log | Gold labels per field, plus a calibrated judge for free text |
| Autonomy question | When may it mutate production without a human? | When may it run nightly and feed a dashboard without review? |
| Hardest part | Safety: dangerous actions, prompt injection, false alarms | Measurement: label definitions, precision vs recall, cost frontier |
| Milestones | [8](A-ops-agent/README.md) | [6](B-llm-pipeline/README.md) |
| Time | 3–4 weekends | 2–3 weekends |

## The distributed-systems anchor
Variant A is a **production readiness review for a new on-call engineer who happens to be a model**. You would not give a new hire root on day one. You give them read access, shadow shifts, a runbook, and a narrow set of pre-approved actions, then widen the set as their track record grows. The capstone does the same thing with numbers: pass rate with a CI, pass^k as the consistency SLO, a dangerous-action rate that must be zero, and a staged rollout from shadow mode to auto-remediation.

Variant B is **a data pipeline with a fuzzy transform**. You already know how to test a deterministic ETL job: fixtures, row-level diffs, data-quality checks. Here the transform is a model call, so "correct" becomes a per-field precision/recall measurement on a labeled sample, and "regression" becomes a paired statistical comparison. DocETL treats this as query optimization: rewrite the plan into equivalent forms and search the accuracy/cost space ([DocETL, VLDB 2025](https://arxiv.org/abs/2410.12189)).

Where the analogies break: a new hire does not get *worse* when you rephrase the runbook, and a SQL optimizer's rewrites are provably equivalent. Here, every prompt edit is a behavior change that you have to measure, and every "equivalent" rewrite is only equivalent up to your eval's resolution.

## Learning goals
- [ ] Write a spec, an AGENTS.md and an invariants file that make the system's correctness conditions explicit before any model call.
- [ ] Instrument every run with spans and do error analysis on at least 50 traces, producing a failure taxonomy with counts.
- [ ] Build an eval suite with code graders for objective checks and a judge calibrated to stated TPR/TNR on held-out human labels.
- [ ] Run a noise check, then hill-climb with a train/test split, paired comparisons and an experiment log with keep/revert decisions.
- [ ] (A) Ship guardrails that drive dangerous-action and injection-success rates to zero on a regression suite, without blocking legitimate fixes.
- [ ] (A) Run the agent as a scheduled loop with an inbox, idempotent actions and budgets.
- [ ] (B) Map the accuracy/cost frontier across prompt decomposition, chunking and model/effort, and gate CI on it.
- [ ] Write a readiness review that states what autonomy the system has earned and what evidence supports it.

## Reading order
1. [rubric.md](rubric.md): grading levels for every milestone. Read it first so you know what "done" looks like.
2. [A-ops-agent/README.md](A-ops-agent/README.md): variant A overview, then [M1](A-ops-agent/M1-spec-and-harness.md) through [M8](A-ops-agent/M8-production-readiness.md).
3. [B-llm-pipeline/README.md](B-llm-pipeline/README.md): variant B overview, then [M1](B-llm-pipeline/M1-pipeline-v0.md) through [M6](B-llm-pipeline/M6-ci-gate-and-drift.md).
4. [code/README.md](code/README.md): the starter scaffolds, what each file does, how to run them offline.
- [references.md](references.md)

## How the capstone exercises every module
Each row says where the module's skill shows up as a graded deliverable. If you skipped a module, the milestone is the place you will notice.

| Module | Variant A (ops agent) | Variant B (pipeline) |
|---|---|---|
| [00-orientation](../00-orientation/README.md) | M1: state the verifiability argument for each action class; M8: the autonomy decision | M1: which fields are verifiable by code vs judge |
| [01-llms-for-systems-engineers](../01-llms-for-systems-engineers/README.md) | M2: token budgets, `max_tokens` stops; M5: effort as a dimension | M4: context length vs accuracy on long docs; temperature 0 is not determinism |
| [02-prompting-as-specification](../02-prompting-as-specification/README.md) | M1/M2: the system prompt as a versioned spec; M5: prompt changes logged as deploys | M1/M4: extraction prompt with field definitions; prompt decomposition |
| [03-context-engineering](../03-context-engineering/README.md) | M2: what tool results go back in context; truncating logs | M4: chunking and context minimization |
| [04-agentic-coding-workflows](../04-agentic-coding-workflows/README.md) | All: you build the capstone with a coding agent, spec-first | All: same |
| [05-tools-mcp-skills-hooks](../05-tools-mcp-skills-hooks/README.md) | M2: tool design, error messages; M6: hooks | M6: CI hook |
| [06-agent-architectures](../06-agent-architectures/README.md) | M2: single writer; M6: plan-then-execute / dual-LLM for injection | M1: workflow, not agent; map/reduce/resolve operators |
| [07-loops](../07-loops/README.md) | M2: the loop and governors; M7: scheduled loop with inbox | M6: nightly run with bookmarks |
| [08-harness-engineering](../08-harness-engineering/README.md) | M1: AGENTS.md, invariants, runbooks; autonomy rate | M1: labeling guide as the system of record |
| [09-frameworks-langchain-langgraph](../09-frameworks-langchain-langgraph/README.md) | Stretch: port M2 to LangGraph with checkpoints and interrupts | Stretch: compare against DocETL itself |
| [10-evals-fundamentals](../10-evals-fundamentals/README.md) | M3: traces and error analysis; M4: code graders, pass^k, abstention | M2: labels and field-level P/R; M3: error analysis |
| [11-llm-as-judge](../11-llm-as-judge/README.md) | M4: judge for the incident summary, TPR/TNR | M5: judge for summary and action items |
| [12-hill-climbing](../12-hill-climbing/README.md) | M5: noise check, paired tests, revert rules | M4: hill-climb and cost frontier |
| [13-testing-agentic-systems](../13-testing-agentic-systems/README.md) | M3/M4: deterministic sim, trajectory checks, transition matrix | M2: property tests on the scorer |
| [14-steering-and-guardrails](../14-steering-and-guardrails/README.md) | M6: blocking gates, validators, HITL | M4: structured output and validators |
| [15-observability-and-production](../15-observability-and-production/README.md) | M8: SLIs, canary, rollback | M6: drift monitoring, cost budget |
| [16-security-and-containment](../16-security-and-containment/README.md) | M6: lethal-trifecta audit, injection suite, containment | M3: postmortems are untrusted input too |
| [17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md) | M8: review policy, who owns the pager | M6: who reviews pipeline changes |
| [99-capstone](README.md) | You are here | You are here |


## Code to reuse, by milestone
The capstone scaffold is in [code/](code/). These files from earlier modules are the pieces to lift. Copy them in or import them; don't rebuild them.

| Milestone | Reuse | What it gives you |
|---|---|---|
| A-M1 | [08 sample_service docs](../08-harness-engineering/code/sample_service/AGENTS.md), [INVARIANTS.md](../08-harness-engineering/code/sample_service/INVARIANTS.md), [lint_invariants.py](../08-harness-engineering/code/sample_service/tools/lint_invariants.py) | Templates for AGENTS.md and invariants, and a lint whose errors say how to fix the problem |
| A-M2 | [07 agent_loop.py](../07-loops/code/agent_loop.py), [governor.py](../07-loops/code/governor.py) | Agent loop with governors, stall detection, typed exit codes |
| A-M2 | [05 tool_formatter.py](../05-tools-mcp-skills-hooks/code/tool_formatter.py), [ops_tools.py](../05-tools-mcp-skills-hooks/code/ops_tools.py) | Token-efficient tool responses and actionable errors |
| A-M3 / B-M3 | [10 error_analysis.py](../10-evals-fundamentals/code/error_analysis.py), [shared Tracer](../shared/ainative_kit/tracing.py) | Trace sampling, labeling CSV, axial codes, transition matrix |
| A-M4 / B-M2 | [10 eval_harness.py](../10-evals-fundamentals/code/eval_harness.py), [graders.py](../10-evals-fundamentals/code/graders.py), [13 trajectory_checks.py](../13-testing-agentic-systems/code/trajectory_checks.py), [13 flaky.py](../13-testing-agentic-systems/code/flaky.py) | Dataset runner, pass@k / pass^k, trajectory assertions, infrastructure noise separated from model failures |
| A-M4 / B-M5 | [11 judge.py](../11-llm-as-judge/code/judge.py), [calibrate.py](../11-llm-as-judge/code/calibrate.py) | Binary judge, and its calibration: TPR/TNR and the corrected pass rate |
| A-M5 / B-M4 | [12 stats.py](../12-hill-climbing/code/stats.py), [hillclimb.py](../12-hill-climbing/code/hillclimb.py), [noise_check.py](../12-hill-climbing/code/noise_check.py), [pareto.py](../12-hill-climbing/code/pareto.py) | Clustered SEs, paired tests, keep/revert runner, cost frontier |
| A-M6 | [14 stop_gate.py](../14-steering-and-guardrails/code/hooks/stop_gate.py), [pre_tool_guard.py](../14-steering-and-guardrails/code/hooks/pre_tool_guard.py), [16 injection_suite/](../16-security-and-containment/code/injection_suite/), [egress_proxy_policy.py](../16-security-and-containment/code/egress_proxy_policy.py), [trifecta_audit.py](../16-security-and-containment/code/trifecta_audit.py) | Gates, guards, an injection regression suite, egress policy |
| A-M7 | [07 ralph.py](../07-loops/code/ralph.py), [06 run_log.py](../06-agent-architectures/code/run_log.py) | Fresh-context loop driver, event-sourced resumable runs |
| A-M8 / B-M6 | [15 online_eval.py](../15-observability-and-production/code/online_eval.py), [canary.py](../15-observability-and-production/code/canary.py), [router.py](../15-observability-and-production/code/router.py), [12 ci_gate.py](../12-hill-climbing/code/ci_gate.py) | Online SLIs, canary analysis, budgeted routing, CI eval gate |
| B-M1 | [03 context_budget.py](../03-context-engineering/code/context_budget.py), [02 prompt_registry.py](../02-prompting-as-specification/code/prompt_registry.py) | Prompt assembly under a token budget; versioned prompts |

## Prerequisites
The core track at minimum: [00](../00-orientation/README.md), [01](../01-llms-for-systems-engineers/README.md), [04](../04-agentic-coding-workflows/README.md), [07](../07-loops/README.md), [10](../10-evals-fundamentals/README.md), [11](../11-llm-as-judge/README.md), [12](../12-hill-climbing/README.md), [13](../13-testing-agentic-systems/README.md), [14](../14-steering-and-guardrails/README.md). Variant A also leans on [16](../16-security-and-containment/README.md); variant B on [03](../03-context-engineering/README.md).

You need an `ANTHROPIC_API_KEY` from M3 onward (A) or M2 onward (B). M1–M2 run fully offline. Budget: the course has no verified per-run price for you, so measure it. Both scaffolds log token counts, and M5/M4 ask you to turn them into a cost per run.

## Ground rules
1. **Grade outcomes, not claims.** The ops grader reads the simulator's state, never the agent's summary. The pipeline scorer reads fields, never the model's confidence. Keep it that way when you extend them ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).
2. **The agent never edits its own grader.** Keep `grade.py`, `score.py`, labels and the test split in a directory the coding agent you build with cannot write to, or review every diff there by hand.
3. **Every claimed improvement has a CI.** "It feels better" is not a milestone result.
4. **Synthetic is a starting point, not the finish.** The simulator and the postmortems are synthetic so you can start offline. Add at least a few real or realistic cases from your own work before M8/M6; the rubric rewards it.

## Key takeaways
- The capstone deliverable is an evidence pack (spec, traces, evals, experiment log, readiness review), not a demo.
- Build the oracle before the agent: a deterministic simulator or a labeled set, plus graders that you have shown can fail.
- Error analysis on real traces decides what to build next; the taxonomy's counts set the order.
- No improvement without a noise check, a paired comparison and a held-out split. Train up and test flat means revert.
- Safety properties (no dangerous action, injection not followed) are zero-tolerance checks, separate from the quality score.
- Autonomy is granted per action class, in stages, backed by numbers: shadow, suggest, auto-with-approval, auto.
- For pipelines, the label definitions are the spec. Most "model errors" in the first round are spec gaps.
