"""A minimal MCP server wrapping an internal deploy-status API.

Install the SDK to actually serve it (not needed for the tests):
    pip install "mcp[cli]"
    python deploy_status_mcp.py                       # stdio: the client launches this as a subprocess
    claude mcp add deploy-status -- python /abs/path/deploy_status_mcp.py

Written against the MCP Python SDK v2 (`from mcp.server import MCPServer`), with a fallback to
v1 (`from mcp.server.fastmcp import FastMCP`). In SDK v2 only a `ToolError`'s message reaches
the model; any other exception is reported as a generic "Error executing tool <name>". So every
fixable failure below raises ToolError with a message written for the model.

The backend is `DeployAPI`. By default it serves fixture data; set DEPLOY_API_URL to point it
at a real HTTP service exposing GET /deploys?service=&env= (shape documented in `_fetch`).
"""

from __future__ import annotations

import difflib
import json
import os
import urllib.parse
import urllib.request
from typing import Any

try:  # SDK v2
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError as _SDKToolError
except ImportError:  # pragma: no cover - depends on the installed SDK
    try:  # SDK v1
        from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]
        from mcp.server.fastmcp.exceptions import ToolError as _SDKToolError  # type: ignore[no-redef]
    except ImportError:
        MCPServer = None  # type: ignore[assignment,misc]
        _SDKToolError = Exception  # type: ignore[assignment,misc]

MCP_AVAILABLE = MCPServer is not None
NOW = 1_760_000_000


class DeployToolError(_SDKToolError):  # type: ignore[misc,valid-type]
    """Raised for anything the model can fix. Subclasses the SDK's ToolError when available."""


FIXTURE: list[dict[str, Any]] = [
    {"id": "dpl_9a71", "service": "ledger-writer", "env": "prod", "version": "v2.14.1", "status": "rolling",
     "started_at": NOW - 900, "pods_ready": 7, "pods_total": 12, "error_rate_delta_pct": 0.4, "author": "priya"},
    {"id": "dpl_8f2c", "service": "ledger-writer", "env": "prod", "version": "v2.14.0", "status": "succeeded",
     "started_at": NOW - 2400, "pods_ready": 12, "pods_total": 12, "error_rate_delta_pct": 0.0, "author": "ci-bot"},
    {"id": "dpl_77d0", "service": "payments-api", "env": "prod", "version": "v5.3.2", "status": "succeeded",
     "started_at": NOW - 86400, "pods_ready": 30, "pods_total": 30, "error_rate_delta_pct": -0.1, "author": "ci-bot"},
    {"id": "dpl_1b3e", "service": "payments-api", "env": "staging", "version": "v5.4.0-rc1", "status": "failed",
     "started_at": NOW - 3000, "pods_ready": 0, "pods_total": 3, "error_rate_delta_pct": None, "author": "ci-bot",
     "failure": "readiness probe timeout"},
]
ENVS = ("prod", "staging")


class DeployAPI:
    def __init__(self, base_url: str | None = None, fixture: list[dict[str, Any]] | None = None):
        self.base_url = base_url
        self.fixture = FIXTURE if fixture is None else fixture

    def _fetch(self, service: str | None, env: str) -> list[dict[str, Any]]:
        """Real mode expects JSON: {"deploys": [ {id, service, env, version, status, started_at, ...} ]}."""
        if not self.base_url:
            return [d for d in self.fixture if d["env"] == env and (service is None or d["service"] == service)]
        q = urllib.parse.urlencode({k: v for k, v in {"service": service, "env": env}.items() if v})
        try:
            with urllib.request.urlopen(f"{self.base_url}/deploys?{q}", timeout=5) as r:
                return json.load(r)["deploys"]
        except OSError as e:  # surface infra failures as retryable, not as the model's fault
            raise DeployToolError(f"deploy API unreachable ({e}). This is transient; retry once, then report it.")

    def services(self) -> list[str]:
        return sorted({d["service"] for env in ENVS for d in self._fetch(None, env)})


API = DeployAPI(os.environ.get("DEPLOY_API_URL"))


def _check(service: str, env: str) -> None:
    if env not in ENVS:
        raise DeployToolError(f"env must be one of {list(ENVS)}, got {env!r}.")
    known = API.services()
    if service not in known:
        close = difflib.get_close_matches(service, known, n=1, cutoff=0.4)
        hint = f"Did you mean {close[0]!r}? " if close else ""
        raise DeployToolError(f"Unknown service {service!r}. {hint}Known services: {known}.")


def _line(d: dict[str, Any]) -> str:
    age = (NOW - d["started_at"]) // 60
    s = f"{d['service']} {d['env']} {d['version']} {d['status']} {age}m ago pods={d['pods_ready']}/{d['pods_total']}"
    if d.get("error_rate_delta_pct") is not None:
        s += f" error_rate_delta={d['error_rate_delta_pct']:+.1f}pp"
    if d.get("failure"):
        s += f" failure={d['failure']!r}"
    return s


# ---------------------------------------------------------------- tool functions (plain, testable)

def deploys_status(service: str, env: str = "prod") -> str:
    """Current and previous deploy of one service in one environment.

    Use this first when an alert might be caused by a recent change. Returns version, status
    (rolling/succeeded/failed/rolled_back), age, pod readiness and the error-rate change since the deploy.
    """
    _check(service, env)
    rows = sorted(API._fetch(service, env), key=lambda d: -d["started_at"])
    if not rows:
        return f"No deploys of {service} in {env}."
    out = [f"current:  {_line(rows[0])} id={rows[0]['id']} by={rows[0]['author']}"]
    if len(rows) > 1:
        out.append(f"previous: {_line(rows[1])} id={rows[1]['id']}")
    return "\n".join(out)


def deploys_recent(env: str = "prod", since_minutes: int = 60, limit: int = 10) -> str:
    """Deploys to any service in one environment within the last N minutes, newest first.

    Use this to answer "what changed recently?" during an incident.
    """
    if env not in ENVS:
        raise DeployToolError(f"env must be one of {list(ENVS)}, got {env!r}.")
    if not 1 <= since_minutes <= 10080:
        raise DeployToolError(f"since_minutes must be 1..10080 (7 days), got {since_minutes}.")
    if not 1 <= limit <= 50:
        raise DeployToolError(f"limit must be 1..50, got {limit}.")
    rows = sorted((d for d in API._fetch(None, env) if d["started_at"] >= NOW - since_minutes * 60),
                  key=lambda d: -d["started_at"])
    if not rows:
        return f"No deploys in {env} in the last {since_minutes}m. Widen since_minutes to look further back."
    shown = rows[:limit]
    more = f"\n[{len(rows) - limit} more; raise limit or narrow since_minutes]" if len(rows) > limit else ""
    return f"{len(shown)} of {len(rows)} deploys in {env}, last {since_minutes}m:\n" + "\n".join(map(_line, shown)) + more


TOOLS = [deploys_status, deploys_recent]


def build_server() -> Any:
    """Create the MCP server and register the tools. Type hints + docstrings become the tool schema."""
    if not MCP_AVAILABLE:
        raise RuntimeError('The MCP SDK is not installed. Run: pip install "mcp[cli]"')
    server = MCPServer("deploy-status", instructions="Read-only deploy status for prod and staging.")
    for fn in TOOLS:
        server.tool()(fn)
    return server


if __name__ == "__main__":  # pragma: no cover
    build_server().run(transport="stdio")
