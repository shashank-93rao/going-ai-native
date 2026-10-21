# Code for module 05

Everything runs offline. From the course root:

```bash
.venv/bin/python -m pytest -q 05-tools-mcp-skills-hooks/code
```

To run a script directly, put the shared kit on the path (the tests do this via the root `conftest.py`):

```bash
cd 05-tools-mcp-skills-hooks/code
export PYTHONPATH=../../shared
AINATIVE_FAKE=1 python agent_loop.py      # drop AINATIVE_FAKE and set ANTHROPIC_API_KEY for a real model
```

| File | What it shows | Run |
|---|---|---|
| `tool_formatter.py` | `ToolError`, `concise`/`detailed` rendering, "N of M" headers, token-budget truncation with guidance, head+tail text truncation | imported by the others |
| `ops_tools.py` | An on-call toolset (deploys, Kafka lag, logs): schemas, implementations, a dispatcher that validates argument names and never raises for model mistakes | imported |
| `query_db_redesign.py` | Before/after for a generic `query_db(q)` tool on a seeded SQLite `payments` table; read-only escape hatch with `PRAGMA query_only` | `python query_db_redesign.py` |
| `agent_loop.py` | A minimal tool loop (max turns, consecutive-error breaker, tracing) and the actionable-vs-opaque error demo | `python agent_loop.py` |
| `code_as_action.py` | Direct calling vs one script for a 295-call lag scan; an `execute_python` tool; footprint measurements | `python code_as_action.py` |
| `deploy_status_mcp.py` | A minimal MCP server for a deploy-status API, with guarded SDK import (v2 `MCPServer`, v1 `FastMCP`) | see below |
| `hooks/block_kubectl_delete.py` | Claude Code `PreToolUse` hook: reads the event JSON on stdin, denies `kubectl delete` in prod contexts, fails closed | see below |
| `hooks/settings.example.json` | The settings block that registers the hook | copy into `.claude/settings.json` |
| `skills/investigate-kafka-consumer-lag/` | A complete skill: `SKILL.md`, `references/`, `scripts/lag_summary.py`, `assets/` template | `python3 skills/.../scripts/lag_summary.py data/describe_poison_partition.txt` |
| `data/*.txt` | `kafka-consumer-groups.sh --describe` fixtures | |

## The scripted model

`agent_loop.scripted_oncall_model` and `code_as_action.scripted_coder` are deterministic policies passed to `FakeClient`. They act only on what the tool results contain (for example, they retry with a name only if the error suggests one). That's enough to show the mechanism in tests. It is not evidence about how often a real model recovers; for that, run with an API key and measure (exercise 2).

## The MCP server

The MCP SDK is **not** installed in the course venv, and the tests don't need it (`test_deploy_status_mcp.py` injects a fake SDK module to test registration). To serve it, use a separate venv:

```bash
python -m venv /tmp/mcpvenv && /tmp/mcpvenv/bin/pip install "mcp[cli]"
/tmp/mcpvenv/bin/mcp dev deploy_status_mcp.py                         # MCP Inspector
claude mcp add deploy-status -- /tmp/mcpvenv/bin/python "$PWD/deploy_status_mcp.py"
```

Set `DEPLOY_API_URL` to point it at a real service exposing `GET /deploys?service=&env=` returning `{"deploys": [...]}`; otherwise it serves fixture data.

## The hook

```bash
mkdir -p .claude/hooks && cp hooks/block_kubectl_delete.py .claude/hooks/
# merge hooks/settings.example.json into .claude/settings.json
echo '{"tool_name":"Bash","tool_input":{"command":"kubectl delete pod x"}}' \
  | HOOK_KUBE_CURRENT_CONTEXT=prod-eu-1 python3 hooks/block_kubectl_delete.py
```

`HOOK_KUBE_CURRENT_CONTEXT` overrides the `kubectl config current-context` lookup (used by the tests). `PROD_CONTEXT_PATTERN` overrides which context names count as prod.

## Safety note

`code_as_action.run_code_action` uses `exec` with trimmed builtins to illustrate the data flow. It is not a sandbox. Exercise 6 replaces it with a container.
