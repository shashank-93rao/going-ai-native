# 05: Tools, MCP, skills, hooks & execution environments
> After this module you can design the interface an agent works through (tools, MCP servers, skills, hooks and the sandbox under them) so that it uses few tokens, recovers from its own mistakes, and can't do the irreversible thing by accident.

## Why this matters

Your agent is only as good as the actions it can take and the observations it gets back. The model decides; the tools are the only way that decision reaches the world. Anthropic's SWE-bench team reports that they "spent more time optimizing our tools than the overall prompt" ([Anthropic, "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents)). Most bad agent behavior you will debug traces back to one of four tool-layer faults: the agent picked the wrong tool from too many similar ones, a tool flooded the context with 20k tokens of rows, an error said `KeyError: 'ledger-writer'` and gave no way forward, or nothing stopped a destructive command.

The stakes are concrete for an infra engineer. Give an on-call agent a generic `query_db(sql)` tool and it will guess column names, dump a table into its context, and then reason over the wreckage. Give it 40 MCP tools from four servers and it will spend tens of thousands of tokens on tool definitions before it reads the alert. Give it `kubectl` with no hook and no RBAC, and a prompt injection in a log line is one step away from `kubectl delete ns payments`.

This module treats the agent–computer interface as an engineering artifact with tests: tool schemas you can diff, responses with token budgets, error messages you can grep for in traces, hooks with unit tests, and skills with trigger evals. That's the course thesis applied at the boundary where the model touches your systems. **Autonomy scales with verifiability**, and the tool layer is where you make actions checkable (hooks as gates), observations cheap (response formats, code-as-action), and mistakes recoverable (actionable errors).

## The distributed-systems anchor

**Tool design is API design for an unreliable client.** You've designed APIs for clients you don't control: mobile apps on old versions, partner integrations written by an intern. You learned to make invalid states unrepresentable, return errors that say how to fix the request, paginate everything, and version the contract. An LLM is that client, but more so. It is nondeterministic. It reads your docs (the tool description) on every single call. It has a small, expensive buffer (the context window) that your response gets copied into permanently. And it will retry, so an error message is not a log line; it is the input to its next request.

**Hooks are admission controllers. Sandboxes are capability boundaries.** A `PreToolUse` hook is a validating admission webhook: it sees the request before it executes and can deny it with a reason. The sandbox is the cgroup/namespace boundary: whatever the policy layer misses, the kernel still enforces.

Where the analogy breaks:
- A human API client reads the docs once. The model re-reads every tool description on every turn, so descriptions are a recurring token cost and also a steering surface. Changing one sentence changes behavior.
- Your API's response goes to a parser. The model's tool result goes into a context window where it competes for attention with everything else and stays there. Verbosity isn't free bandwidth; it degrades later reasoning.
- An admission webhook is a security control. A hook running in the same environment as an agent that can write arbitrary code is a guardrail against mistakes, not a boundary against an adversary. Real boundaries are credentials and the sandbox (see [Module 16](../16-security-and-containment/README.md)).

## Learning goals
- [ ] Redesign a generic tool (`query_db`) into task-shaped tools with namespaced names, `response_format`, pagination, a token budget and actionable errors, and measure the token difference.
- [ ] Explain why accuracy drops as tool count grows, and choose between curating subsets, deferred loading (tool search), and code-as-action.
- [ ] Build and register a minimal MCP server, and state when an MCP server is the right choice versus a CLI the agent calls through the shell.
- [ ] Quantify how code-as-action and programmatic tool calling move intermediate data out of the context.
- [ ] Write a skill folder that uses progressive disclosure, with a bundled script that is executed rather than read.
- [ ] Write a `PreToolUse` hook that blocks a destructive command, test it offline, and explain why blocking gates work and steering hooks mostly don't.
- [ ] Choose an execution environment (local sandbox, container, remote devbox) for a given autonomy level, and make one of your own products consumable by agents (llms.txt, a JSON-mode CLI).

## Reading order
1. [01-tool-design-as-api-design](01-tool-design-as-api-design.md): naming, consolidation, token-efficient responses, pagination, actionable errors. Worked example: redesigning `query_db`.
2. [02-tool-count-and-curation](02-tool-count-and-curation.md): why more tools makes agents worse, curated subsets (Stripe Toolshed), tool search, and how to measure the effect of adding a tool.
3. [03-mcp](03-mcp.md): what MCP is, primitives, transports, and when to use it instead of a CLI. Worked example: a deploy-status MCP server.
4. [04-code-as-action](04-code-as-action.md): code execution with MCP, programmatic tool calling, CodeAct. Worked example: cluster-wide lag scan, 295 calls vs one script.
5. [05-skills](05-skills.md): progressive disclosure, SKILL.md, scripts that run instead of load. Worked example: "investigate a Kafka consumer lag alert".
6. [06-hooks](06-hooks.md): PreToolUse/PostToolUse/Stop, blocking gates vs steering. Worked example: blocking `kubectl delete` in prod.
7. [07-execution-environments-and-agent-surfaces](07-execution-environments-and-agent-surfaces.md): sandboxes as capability boundaries, and building products that agents can use (llms.txt, CLIs).
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
- [Module 01](../01-llms-for-systems-engineers/README.md): tokens, context, prompt caching.
- [Module 03](../03-context-engineering/README.md): context as a budget; just-in-time retrieval.
- Helpful: [Module 07](../07-loops/README.md) for the agent loop this module's tools plug into.

## Key takeaways
- Design tools around the questions the agent must answer (`payments_failure_summary`), not around your tables or endpoints (`query_db`, `get_partition_lag`).
- Every tool response has a token budget, a `concise`/`detailed` switch, and a header that says "N of M". Truncation always tells the model how to get the rest.
- Error messages are the model's next input. Name the valid values, suggest the nearest match, and say which tool to call instead. Our test fixture shows the difference: the same scripted policy recovers in one step with an actionable error and exhausts its error budget with `KeyError`.
- Fewer tools beat more tools. Curate per-agent subsets, defer-load the long tail, and measure each addition with an eval instead of assuming it helps.
- Use MCP when you need a shared, authenticated, stateful integration across many agents and hosts. Use a CLI when the agent has a shell and the tool already exists. Use code-as-action when the work is loops over data.
- Skills are lazily-loaded runbooks: about 100 tokens of description always in context, the body only when triggered, scripts executed rather than read.
- Hooks that block on a deterministic check (deny `kubectl delete` in prod, refuse to stop while tests fail) work. Hooks that try to nudge behavior mostly don't.
- The sandbox is both the capability boundary and the security boundary. Hooks and prompts reduce mistakes; credentials and isolation limit blast radius.
