# Draft topic list (Phase A2)

Starting list before research. Will be revised in 02-final-topics.md.

| # | Module | Core question it answers |
|---|---|---|
| 00 | Orientation: what "AI-native" actually means | What changes in the job, and what doesn't (Software 3.0, vibe coding vs. agentic engineering) |
| 01 | LLMs for systems engineers | Tokens, context windows, sampling, reasoning models, cost and latency, failure modes. Treat the model as a nondeterministic, unreliable component |
| 02 | Prompting as specification | Prompts as versioned code: structure, examples, system prompts, ambiguity removal |
| 03 | Context engineering | What goes into the window and why: retrieval, memory, compaction, CLAUDE.md, context rot |
| 04 | Agentic coding workflows | Claude Code/Codex in practice: explore→plan→code→verify, TDD with agents, parallel agents and worktrees, reviewing AI code, knowing when not to use an agent |
| 05 | Tools, MCP, skills, hooks | Designing the agent–computer interface |
| 06 | Building agents | Workflows vs. agents, the augmented LLM, chaining, routing, orchestrator-workers, evaluator-optimizer, multi-agent tradeoffs |
| 06b | **Loops** | The loop is the core primitive of agents. Covers the agent loop internals (model → tool → observe → repeat), stop conditions and budgets, self-correcting generate→verify→fix loops, long-running autonomous loops ("Ralph"-style while-loops, Claude Code `/loop`, scheduled agents), keeping state outside the context across iterations, and detecting stuck or runaway loops. Analogy: control loops / reconcilers in Kubernetes |
| 06c | **Frameworks: LangChain / LangGraph / LangSmith** | When a framework helps and when the raw SDK is better. Covers the LangGraph state graph, checkpointing and persistence, human-in-the-loop interrupts, LangSmith tracing and evals, and deep agents. The same example agent is built with the raw SDK and with LangGraph |
| 07 | Evals fundamentals | Error analysis, golden datasets, code-graded / model-graded / human grading, pass@k vs pass^k |
| 08 | LLM-as-judge | Rubrics, calibrating against humans, judge biases, judge drift |
| 09 | Hill-climbing | The eval-driven dev loop, regression suites, error bars and significance, overfitting to evals |
| 10 | Testing agentic systems | Trajectory evals, simulated users, sandboxed environments, record/replay, flakiness under nondeterminism, property-based tests |
| 11 | Steering & guardrails | Verifiable feedback loops, structured outputs, validators, retries, hooks, human-in-the-loop, recovering a run that is drifting |
| 12 | Observability & production | Tracing, online evals, drift, caching, rate limits, cost and latency budgets, model routing |
| 13 | Security & failure modes | Prompt injection, the "lethal trifecta", reward hacking, sycophancy, hallucination containment |
| 14 | The AI-native engineer & team | Specs as source, code review at scale, team practices, career positioning |
| 99 | Capstone | Build an agent, write its eval suite, hill-climb it, and ship it with guardrails and tracing |
