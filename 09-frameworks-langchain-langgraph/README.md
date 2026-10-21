# 09: Frameworks: LangChain, LangGraph, LangSmith and the landscape
> Build the same agent raw, in LangGraph and on a vendor SDK, prove they behave identically, and decide with evidence when a framework earns its keep.

## Why this matters

You will be asked to "just use LangChain" or "just use the Agents SDK" within a week of proposing any agent. Both sides of that argument have a point. Anthropic's "Building effective agents" warns that frameworks "hide prompts and responses and make debugging harder." Production agents also need things a 60-line loop does not have: state that survives a deploy while a human decides, replay from the middle of a run, traces that three people can search, and evals wired to experiments.

Engineers who skip the raw step cannot debug the framework. They do not know which layer wrote the system prompt, and they cannot say whether a regression came from the model, a middleware or a default that changed in a minor release. Engineers who never adopt a framework end up hand-rolling a checkpointer, usually one that re-executes the last tool call on resume.

This module takes the course stance ([`research/01-gap-analysis.md`](../research/01-gap-analysis.md)): **build it raw once to understand it, then adopt a framework for durability and tracing.** It teaches the LangChain Academy curriculum in depth (LangChain essentials, LangGraph, LangSmith, Deep Agents, ambient agents), then puts the alternatives (OpenAI Agents SDK, Claude Agent SDK, CrewAI, Google ADK and A2A, Pydantic AI) in one decision table.

The running example is an **on-call triage agent** with three tools: `get_alert`, `query_logs` and the risky `restart_service`. It is built three ways, and a test asserts that the raw and LangGraph versions send **byte-identical requests** to the model.

## The distributed-systems anchor

**Library vs framework, and buying vs building infrastructure.** A LangGraph thread is an **event-sourced aggregate**: each super-step appends a checkpoint, `interrupt()` is a saga step waiting on an external event, resume is replay from the last snapshot, and time travel is point-in-time restore into a branch. The Store is an external KV store that is *not* part of that log. LangSmith is distributed tracing plus a test-results database.

Where the analogy breaks: **a checkpoint records state, not effects.** Event sourcing assumes handlers are deterministic and side-effect free, or guarded by idempotency keys. Agent nodes call a nondeterministic model and mutate the world. LangGraph re-runs an interrupted node from its first line on resume, and re-runs any node you replay. The framework gives you the log. You still owe the idempotency.

## Learning goals
- [ ] Explain what a framework adds over a raw loop in terms of six infrastructure primitives, and decide whether a given agent needs any of them
- [ ] Build a LangGraph `StateGraph` with typed state, reducers, conditional edges, `Send` fan-out and a subgraph, and explain super-step semantics
- [ ] Add a durable human gate with `interrupt()` / `Command(resume=...)`, resume it from a fresh process, and prove with a test that no side effect ran twice
- [ ] Use `get_state_history` and `update_state` to replay and fork a run, and explain why the Store is not rolled back
- [ ] Write `create_agent` middleware (turn budget, tool retry, HITL) and explain how middleware order changes what the model sees
- [ ] Trace a non-LangChain agent with `@traceable`, run an experiment with code evaluators and a summary evaluator, and set up a pairwise comparison and an annotation queue
- [ ] Describe Deep Agents' four components as context strategies, and run an ablation that shows whether each one helps your agent
- [ ] Choose among LangGraph, the OpenAI Agents SDK, the Claude Agent SDK, CrewAI, ADK/A2A and Pydantic AI using the three questions: where is the gate, where is paused state, who sees the requests

## Reading order
1. [01-build-raw-then-adopt](01-build-raw-then-adopt.md): the course stance, what frameworks buy, and the parity test
2. [02-langchain-essentials](02-langchain-essentials.md): models, messages, tools, `create_agent`, middleware
3. [03-langgraph-core](03-langgraph-core.md): state, reducers, edges, `Send`, subgraphs, streaming
4. [04-langgraph-durability-hitl](04-langgraph-durability-hitl.md): checkpointers, threads, interrupts, time travel, Store, double texting
5. [05-langsmith-tracing-and-evals](05-langsmith-tracing-and-evals.md): tracing, datasets, evaluators, experiments, pairwise, queues, online evals
6. [06-deep-agents-and-ambient](06-deep-agents-and-ambient.md): Deep Agents harness, ambient agents, Agent Inbox
7. [07-framework-landscape](07-framework-landscape.md): OpenAI Agents SDK, Claude Agent SDK, CrewAI, ADK/A2A, Pydantic AI, and the decision table
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
- [07: Loops](../07-loops/README.md): you should have written an agent loop by hand
- [06: Agent architectures](../06-agent-architectures/README.md): workflows vs agents, the single-writer rule, durable state
- [05: Tools, MCP, skills, hooks](../05-tools-mcp-skills-hooks/README.md): tool design and hooks
- Helpful: [10: Evals fundamentals](../10-evals-fundamentals/README.md) before file 05

## Key takeaways
- Build the agent raw once (about 60 lines). Keep it and a parity test as your reference implementation and upgrade canary.
- Adopt a framework for **infrastructure**: durable state, async human approval, replay, concurrency across threads, tracing. Be wary of layers that rewrite prompts.
- A checkpoint records state, not effects. Resume re-runs the interrupted node and replay re-runs nodes. Every mutating tool needs an idempotency key that returns the **original** result.
- Put side effects in exactly one node, after the gate. Keep routers and gate nodes pure.
- Choose reducers per key on purpose. Append reducers combined with full-state returns double-count.
- The LangGraph Store is outside the checkpoint log, so forks and failed runs still write to it.
- Keep evaluators as plain functions in your repo. Run them locally in CI, and use LangSmith (or similar) for traces, side-by-side experiments, annotation queues and online evals.
- Choose a framework by three questions: where the gate sits, where paused state lives, and who can see the requests.
