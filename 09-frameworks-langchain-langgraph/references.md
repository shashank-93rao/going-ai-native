# References

Docs were checked on 2026-10-19 unless noted. Code in this module targets langgraph 1.2.16, langgraph-checkpoint 4.3.0 and langsmith 0.14.11.

## LangChain Academy (all 19 catalog items; https://academy.langchain.com/collections)

The catalog is organised as Build / Test / Deploy / Monitor (the ADLC). The LangChain Certified Agent Engineer (LCAE) prerequisite bundle is Intro to LangChain, Intro to Deep Agents, Building Reliable Agents, Intro to LangSmith Deployment and Monitoring Production Agents. Module syllabi below come from `research/curricula.md`.

| Course | What to take from it | Where in this module |
|---|---|---|
| [Introduction to LangGraph](https://academy.langchain.com/courses/intro-to-langgraph) | The core: state schema and reducers, router and agent, breakpoints, editing state, dynamic breakpoints, **time travel**, parallelization, sub-graphs, map-reduce, Store, **double texting** | 03, 04 |
| [Quickstart: LangGraph Essentials](https://academy.langchain.com/courses/langgraph-essentials-python) | Nodes, edges, conditional edges, memory, interrupt (the fast version) | 03, 04 |
| [Quickstart: LangChain Essentials](https://academy.langchain.com/courses/langchain-essentials-python) | `create_agent`, models and messages, streaming, tools, MCP tools, structured output, dynamic prompt, HITL | 02 |
| [Introduction to LangChain](https://academy.langchain.com/courses/foundation-introduction-to-langchain-python) | Module 3 is middleware: long conversations, HITL, dynamic agents | 02 |
| [Introduction to Deep Agents](https://academy.langchain.com/courses/foundation-introduction-to-deepagents) | Harness anatomy: backends, sandboxes, summarization and offload, skills, subagent teams, async subagents | 06 |
| [dcode Essentials](https://academy.langchain.com/courses/dcode-essentials) | A Deep Agents coding CLI: goals, skills, subagents | 06 (context) |
| [Project: Ambient Agents with LangGraph](https://academy.langchain.com/courses/ambient-agents) | Event-driven email assistant with evals, HITL and memory, a template for the triage agent | 06 |
| [Project: Deep Research with LangGraph](https://academy.langchain.com/courses/deep-research-with-langgraph) | Scoping, research agent, supervisor, multi-agent, evaluated in LangSmith | 03 (`Send`, subgraphs) |
| [Intro to Agent Observability & Evaluations](https://academy.langchain.com/courses/intro-to-langsmith) | Run types, datasets, evaluators, experiments, **pairwise**, **summary evaluators**, **annotation queues**, online eval, automations | 05 |
| [Quickstart: LangSmith Essentials](https://academy.langchain.com/courses/quickstart-langsmith-essentials) | Tracing, offline evals, online evaluators, queues, Insights, "closing the loop" | 05 |
| [Building Reliable Agents with LangSmith](https://academy.langchain.com/courses/building-reliable-agents) | Code-based, LLM-as-judge and pairwise evals; Insights agent; online evals | 05 |
| [Autonomous Agent Improvement with LangSmith Engine](https://academy.langchain.com/courses/langsmith-engine) | Automated find-fix-test-monitor loop; contrast it with the manual loop in Module 12 | 05 |
| [Monitoring Production Agents](https://academy.langchain.com/courses/production-monitoring) | Cost, sentiment, A/B tests, security alerts | 05, Module 15 |
| [Introduction to LangSmith Deployment](https://academy.langchain.com/courses/langsmith-deployment) | Assistants, memory in deployment, multi-tenant auth | 04 (double texting) |
| [LangSmith Fleet](https://academy.langchain.com/courses/quickstart-agent-builder) | No-code builder; ambient agents, sandboxes | 06 (context) |
| TypeScript twins of the two Essentials quickstarts, plus the LCAE Practice Exam and LCAE bundle | No distinct content beyond the above | n/a |

## LangChain / LangGraph / LangSmith docs

- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): `interrupt()`, `Command(resume=...)`, `__interrupt__`, static breakpoints "not recommended" for HITL, and resume with the same `thread_id`.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel): `InMemorySaver`, `PostgresSaver.setup()`, `get_state_history` (newest first), replay vs fork with `update_state`.
- [LangGraph memory](https://docs.langchain.com/oss/python/langgraph/add-memory): Store `put`/`search` by namespace, `runtime.store` inside nodes.
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming): stream modes, and the newer `stream_events(version="v3")`.
- [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents), [custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom), [HITL middleware](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) and [models](https://docs.langchain.com/oss/python/langchain/models): `create_agent` params, hook names, `jump_to`, decision types (approve/edit/reject/respond), `init_chat_model`.
- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview) and [subagents](https://docs.langchain.com/oss/python/deepagents/subagents): built-in tools, backends, `task`, isolated vs fork mode, and planning opt-in.
- [LangSmith: evaluate an application](https://docs.langchain.com/langsmith/evaluate-llm-application), [pairwise](https://docs.langchain.com/langsmith/evaluate-pairwise), [online evaluators](https://docs.langchain.com/langsmith/online-evaluations), [annotation queues](https://docs.langchain.com/langsmith/annotation-queues) and [trace with LangGraph](https://docs.langchain.com/langsmith/trace-with-langgraph): evaluator signatures, `randomize_order`, sampling and filters, queue types, env vars, and `@traceable` for non-LangChain code.
- [LangSmith double texting](https://docs.langchain.com/langsmith/double-texting): reject, enqueue, interrupt and rollback. A Deployment feature, "not available in the LangGraph open source framework."
- [langchain-ai/agent-inbox](https://github.com/langchain-ai/agent-inbox): the `HumanInterrupt` / `HumanResponse` schema. **Archived 2026-09-20.**

## LangChain blog posts

- Harrison Chase, ["Deep Agents"](https://www.langchain.com/blog/deep-agents) (2025-07-30): the four components, and the to-do tool as a no-op that still helps.
- Harrison Chase, ["Introducing ambient agents"](https://www.langchain.com/blog/introducing-ambient-agents) (2025-01-14): notify, question and review, and Agent Inbox.
- Vivek Trivedy, ["Improving Deep Agents with harness engineering"](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering) (2026-02-17): 52.8% to 66.5% on Terminal Bench 2.0 with the model fixed, plus the middleware that did it.
- LangChain, ["Context engineering for agents"](https://www.langchain.com/blog/context-engineering-for-agents) (2025-07-02): write / select / compress / isolate, mapped to framework features.

## Vendor SDKs and other frameworks

- Anthropic, ["Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents) (2024-12-19): the case for starting without frameworks.
- Anthropic, ["Building agents with the Claude Agent SDK"](https://claude.com/blog/building-agents-with-the-claude-agent-sdk) (2025-09-29): gather context, take action, verify.
- [Claude Agent SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python) and [hooks](https://code.claude.com/docs/en/agent-sdk/hooks): `ClaudeAgentOptions`, `@tool`, `create_sdk_mcp_server`, `can_use_tool`, and `PreToolUse` decisions (allow/deny/ask/defer).
- OpenAI Agents SDK: [running agents](https://openai.github.io/openai-agents-python/running_agents/), [HITL](https://openai.github.io/openai-agents-python/human_in_the_loop/), [guardrails](https://openai.github.io/openai-agents-python/guardrails/), [handoffs](https://openai.github.io/openai-agents-python/handoffs/) and [tracing](https://openai.github.io/openai-agents-python/tracing/).
- [CrewAI docs](https://docs.crewai.com/en/introduction) and [Flows](https://docs.crewai.com/en/concepts/flows): Crews vs Flows, `@start`/`@listen`/`@router`, `@persist`, `@human_feedback`.
- [Google ADK](https://adk.dev/) and [A2A protocol](https://a2a-protocol.org/latest/): `Agent(name, model, instruction, tools)`. A2A is complementary to MCP and governed by the Linux Foundation.
- [Pydantic AI](https://pydantic.dev/docs/ai/overview/): typed deps and outputs, and durable execution through Temporal, DBOS or Prefect.

## Courses

- Ed Donner, *AI Engineer Agentic Track* ([repo](https://github.com/ed-donner/agents)): week 4 LangGraph and Deep Agents, and week 5 "same worker, five frameworks". Syllabus taken from repo notebook headings; Udemy itself was blocked.
- DeepLearning.AI, [AI Agents in LangGraph](https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/): the "from scratch, then LangGraph" structure this module uses.
- DeepLearning.AI, [Long-Term Agentic Memory with LangGraph](https://www.deeplearning.ai/short-courses/long-term-agentic-memory-with-langgraph/): semantic, episodic and procedural memory on the Store.
