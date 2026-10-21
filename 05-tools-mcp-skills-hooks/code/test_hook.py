import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).parent / "hooks" / "block_kubectl_delete.py"


def run_hook(event, current_context="gke_acme_europe-west1_prod", raw=None):
    env = {**os.environ, "HOOK_KUBE_CURRENT_CONTEXT": current_context}
    p = subprocess.run([sys.executable, str(HOOK)], input=raw if raw is not None else json.dumps(event),
                       capture_output=True, text=True, env=env, timeout=10)
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None
    return p.returncode, out, p.stderr


def bash(cmd):
    return {"session_id": "s1", "cwd": "/repo", "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": cmd, "description": "x"}, "tool_use_id": "toolu_1"}


@pytest.mark.parametrize("cmd", [
    "kubectl delete pod ledger-writer-7d9f-0",
    "kubectl -n payments delete deploy ledger-writer",
    "cd /tmp && kubectl delete ns payments",
    "kubectl get pods | xargs kubectl delete pod",
    "bash -c 'kubectl delete pvc data-0'",
    "sudo /usr/local/bin/kubectl delete node n1",
    "kubectl delete pod x --dry-run=none",
    "KUBECONFIG=~/.kube/other kubectl delete pod x",
])
def test_denies_delete_in_prod_current_context(cmd):
    code, out, _ = run_hook(bash(cmd))
    assert code == 0 and out["permissionDecision"] == "deny"
    assert out["hookEventName"] == "PreToolUse" and "--dry-run=server" in out["permissionDecisionReason"]


@pytest.mark.parametrize("cmd", [
    "kubectl --context=prod-eu-1 delete pod x",
    "kubectl --context production delete pod x",
])
def test_explicit_prod_context_denied_even_from_staging(cmd):
    _, out, _ = run_hook(bash(cmd), current_context="staging")
    assert out["permissionDecision"] == "deny"


@pytest.mark.parametrize("cmd", [
    "kubectl get pods -A",
    "kubectl delete pod x --dry-run=server",
    "kubectl --context staging delete pod x",
    "kubectl --context=preprod-1 delete pod x",
    "echo kubectl delete is dangerous",
    "kubectl describe pod delete-me",
])
def test_allows_safe_commands(cmd):
    code, out, _ = run_hook(bash(cmd))
    assert code == 0 and out is None


def test_echo_mentions_are_not_invocations():
    # `echo kubectl delete` runs echo, not kubectl
    code, out, _ = run_hook(bash("echo 'run kubectl delete later'"))
    assert out is None


def test_unknown_context_asks_a_human():
    _, out, _ = run_hook(bash("kubectl delete pod x"), current_context="")
    assert out["permissionDecision"] == "ask"


def test_unparseable_command_asks():
    _, out, _ = run_hook(bash("kubectl delete pod 'x"))
    assert out["permissionDecision"] == "ask"


def test_other_tools_ignored():
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/x"}}
    assert run_hook(ev)[:2] == (0, None)


def test_garbage_input_fails_closed():
    code, out, err = run_hook(None, raw="not json")
    assert code == 2 and out is None and "invalid hook input" in err


def test_settings_example_is_valid():
    cfg = json.loads((HOOK.parent / "settings.example.json").read_text())
    entry = cfg["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash" and entry["hooks"][0]["type"] == "command"
    assert "block_kubectl_delete.py" in entry["hooks"][0]["command"]


def test_unexpected_input_shape_fails_closed():
    code, out, err = run_hook({"tool_name": "Bash", "tool_input": "kubectl delete pod x"})
    assert code == 2 and out is None and "internal error" in err
