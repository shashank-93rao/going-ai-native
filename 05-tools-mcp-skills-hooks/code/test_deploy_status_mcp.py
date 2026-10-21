import importlib
import sys
import types

import pytest

import deploy_status_mcp as dsm


def test_status_current_and_previous():
    out = dsm.deploys_status("ledger-writer")
    assert out.startswith("current:  ledger-writer prod v2.14.1 rolling 15m ago pods=7/12")
    assert "previous: ledger-writer prod v2.14.0" in out


def test_unknown_service_suggests():
    with pytest.raises(dsm.DeployToolError, match="Did you mean 'payments-api'"):
        dsm.deploys_status("payment-api")
    with pytest.raises(dsm.DeployToolError, match="env must be one of"):
        dsm.deploys_status("payments-api", env="production")


def test_recent_window_and_limits():
    out = dsm.deploys_recent(since_minutes=60)
    assert out.startswith("2 of 2 deploys in prod") and "payments-api" not in out
    assert "Widen since_minutes" in dsm.deploys_recent(env="staging", since_minutes=5)
    with pytest.raises(dsm.DeployToolError, match="limit must be"):
        dsm.deploys_recent(limit=0)


def test_unreachable_api_is_reported_as_transient(monkeypatch):
    monkeypatch.setattr(dsm, "API", dsm.DeployAPI("http://127.0.0.1:9"))
    with pytest.raises(dsm.DeployToolError, match="transient"):
        dsm.deploys_recent()


def test_build_server_without_sdk_explains_install(monkeypatch):
    monkeypatch.setattr(dsm, "MCP_AVAILABLE", False)
    with pytest.raises(RuntimeError, match='pip install "mcp\\[cli\\]"'):
        dsm.build_server()


def test_registers_tools_with_a_fake_v2_sdk(monkeypatch):
    """Stand-in for the SDK so the registration path runs offline."""
    registered = {}

    class FakeMCPServer:
        def __init__(self, name, instructions=None):
            self.name, self.instructions = name, instructions

        def tool(self):
            def deco(fn):
                registered[fn.__name__] = fn
                return fn
            return deco

    class FakeToolError(Exception):
        pass

    server_mod = types.ModuleType("mcp.server")
    server_mod.MCPServer = FakeMCPServer
    exc_mod = types.ModuleType("mcp.server.mcpserver.exceptions")
    exc_mod.ToolError = FakeToolError
    for name, mod in {"mcp": types.ModuleType("mcp"), "mcp.server": server_mod,
                      "mcp.server.mcpserver": types.ModuleType("mcp.server.mcpserver"),
                      "mcp.server.mcpserver.exceptions": exc_mod}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    try:
        mod = importlib.reload(dsm)
        server = mod.build_server()
        assert server.name == "deploy-status"
        assert set(registered) == {"deploys_status", "deploys_recent"}
        assert all(fn.__doc__ and len(fn.__doc__) > 40 for fn in registered.values())  # docstring = tool description
        with pytest.raises(FakeToolError):  # so the SDK forwards our message to the model
            mod.deploys_status("nope")
    finally:
        monkeypatch.undo()
        importlib.reload(dsm)
