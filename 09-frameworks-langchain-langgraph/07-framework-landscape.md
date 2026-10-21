# 07: The framework landscape and how to choose

## The idea

Every agent framework implements the same loop: call the model, classify the result, execute tools, append, repeat. They differ in **what they let you own** and **what they own for you**. Three questions separate them better than any feature list:

1. **Where does the approval gate sit?** In your code (a graph node), in a tool property (`needs_approval`), or in a permission system you configure (hooks, allow rules)?
2. **Where does paused state live?** A checkpointer you choose, a session log the SDK writes, a state blob you serialise, or a durable-execution engine (Temporal, DBOS)?
3. **Who can see the requests?** Can you assert exactly what was sent to the model, or does the framework assemble the prompt?

The answers for the triage agent are in [`code/agents_sdk_sketch.md`](code/agents_sdk_sketch.md). This file generalises them.

## Why it matters

Ed Donner's Agentic Track builds "the same worker five times" across Google ADK with A2A, Strands with Pydantic AI, Microsoft Agent Framework with Agno, and Mastra (see `research/curricula.md` 2b). The lesson from that exercise is the one this module's parity test makes in code: **the loop is a commodity, and the infrastructure around it is not.** Teams that pick on features ("it has multi-agent!") later discover that the parts they need (durable pause, replay, an exportable trace, a gate the model cannot route around) differ a lot between frameworks.

Lock-in is real, but it is not where people expect. Swapping the model is easy in all of them. Swapping the **state format** (checkpoints, sessions, `RunState`) and the **trace format** is hard, and that is what your incident tooling and evals end up depending on.

## How it works: the frameworks

### LangGraph (+ LangChain, Deep Agents, LangSmith)
You own the graph: nodes, edges and reducers. Durability comes from pluggable checkpointers. HITL is `interrupt()` and `Command(resume=...)`. Time travel and a cross-thread Store are first-class. LangChain's `create_agent` and Deep Agents are prebuilt graphs on top. Tracing is LangSmith (or OpenTelemetry export). Files [02](02-langchain-essentials.md) to [06](06-deep-agents-and-ambient.md) cover all of this.

