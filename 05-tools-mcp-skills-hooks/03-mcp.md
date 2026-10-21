# 03: MCP: what it is, and when to use it instead of a CLI

## The idea

The Model Context Protocol (MCP) is an open protocol for connecting LLM applications to tools and data. It uses JSON-RPC 2.0 between three roles: **hosts** (the LLM application, such as Claude Code or your agent), **clients** (connectors inside the host, one per server), and **servers** (processes that expose capabilities). The spec says it takes inspiration from the Language Server Protocol: write the integration once, use it from every host ([MCP specification](https://modelcontextprotocol.io/specification/latest)).

That's the entire value proposition: **an integration boundary with a standard wire format**. Your deploy-status API becomes usable from Claude Code, Claude Desktop, your own agents, and any other MCP host, without each team writing its own wrapper. MCP doesn't make tools better. Everything in [01](01-tool-design-as-api-design.md) still applies to the tools you expose through it.

## Why it matters

MCP is how most third-party integrations reach agents, so you'll use it whether or not you build servers. You need to judge two things: whether a given server is worth its context cost, and whether your own integration should be an MCP server or something simpler.

The practitioner pushback is strong and worth taking seriously:
- Simon Willison: "Almost everything I might achieve with an MCP can be handled by a CLI tool instead," because "LLMs know how to call `cli-tool --help`," so you don't pay tokens up front for descriptions ([Willison](https://simonwillison.net/2025/Oct/16/claude-skills/)).
- Armin Ronacher, "Your MCP Doesn't Need 30 Tools: It Needs Code": expose one tool that runs code against retained state, and let MCP do "the thing that it does really well: session management" ([Ronacher](https://lucumr.pocoo.org/2025/8/18/code-mcps/)).

Both are arguments about *how* to use MCP, not against having a standard. The course stance: few curated tools, code-as-action for data-heavy work, and an MCP server when you need what only a server gives you.

## How it works

### Primitives

| Primitive | Who controls it | Use it for |
|---|---|---|
| **Tools** | The model decides when to call | Actions and queries: `deploys_status(service, env)` |
| **Resources** | The application or user attaches them | Context and data addressed by URI: `deploy://ledger-writer/prod/latest` |
| **Prompts** | The user picks them | Templated workflows: "/triage-alert" |
| **Elicitation** (client feature) | Server asks the user via the host | "Which environment?" mid-operation |

The 2025-06-18 revision also defined **sampling** (server asks the host's model for a completion) and **roots** as client features. The 2026-07-28 overview lists only elicitation, so check the revision your host and SDK speak before you rely on the others.

### Transports

Two standard transports ([MCP transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)):
- **stdio**: the host launches the server as a subprocess and exchanges newline-delimited JSON-RPC on stdin/stdout. The server **must not** write anything to stdout that isn't an MCP message; logs go to stderr. One stray `print()` corrupts the stream.
- **Streamable HTTP**: one endpoint (for example `https://deploys.internal/mcp`). Each client message is an HTTP POST, and replies come back as JSON or a request-scoped SSE stream. The spec's security warnings: validate `Origin` (DNS rebinding), bind to `127.0.0.1` when local, and authenticate every connection.

The older HTTP+SSE transport (2024-11-05) is deprecated; Claude Code's docs say to use HTTP servers instead ([Claude Code MCP docs](https://code.claude.com/docs/en/mcp)).

### The 2026 revision went stateless

This is the part a distributed-systems engineer should notice. The 2025-06-18 Streamable HTTP transport had connection-scoped sessions (`initialize` handshake, an `Mcp-Session-Id` header, `404` meaning "start a new session"). That means sticky routing or a shared session store behind a load balancer. The 2026-07-28 revision describes the base protocol as "stateless, self-contained requests" with "per-request capability negotiation": every request carries its protocol version and client capabilities in `_meta` fields, and servers no longer initiate JSON-RPC requests. Bindings handle backward compatibility with initialization-based peers ([MCP spec 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)).

In practice: a 2026-era server is a plain request/response service you can put behind any load balancer and scale horizontally. Long-running work moves to the opt-in **Tasks** extension (polling, durable handles) instead of a held-open session.

### Security model in one paragraph

The spec says hosts must get explicit user consent before invoking tools, and that tool descriptions and annotations "should be considered untrusted, unless obtained from a trusted server." An MCP server is code you run with your credentials, and its descriptions are text that enters your model's context. Treat installing one like adding a dependency with network access. [Module 16](../16-security-and-containment/README.md) covers the lethal-trifecta problem that mixing servers creates.

### MCP, CLI, or code?

| You have | Prefer | Why |
|---|---|---|
| A coding agent with a shell, and the tool already exists as a CLI (`kubectl`, `gh`, `psql`) | **CLI** | Zero definition tokens; the model already knows it; `--help` is the docs. |
| An internal HTTP API many agents and hosts need, with auth | **MCP server** (Streamable HTTP) | One integration, central auth and audit, works in hosts with no shell (desktop, chat). |
| A stateful session (debugger, browser, REPL) | **MCP server with one code tool** | Ronacher's point: MCP holds the session; code composes the actions. |
| Loops over lots of data | **Code-as-action** over the API ([04](04-code-as-action.md)) | Intermediate data never enters the context. |
| A procedure ("how we triage lag") rather than a capability | **Skill** ([05](05-skills.md)) | It's instructions, not an integration. |

## Worked example: a deploy-status MCP server

Situation: your deploy system has an HTTP API (`GET /deploys?service=&env=`). On-call engineers want Claude Code to answer "what changed recently?" during incidents. Other teams want the same thing from their own agents.

### Before: the endpoint mirror

The first version someone writes generates one tool per endpoint and returns raw JSON:

```python
@mcp.tool()
def get_deploys(service_id: str, env_id: str) -> str:
    """GET /deploys"""
    return requests.get(f"{BASE}/deploys", params={"service": service_id, "env": env_id}).text
```

Plus `get_deploy`, `list_envs`, `list_services`, `get_pods`, `get_rollout`, ..., a dozen in all. Problems: the description is the HTTP verb; parameters are IDs the model doesn't have; responses are full JSON with every field; and an unknown service raises `KeyError` inside the handler. In SDK v2 that surfaces to the model as a generic `Error executing tool get_deploys` with the traceback only in your server log. The model can't see why it failed.

### After: two task-shaped tools

From `code/deploy_status_mcp.py` (abridged):

```python
try:  # MCP Python SDK v2
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError as _SDKToolError
except ImportError:
    try:  # SDK v1
        from mcp.server.fastmcp import FastMCP as MCPServer
        from mcp.server.fastmcp.exceptions import ToolError as _SDKToolError
    except ImportError:
        MCPServer, _SDKToolError = None, Exception


class DeployToolError(_SDKToolError):
    """Raised for anything the model can fix; its message reaches the model."""


def deploys_status(service: str, env: str = "prod") -> str:
    """Current and previous deploy of one service in one environment.

    Use this first when an alert might be caused by a recent change. Returns version, status
    (rolling/succeeded/failed/rolled_back), age, pod readiness and the error-rate change since the deploy.
    """
    _check(service, env)  # raises DeployToolError("Unknown service 'payment-api'. Did you mean 'payments-api'? ...")
    ...


def deploys_recent(env: str = "prod", since_minutes: int = 60, limit: int = 10) -> str:
    """Deploys to any service in one environment within the last N minutes, newest first."""
    ...


def build_server():
    server = MCPServer("deploy-status", instructions="Read-only deploy status for prod and staging.")
    for fn in (deploys_status, deploys_recent):
        server.tool()(fn)   # type hints become the input schema; the docstring becomes the description
    return server


if __name__ == "__main__":
    build_server().run(transport="stdio")
```

Design notes:
- **Plain functions first, MCP second.** The tools are ordinary Python functions with tests (`test_deploy_status_mcp.py`). The MCP layer is five lines. The tests inject a fake SDK module to check registration, so they run offline without `mcp` installed.
- **Errors subclass the SDK's `ToolError`**, so the message reaches the model.
- **Infra failures say they're transient**: `deploy API unreachable (...). This is transient; retry once, then report it.`
- **Read-only by construction.** No rollback tool. Rollbacks belong to a different server, attached to a different agent, behind a human approval.

Register and try it:

```bash
pip install "mcp[cli]"
uv run mcp dev code/deploy_status_mcp.py                    # MCP Inspector: call tools by hand
claude mcp add deploy-status -- python /abs/path/code/deploy_status_mcp.py
```

For the whole team, commit a project-scoped `.mcp.json` (Claude Code asks each user to approve project-scoped servers before first use):

```json
{"mcpServers": {"deploy-status": {"command": "python", "args": ["tools/deploy_status_mcp.py"],
                                  "env": {"DEPLOY_API_URL": "${DEPLOY_API_URL}"}}}}
```

In Claude Code the tools appear as `mcp__deploy-status__deploys_status` and `mcp__deploy-status__deploys_recent`. Those names are what hook matchers and subagent `tools:` lists refer to.

A session using it (tool output is real output from the fixture; model text is illustrative):

```text
> ledger-writer lag alert just fired. Did anything ship?

-> mcp__deploy-status__deploys_status(service="ledger-writer", env="prod")
current:  ledger-writer prod v2.14.1 rolling 15m ago pods=7/12 error_rate_delta=+0.4pp id=dpl_9a71 by=priya
previous: ledger-writer prod v2.14.0 succeeded 40m ago pods=12/12 error_rate_delta=+0.0pp id=dpl_8f2c

(illustrative) v2.14.1 is mid-rollout (7/12 pods) and started 15 minutes ago, close to when lag began.
```

**When to move it to Streamable HTTP:** once a second team wants it. Run it as a service with SSO-backed auth, and every host points at one URL (`claude mcp add --transport http deploy-status https://deploys.internal/mcp`). You get one audit log of agent reads, and a single place to fix descriptions.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| `print()` in a stdio server | Host reports parse errors or the server "disconnects" at random. Log to stderr only. |
| Generic exceptions in tools (SDK v2) | The model sees `Error executing tool X` and retries blindly. Grep server logs for tracebacks; raise `ToolError` for fixable cases. |
| Endpoint-mirror servers | Ten or more tools, descriptions that are HTTP verbs, ID parameters. Apply [01](01-tool-design-as-api-design.md). |
| Write tools on a read server | A "status" server that also has `rollback`. Split by risk, attach per agent. |
| Trusting third-party descriptions | A server's description says "always call this tool first." Review descriptions on install and on upgrade; they're prompts. |
| Local HTTP server bound to 0.0.0.0 without Origin checks | Any web page can reach it via DNS rebinding. Bind to localhost, validate `Origin`, authenticate. |
| Assuming session semantics | Code that stores state per `Mcp-Session-Id` breaks against 2026-era clients. Keep tools stateless, or use the Tasks extension for long-running work. |

## In your day job
- Before adding any MCP server to your team's config, count its tools and their definition tokens, and ask whether a CLI already does the job.
- Wrap one internal read-only API your on-call uses as a two- or three-tool MCP server. Plain functions, unit tests, five lines of MCP glue.
- Keep read and write servers separate, and attach write servers only to agents that have a gate in front of them.
