# References

Facts about fast-moving tools were checked against the live docs in October 2026. Check again before relying on exact field names.

## Tool design
- [Anthropic, "Writing effective tools for agents, with agents"](https://www.anthropic.com/engineering/writing-tools-for-agents) (2025-09). The core source for [01](01-tool-design-as-api-design.md). Take: consolidation examples (`schedule_event`, `search_logs`, `get_customer_context`), namespacing, names over UUIDs, `response_format` (72 vs 206 tokens), the 25k-token Claude Code cap, the "2025" web-search anecdote, and the eval loop for improving tools.
- [Anthropic, "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents) (2024-12). Appendix 2 on the agent–computer interface: poka-yoke your tools, the absolute-paths fix.
- [Anthropic, "Effective context engineering for AI agents"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (2025-09). Avoid bloated, overlapping toolsets.
- [HumanLayer, "12-Factor Agents"](https://github.com/humanlayer/12-factor-agents). Factor 9 (compact errors into context, break after about 3 consecutive errors) is the governor in `agent_loop.py`.

## Tool count and curation
- [Drew Breunig, "How Long Contexts Fail"](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html) (2025-06). Context confusion: BFCL, and the 46-tools vs 19-tools result.
- [Anthropic, "Introducing advanced tool use"](https://www.anthropic.com/engineering/advanced-tool-use) (2025-11). Tool search (`defer_loading`), programmatic tool calling (`allowed_callers`), `input_examples`, and their measured gains.
- [Stripe, "Minions: Stripe's one-shot, end-to-end coding agents"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) (2026-02). Toolshed: 400+ tools, curated subsets per agent; isolated devboxes.
- [Spotify Engineering, "Context engineering for background coding agents" (part 2)](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2). Three tools only, and why.
- [OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/). Don't change tools mid-thread; tool-ordering cache misses.

## MCP
- [MCP specification (latest, 2026-07-28)](https://modelcontextprotocol.io/specification/latest). Roles, primitives, the stateless base protocol, the security principles.
- [MCP transports, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) and [2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports). Compare them to see the session model go away.
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) and [What's new in v2](https://py.sdk.modelcontextprotocol.io/whats-new/). `MCPServer` (formerly `FastMCP`), and only `ToolError` messages reach the model.
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp). `claude mcp add`, scopes, `.mcp.json`, the 10k-token warning and 25k-token default cap (`MAX_MCP_OUTPUT_TOKENS`).
- [Simon Willison, "Claude Skills are awesome, maybe a bigger deal than MCP"](https://simonwillison.net/2025/Oct/16/claude-skills/) (2025-10). The CLI-over-MCP argument and token costs.
- [Armin Ronacher, "Your MCP Doesn't Need 30 Tools: It Needs Code"](https://lucumr.pocoo.org/2025/8/18/code-mcps/) (2025-08). One code tool plus MCP for session management; `pexpect-mcp`.

## Code-as-action
- [Anthropic, "Code execution with MCP"](https://www.anthropic.com/engineering/code-execution-with-mcp) (2025-11). Servers as a code API on a filesystem; 150k to 2k tokens; PII tokenization; saving code as skills; the sandbox tradeoff.
- [Wang et al., "Executable Code Actions Elicit Better LLM Agents" (CodeAct)](https://arxiv.org/abs/2402.01030) (2024). Code as the action space; up to 20% higher success on their benchmarks.
- Hugging Face Agents Course, smolagents unit ("Writing actions as code snippets or JSON blobs"). A framework built around code agents; good for trying the pattern quickly.

## Skills
- [Anthropic, "Equipping agents for the real world with Agent Skills"](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) (2025-10, updated 2025-12). Three levels of progressive disclosure; run vs read scripts; security.
- [Agent Skills specification](https://agentskills.io/specification). Frontmatter constraints (`name` 64 chars, `description` 1024), directory conventions, size guidance.
- [Claude Code skills docs](https://code.claude.com/docs/en/skills). Claude Code's extra frontmatter fields (`disable-model-invocation`, `context: fork`, `paths`) and the compaction re-attach budget.
- [OpenAI, "Testing Agent Skills Systematically with Evals"](https://developers.openai.com/blog/eval-skills). Trigger evals with negative controls.
- [Geoffrey Huntley, "nobody should type code by hand anymore"](https://ghuntley.com/agency/) (2026-10). Skills and AGENTS.md are probabilistic; test with and without; prune periodically.

## Hooks
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks) and [hooks guide](https://code.claude.com/docs/en/hooks-guide). Event list, stdin schema, exit codes, `permissionDecision`, Stop `decision: "block"`, `stop_hook_active`, the 8-continuation cap.
- [Armin Ronacher, "Agentic Coding Things That Didn't Work"](https://lucumr.pocoo.org/2025/7/30/things-that-didnt-work/) (2025-07). The case against hooks for steering.
- [Spotify Engineering, "Feedback loops" (part 3)](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3). Verifiers in a Stop hook: no PR if any fail.

## Execution environments and agent-native surfaces
- [Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing). What's inside the boundary (shell) and what isn't (file tools, MCP servers, hooks); `allowUnsandboxedCommands`.
- [Anthropic, "Beyond permission prompts: Claude Code sandboxing"](https://www.anthropic.com/engineering/claude-code-sandboxing). 84% fewer prompts; credentials outside the sandbox.
- [Anthropic, "Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents) (2026-04). Containers as cattle.
- [Anthropic, "How we contain Claude across products"](https://www.anthropic.com/engineering/how-we-contain-claude). Pre-trust code paths, credentials, live inspection.
- [Simon Willison, "Designing agentic loops"](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/) (2025-09). Sandbox YOLO mode; shell commands documented in AGENTS.md; budget-capped credentials.
- [llms.txt](https://llmstxt.org/). The format (Jeremy Howard, 2024).
- [Andrej Karpathy, "Software Is Changing (Again)"](https://www.youtube.com/watch?v=LCEmiRjPEtQ) (2025-06). "Build for agents": agents as a third consumer of digital information.