### OpenAI Agents SDK
`Runner` owns the loop, which classifies each model result as final output, handoff, or tool calls, under `max_turns`. Its primitives:
- **Tools** via `@function_tool`. Approval is `needs_approval=True` (or a predicate) on the tool. A paused run surfaces `result.interruptions`, which you `approve`/`reject` on a `RunState` and resume with `Runner.run(agent, state)`.
- **Handoffs**, exposed to the model as `transfer_to_<agent>` tools, with `input_filter` to trim history and `on_handoff` for checks. `Agent.as_tool()` is the alternative that keeps control in the caller.
- **Guardrails**: input guardrails (first agent only), output guardrails (final agent only) and tool guardrails. Input guardrails run **in parallel with the agent by default**, so tokens and tool calls may already be spent when a tripwire fires. Blocking mode (`run_in_parallel=False`) prevents that.
- **Tracing**, on by default, with spans for agent, generation, function, guardrail and handoff. It captures sensitive data by default. Custom processors export to other backends.
([OpenAI Agents SDK docs](https://openai.github.io/openai-agents-python/))

### Claude Agent SDK
The Claude Code harness as a library ([Anthropic, "Building agents with the Claude Agent SDK"](https://claude.com/blog/building-agents-with-the-claude-agent-sdk)). You get its loop, compaction, built-in tools (Read, Write, Edit, Bash, Glob, Grep, WebFetch, and more), subagents, and permission system. Custom tools are in-process MCP servers (`@tool` plus `create_sdk_mcp_server`, named `mcp__<server>__<tool>`). Control points are **hooks** (`PreToolUse` can return allow, deny, ask or defer, and can rewrite input), `can_use_tool`, `allowed_tools` and `disallowed_tools`, `permission_mode`, and `max_turns`. Sessions resume by `resume=<session_id>` and branch with `fork_session`. Its strength is that it is the harness Anthropic tunes for its own models. Its cost is that you configure the loop rather than own it. ([Agent SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python))

### CrewAI
Two layers. **Crews** are role-playing agent teams (each agent has a role, goal and backstory) executing tasks with sequential or hierarchical processes. **Flows** are event-driven workflows: `@start`, `@listen`, `@router` on methods of a `Flow[StateModel]` class, with `@persist` for state persistence and a `@human_feedback` decorator (CrewAI 1.8.0+). The docs recommend Flows as the backbone and Crews for steps that need a team. ([CrewAI docs](https://docs.crewai.com/))

### Google ADK and A2A
ADK (`pip install google-adk`) defines `Agent(name, model, instruction, tools)`, with workflow agents (sequential, parallel, loop) and sub-agents. It is Gemini-first but supports other models. **A2A** (Agent2Agent) is a separate open protocol, originally from Google and now under the Linux Foundation, for **agent-to-agent** discovery and task delegation between opaque agents. Its docs describe it as complementary to MCP: MCP connects an agent to tools, and A2A connects agents to agents. Reach for A2A when the other agent belongs to another team or vendor and you can only see its interface. ([adk.dev](https://adk.dev/), [a2a-protocol.org](https://a2a-protocol.org/latest/))

### Pydantic AI
A type-first agent library: `Agent("anthropic:...", deps_type=..., output_type=Model)`, tools via `@agent.tool` (which receives a `RunContext` with typed dependencies) or `@agent.tool_plain`, and validated `result.output`. Durable execution is delegated to real engines (Temporal, DBOS, Prefect), so each model and tool call becomes a durable activity. Graph control flow lives in a separate `pydantic-graph` package. Its strength: if your team already thinks in Pydantic models and dependency injection, it feels like ordinary Python. ([Pydantic AI docs](https://pydantic.dev/docs/ai/overview/))

## The decision table

| | Raw loop (`ainative_kit`) | LangGraph | OpenAI Agents SDK | Claude Agent SDK | CrewAI | Google ADK + A2A | Pydantic AI |
|---|---|---|---|---|---|---|---|
| **Who owns the loop** | you | you, as a graph | SDK `Runner` | SDK (Claude Code harness) | framework (Crew process / Flow) | framework (agent and workflow agents) | library `Agent.run` |
| **Approval gate** | your callback | `interrupt()` node, or `HumanInTheLoopMiddleware` | `needs_approval` on the tool | `PreToolUse` hook / `can_use_tool` | `@human_feedback` in Flows | callbacks / tool confirmation (check docs) | built-in tool approval (per docs) |
| **Paused / durable state** | none (you build it) | checkpointer per super-step (memory, SQLite, Postgres) | `RunState` you serialise | session log, `resume` / `fork_session` | `@persist` on Flows | ADK session services | external engine (Temporal, DBOS, Prefect) |
| **Replay / time travel** | record/replay cassettes | first-class (`get_state_history`, fork) | resume only | session fork | limited | session-level | engine replay (Temporal) |
| **Request visibility** | total | total if nodes call your client; less with prebuilt agents | SDK builds the request; visible in traces | harness builds the prompt; visible via hooks and transcript | framework builds role prompts | framework builds | high (you write instructions; typed) |
| **Tracing** | your spans | LangSmith / OTel | built in, on by default | message stream, hooks, OTel (check docs) | built in plus integrations | Google Cloud tooling | Logfire / OTel |
| **Multi-agent primitive** | you compose | subgraphs, `Send`, supervisor patterns | handoffs, agents-as-tools | subagents | crews (roles, hierarchical process) | sub-agents, A2A across orgs | agent delegation via tools |
| **Model portability** | whatever your client supports | any (via LangChain or your client) | OpenAI-first, adapters for others | Claude | any (via LiteLLM) | Gemini-first, others supported | any |
| **Choose it when** | learning; tiny agents; you need full control and no pause | durable, long-running, HITL-heavy or replay-heavy agents | OpenAI-centric stack; handoff-style routing; guardrails as a first-class concept | you want Claude Code's harness (files, bash, compaction) for a Claude agent | role-based business workflows; teams that like the crew metaphor | GCP stack; cross-org agent interop via A2A | type-heavy Python teams; durable execution via Temporal |

**Verification status (2026-10-19).** The LangGraph, OpenAI Agents SDK and Claude Agent SDK columns were checked against their primary docs. For CrewAI, ADK and Pydantic AI, the loop, gate and state rows come from their docs. Their tracing, portability and replay cells, plus anything marked "check docs", are general knowledge that was not re-verified for this module. Confirm those before you rely on them.

> **Synthesis:** For the systems this course targets (agents that mutate production and need audit, replay and asynchronous approval), the decisive rows are *durable state*, *replay* and *request visibility*. On those three, LangGraph with your own model client, or Pydantic AI on Temporal, are the strongest open options. The Claude Agent SDK wins when the task looks like Claude Code's: files, shell, long context. The OpenAI Agents SDK is the simplest path to guardrails and handoffs if you are on OpenAI models.

## Worked example: choosing for three real requests

**1. "An agent that triages PagerDuty alerts and can restart services with approval."** Gate: must be structural. Paused state: must survive deploys (approval can take an hour). Visibility: auditors will ask what the agent saw. **Choice:** LangGraph with a Postgres checkpointer and your own client, which is this module's code. The bad choice is a chat-style SDK with in-memory sessions: the approval request outlives the pod.

**2. "A repo-maintenance bot that upgrades dependencies and opens PRs."** It needs files, shell, tests and long context, so it looks like Claude Code. **Choice:** Claude Agent SDK, with a `PreToolUse` hook that denies `git push` to protected branches, `disallowed_tools` for network tools, and a sandbox ([Module 16](../16-security-and-containment/README.md)). Writing your own file-edit tools and compaction would be rebuilding the harness.

**3. "Customer-support routing across billing, refunds and tech, on an OpenAI-based stack."** Handoffs are the core primitive, and the input guardrail is a real requirement (block prompt injection before the expensive agent runs). **Choice:** OpenAI Agents SDK with blocking input guardrails (`run_in_parallel=False`), because refunds have side effects.

What to check in each case: build the raw version first (a day), write the parity test, and make sure your eval suite runs against both. If the framework version's requests differ from the raw version's, find out why before you ship.

## Pitfalls

- **Picking by demo.** Multi-agent demos are easy and multi-agent production is hard. Ask the three questions first.
- **Parallel guardrails on side-effecting agents** (OpenAI Agents SDK default). The tripwire fires after the tool already ran. Use blocking mode.
- **`allowed_tools` as an allowlist** (Claude Agent SDK). It auto-approves; it does not restrict. Use `disallowed_tools` or `tools`.
- **Assuming durable means idempotent.** No framework makes your tools idempotent. Temporal retries activities, LangGraph replays nodes, and session resume can re-issue calls.
- **Adopting two frameworks at once** (for example CrewAI orchestrating LangGraph agents) without a reason. You get two state models and two trace trees. A2A is the principled way to cross a framework boundary.
- **Ignoring trace export.** If the framework's traces cannot leave its platform, your incident tooling is locked in. Prefer OTel-compatible exporters.

## In your day job

- Add the three questions to your design-review template for any agent proposal.
- Keep the raw loop and a parity test no matter which framework you choose. It is your exit strategy.
- When a framework releases a major version, re-run the parity test and the eval suite before you upgrade. Default prompts and tool schemas change between versions.
- For cross-team agents, standardise on a protocol (MCP for tools, A2A for agents) rather than on a framework.
