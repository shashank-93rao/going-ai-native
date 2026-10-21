# 02: Tool count, curation and deferred loading

## The idea

Every tool you give an agent costs you twice. First in tokens: its name, description and schema sit in the context on every turn. Second in accuracy: each extra tool is one more wrong answer to "which tool now?", and one more description competing for attention. Past a small number, adding tools makes agents worse at tasks they could already do.

There are three responses, in order of preference:
1. **Curate**: give each agent only the tools its job needs.
2. **Defer**: keep a few tools hot and let the agent search for the rest when it needs them.
3. **Collapse**: replace many narrow tools with one code-execution tool over an API (see [04-code-as-action](04-code-as-action.md)).

The course stance, from the research synthesis: use few, curated tools, prefer code-as-action for data-heavy work, and **measure the effect of adding a tool** instead of assuming it helps.

## Why it matters

The evidence points one way, from several directions:
- Drew Breunig calls this *context confusion*. He reports that on the Berkeley Function-Calling Leaderboard "every model performs worse when provided with more than one tool," and cites a study (arXiv 2411.15399) where a quantized Llama 3.1 8B failed a query when given all 46 tools and succeeded with 19, even though the context was within its window ([Breunig, "How Long Contexts Fail"](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)).
- Anthropic reports that tool definitions alone can consume tens of thousands of tokens before the conversation starts. In their tool search example, about 77k tokens of definitions dropped to about 8.7k with deferred loading, and MCP eval accuracy rose from 49% to 74% on Opus 4 and from 79.5% to 88.1% on Opus 4.5 ([Anthropic, "Introducing advanced tool use"](https://www.anthropic.com/engineering/advanced-tool-use)).
- Simon Willison: "GitHub's official MCP on its own famously consumes tens of thousands of tokens of context" ([Willison, "Claude Skills are awesome"](https://simonwillison.net/2025/Oct/16/claude-skills/)).
- Spotify's background coding agent deliberately keeps a minimal toolset (a verify tool, restricted git, allowlisted bash): "The more tools you have, the more dimensions of unpredictability you introduce" ([Spotify Engineering, part 2](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2)).
- Stripe runs the other end of the spectrum. Its internal MCP server, Toolshed, hosts 400+ tools, and each Minion agent gets a *curated subset* ([Stripe, "Minions"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)). A big catalog is fine. A big loadout is not.

Anthropic's context-engineering guidance puts the selection test well (paraphrased): if a human engineer can't say for certain which tool fits a situation, don't expect the agent to do better ([Anthropic, "Effective context engineering"](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

## How it works

### Why more tools hurt
- **Token cost per turn.** Definitions are part of the prompt. With prompt caching they are cheap to resend, but they still occupy the window and the model still attends over them.
- **Selection is a classification problem** with a growing label set. Overlapping tools (`search_issues` vs `find_issues` vs `github_search`) are near-duplicate labels, and there is no right answer between them.
- **Descriptions are instructions.** Forty descriptions are forty small prompts, some of which will conflict with your system prompt ("always use this tool for X").
- **Changing the tool list breaks the cache.** OpenAI's Codex write-up notes that changing tools mid-thread breaks the prompt-cache prefix, and that an early MCP bug that listed tools in inconsistent order caused cache misses ([OpenAI, "Unrolling the Codex agent loop"](https://openai.com/index/unrolling-the-codex-agent-loop/)). Pick the loadout at session start and keep it fixed.

### Decision rules

| Situation | Do this |
|---|---|
| One agent, one job, fewer than ~10 tools | Curate the list and stop. |
| Many agents sharing a big catalog | Central registry (Toolshed-style), per-agent allowlists checked into config. |
| One agent that genuinely needs a long tail of rarely used tools | Defer-load them: keep 3–5 hot, search for the rest. Anthropic suggests this when definitions exceed about 10k tokens or there are more than about 10 tools. |
| Many narrow tools over one API, used in loops | Collapse to code-as-action. |
| Two tools whose descriptions you can't tell apart | Merge them, or delete one. |

### Mechanisms

**Per-agent allowlists in Claude Code.** A subagent's frontmatter lists its tools, and `--allowedTools` scopes a headless run:

```markdown
---
name: incident-triage
description: Read-only triage of a production alert. Use for pages and alert investigations.
tools: Read, Grep, Glob, Bash, mcp__deploy-status__deploys_status, mcp__deploy-status__deploys_recent
---
```

**Deferred loading on the API.** Mark the long tail `defer_loading: true` and include a tool-search tool. The API loads matching definitions only when the model searches ([Anthropic, advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use); beta header `advanced-tool-use-2025-11-20` at time of writing):

```json
{"tools": [
  {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},
  {"name": "kafka_consumer_lag", "description": "...", "input_schema": {"...": "..."}},
  {"name": "kafka_reassign_partitions_plan", "description": "...", "input_schema": {"...": "..."},
   "defer_loading": true}
]}
```

Claude Code turns tool search on by default for MCP tools ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)), so in a coding session the big-MCP-server penalty is smaller than it was in 2025. In your own agents on the raw API, you have to opt in.

**Tool use examples.** For tools whose correct use isn't obvious from the schema, Anthropic's `input_examples` field (1–5 realistic examples) raised complex-parameter accuracy from 72% to 90% in their internal test. Use it on the two or three tools that confuse the model, not on all of them.

## Worked example: curating an incident agent

Situation: your team wires a triage agent to every MCP server it has: a GitHub server, a Kubernetes server, a metrics server, a PagerDuty server and the deploy-status server from [03-mcp](03-mcp.md). That's about 70 tools. The agent's job is read-only triage of a page.

**Before.** The trace of a typical run (illustrative output):

```text
turn 1  github_search_code(query="ConsumerLagHigh")             # wrong tool: alert names aren't in code
turn 2  k8s_list_pods(namespace="default")                      # wrong namespace, 180 pods returned
turn 3  metrics_query(q="kafka_consumergroup_lag")              # right idea, no label filter, 9k tokens
turn 4  k8s_get_events(namespace="payments")
turn 5  pagerduty_list_incidents(status="triggered")            # irrelevant to the diagnosis
...
turn 14 answer
```

The model isn't stupid. It's choosing among 70 labels, half of which plausibly apply.

**After.** Start from the job, not the catalog. Write down the 5–8 questions triage actually asks, and map each to one tool:

| Triage question | Tool | Source |
|---|---|---|
| What changed recently? | `deploys_recent` | deploy-status MCP |
| Is this service's latest deploy healthy? | `deploys_status` | deploy-status MCP |
| What does consumer lag look like? | `kafka_consumer_lag` | in-house tool |
| What are the errors? | `logs_search` | in-house tool |
| What does the metric say over time? | `metrics_query` (with required label filters) | metrics MCP |
| Pod health for one workload | `k8s_get_workload_status` | Kubernetes MCP |

Six hot tools. The rest of the Kubernetes and GitHub servers are deferred, or simply not attached to this agent. Writes (`k8s_rollout_restart`) aren't attached at all: that's a different agent with a human approval step.

**Measure it instead of believing it.** Build a small eval from past incidents ([Module 10](../10-evals-fundamentals/README.md) covers how). One JSONL row per task:

```json
{"id": "inc-2291", "alert": "ConsumerLagHigh group=ledger-writer-v2", "expected_cause": "poison_message", "expected_partition": 3}
{"id": "inc-2304", "alert": "PaymentsErrorRate merchant=Globex Rail", "expected_cause": "issuer_outage"}
{"id": "inc-2317", "alert": "ConsumerLagHigh group=search-indexer", "expected_cause": "consumer_down"}
```

Run each configuration several times per task (agents are nondeterministic; see [Module 12](../12-hill-climbing/README.md) on noise checks) and compare:

| Config | Hot tools | Correct cause | Median tool calls | Median input tokens |
|---|---|---|---|---|
| all servers attached | ~70 | (measure) | (measure) | (measure) |
| curated 6 | 6 | (measure) | (measure) | (measure) |
| curated 6 + deferred rest | 6 hot | (measure) | (measure) | (measure) |

The cells are blank on purpose: the numbers are yours to measure, not ours to invent. The decision rule is the same as any performance change. Keep the configuration that wins on accuracy, break ties on tokens, and re-run when the model changes.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Attaching a whole MCP server "in case" | Count tools in the first request of a trace. If it's above ~15, ask which ones were called in the last 100 runs. |
| Two tools that overlap | Tool-call distribution shows both used for the same task type, or the model alternating between them. Merge or delete. |
| Curating by intuition | A tool you removed turns out to be needed for 5% of tasks. Only an eval with real tasks tells you. |
| Changing the toolset mid-session | Cache-read tokens drop to zero after a tool list change. Keep the loadout fixed per session. |
| Deferring the tools that matter | The model never searches for a tool it doesn't know exists. Keep the core path hot; defer only the long tail. |
| Write tools in a read-only agent | A triage agent that can restart pods will eventually do it. Keep writes in a separate agent with its own gate ([06-hooks](06-hooks.md)). |

## In your day job
- Dump the tool list from the first request of one of your agent traces. Count it. Delete everything not called in the last 100 runs, then run your eval.
- For a shared MCP catalog, keep a per-agent allowlist in the agent's config and review changes to it like IAM changes.
- When someone proposes "let's also give it tool X," ask for the eval delta, not the demo.
