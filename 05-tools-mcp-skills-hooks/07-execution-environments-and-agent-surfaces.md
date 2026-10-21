# 07: Execution environments, sandboxes, and agent-native product surfaces

## The idea

Two sides of the same boundary.

**Inward: where the agent runs.** The execution environment (laptop shell, OS-level sandbox, container, remote devbox, microVM) defines what the agent *can* do, regardless of what its prompt, skills or hooks say. It's the capability boundary and the security boundary at once. Every other control in this module reduces the chance of a mistake; the environment bounds the cost of one.

**Outward: how agents use what you build.** Your service, CLI and docs are now consumed by other people's agents as well as humans and programs. Karpathy's "build for agents" framing calls agents a third consumer of digital information, after humans (GUIs) and programs (APIs): docs should be Markdown, and "click here" should become a curl command ([Karpathy, "Software Is Changing (Again)"](https://www.youtube.com/watch?v=LCEmiRjPEtQ)). An agent-native surface is the same API-design discipline as [01](01-tool-design-as-api-design.md), applied to your product.

## Why it matters

The environment decides how much autonomy is safe, which is the course thesis in its most physical form:
- Anthropic reports that sandboxing Claude Code cut permission prompts by 84%, and that it means "even a successful prompt injection is fully isolated" ([Anthropic, "Beyond permission prompts"](https://www.anthropic.com/engineering/claude-code-sandboxing)). Fewer prompts is not a convenience feature: approval fatigue is how humans end up rubber-stamping the one prompt that mattered.
- Stripe's Minions run in isolated, pre-warmed devboxes that spin up in about 10 seconds, cut off from production and the internet. That isolation is what lets them run without per-action permission prompts, and in parallel ([Stripe](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)).
- Willison's guidance for YOLO mode: run it in Docker, Apple's `container`, or Codespaces; restrict files, secrets and network to an allowlist; and give any credential that can spend money a dedicated account with a hard budget ([Willison, "Designing agentic loops"](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/)).
- Anthropic's Managed Agents treat containers "as cattle, not pets": a sandbox failure becomes a tool-call error the agent can retry on a fresh container ([Anthropic, "Scaling Managed Agents"](https://www.anthropic.com/engineering/managed-agents)).

On the outward side, agents that can't use your product will route around it, often by scraping your HTML docs or parsing human-oriented CLI output. Both are brittle, and the brittleness becomes your support load.

## How it works

### Choosing an environment

| Autonomy level | Environment | What it bounds | Gaps |
|---|---|---|---|
| Interactive, you approve most actions | Laptop, Claude Code permission prompts | Each action, by your attention | Approval fatigue |
| Interactive, auto-approve shell | Claude Code Bash sandbox (Seatbelt on macOS, bubblewrap on Linux/WSL2) | Shell commands: writes limited to allowed dirs, network through a proxy with a domain allowlist (empty by default) | File tools, MCP servers and hooks run **outside** it |
| Unattended loops, background agents | Container or dev container with no prod credentials, egress allowlist | The whole agent process | Whatever credentials you mount |
| Fleet of agents, untrusted inputs | Remote devboxes / microVMs per task, credentials via proxy | Per-task blast radius; easy reset | Cost and spin-up time |

The Claude Code sandbox is worth understanding precisely, because the gap matters ([Claude Code sandboxing docs](https://code.claude.com/docs/en/sandboxing)):
- It's off by default. Turn it on with `/sandbox` or `"sandbox": {"enabled": true}` in settings.
- It covers Bash (and PowerShell and Monitor) commands and their child processes. Claude's built-in Read/Edit/Write/WebFetch follow permission rules instead, and MCP servers and hooks run unsandboxed.
- Sandboxed commands can be auto-approved. A command that fails in the sandbox can be retried unsandboxed unless you set `allowUnsandboxedCommands: false`.
- To put everything behind one boundary, run the Claude Code process itself in a container or VM.

### Principles that carry across environments
- **Credentials stay outside.** Anthropic's cloud setup keeps git credentials out of the sandbox; a proxy checks the push target before attaching the real token. Apply the same idea to cloud and database credentials: the agent gets a token that can read, and a proxy or a human holds the one that can write.
- **Egress is a capability.** An allowlist of domains is the difference between "the agent read a malicious log line" and "the agent sent your secrets to the attacker" ([Module 16](../16-security-and-containment/README.md)).
- **Reset is cheap, so use it.** Fresh environment per task means no state leaks between runs. It also matters for evals: Anthropic found agents using git history from earlier trials (see [Module 10](../10-evals-fundamentals/README.md)).
- **The environment must still be legible.** A sandbox the agent can't observe (no logs, no test runner, no local services) produces confident wrong answers. That's the subject of [Module 08](../08-harness-engineering/README.md).

### Agent-native surfaces: what to build

| Surface | Agent-native version |
|---|---|
| Docs | Markdown at stable URLs, plus an `llms.txt` index |
| CLI | `--json` output, stable exit codes, errors that name the fix, no interactive prompts unless a TTY is attached, `--dry-run` |
| Auth | Headless: tokens via env or file, no browser-only flows |
| API errors | The error says the valid values and the next call (same rule as [01](01-tool-design-as-api-design.md)) |
| Integrations | A small MCP server for hosts without a shell ([03](03-mcp.md)) |

**`llms.txt`** is a proposal by Jeremy Howard (first published September 2024): a Markdown file at `/llms.txt` with an H1 title (the only required section), a blockquote summary, optional prose, H2 sections of `[name](url): notes` link lists, and an `## Optional` section an agent can skip when it needs less context. Pages should also be available as clean Markdown at the same URL with `.md` appended ([llmstxt.org](https://llmstxt.org/)). The MCP docs (`modelcontextprotocol.io/llms.txt`) and Claude Code docs (`code.claude.com/docs/llms.txt`) both publish one.

## Worked example: making `deployctl` agent-native

Situation: your platform team's `deployctl` CLI is how humans check and run deploys. Agents in three teams now call it through the shell, and they're doing badly.

### Before

```text
$ deployctl status ledger-writer
╭──────────────────────────────────────────────╮
│ ledger-writer  ●  ROLLING  v2.14.1 (7/12)     │
│ started 15 minutes ago by priya               │
╰──────────────────────────────────────────────╯
? Watch rollout? (Y/n)
```

What the agent experiences: box-drawing characters to parse, a relative time it must convert, and an interactive prompt that hangs a non-TTY shell until timeout. On a typo it gets `Error: not found` and exit code 1, the same exit code as "API down." The docs are a JS-rendered portal the agent's fetch tool sees as an empty page.

### After

```text
$ deployctl status ledger-writer --env prod --json
{"service":"ledger-writer","env":"prod","deploy_id":"dpl_9a71","version":"v2.14.1","status":"rolling",
 "pods_ready":7,"pods_total":12,"started_at":"2025-10-09T08:38:20Z","author":"priya","previous_version":"v2.14.0"}

$ deployctl status ledger-writr --env prod --json; echo "exit=$?"
{"error":"unknown_service","message":"No service 'ledger-writr'. Did you mean 'ledger-writer'? Run `deployctl services` to list all.","retryable":false}
exit=2

$ deployctl rollback ledger-writer --env prod --to v2.14.0 --dry-run --json
{"plan":{"service":"ledger-writer","from":"v2.14.1","to":"v2.14.0","pods":12,"strategy":"rolling"},"executed":false}
```

The changes, as a spec you can hand to the platform team:
1. `--json` on every read command; a stable schema; absolute timestamps.
2. Exit codes: `0` ok, `2` caller error (fix the arguments), `3` transient (retry), `4` refused by policy. The agent can branch on these without parsing prose.
3. Errors as JSON with `error`, `message` (naming the fix) and `retryable`.
4. Never prompt when stdin isn't a TTY; `--yes` for humans who want that.
5. `--dry-run` on every write, printing the plan.
6. A `deployctl help --markdown` page and an `llms.txt` at the docs root:

```markdown
# deployctl

> CLI and HTTP API for deploying services at Acme. All read commands support --json. Writes support --dry-run.

## Docs
- [Quickstart](https://platform.acme.internal/deployctl/quickstart.md): install, auth with DEPLOYCTL_TOKEN, first status call
- [Command reference](https://platform.acme.internal/deployctl/commands.md): every command, flag, exit code and JSON schema
- [Rollbacks](https://platform.acme.internal/deployctl/rollbacks.md): when rollback is allowed, approvals, dry-run output

## Optional
- [Architecture](https://platform.acme.internal/deployctl/architecture.md): how deploys flow through the system
```

Then check it the way you'd check any interface: run your agent eval ([Module 10](../10-evals-fundamentals/README.md)) on "is ledger-writer's latest deploy healthy?" against the old and new CLI, and count tool calls, errors and wrong answers.

Notice that nothing here is AI-specific engineering. Stripe's line applies: "if it's good for humans, it's good for LLMs, too." Scripts in CI have wanted `--json` and honest exit codes for years. Agents make the cost of not having them visible.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| "Sandboxed" but credentials mounted | `env` or `~/.aws` inside the sandbox shows prod credentials. Audit what the agent's process can read. |
| Sandbox covers the shell only | MCP servers or hooks run with full access. Know which components are inside the boundary; containerize the whole agent for unattended runs. |
| Unsandboxed retry escape hatch left on | Commands that fail in the sandbox silently re-run outside it. Set `allowUnsandboxedCommands: false` for unattended work. |
| Network allowlist too broad | `*.githubusercontent.com` or a paste site on the list is an exfiltration channel. Review the allowlist like a firewall rule. |
| Interactive CLIs | Agent tool calls time out at the same command every time. Grep traces for timeouts; add non-TTY behavior. |
| Same exit code for every failure | Agent retries caller errors and gives up on transient ones. Distinct exit codes, documented. |
| `llms.txt` that drifts from the docs | Links 404. Generate it from the docs build and link-check it in CI. |

## In your day job
- Write down, for each agent you run, which environment row above it's in and what credentials it can reach. If an unattended agent has write credentials to prod, fix that before anything else in this module.
- Turn on the Claude Code sandbox for your repo, run the probe commands from the docs (`touch ~/sandbox-probe`, `curl --noproxy '*' https://example.com`) to confirm it's enforcing, and set the network allowlist to what your build actually needs.
- Pick your team's most-used internal CLI. Add `--json`, distinct exit codes and non-TTY behavior. Then publish an `llms.txt` for its docs.
