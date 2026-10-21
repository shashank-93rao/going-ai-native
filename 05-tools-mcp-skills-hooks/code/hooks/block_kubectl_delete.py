#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block `kubectl delete` against production contexts.

Claude Code runs this before every Bash tool call (see settings.example.json) and writes one
JSON object to stdin: {"session_id", "cwd", "hook_event_name": "PreToolUse", "tool_name": "Bash",
"tool_input": {"command": "..."}, ...}.

Decisions are returned as JSON on stdout with exit 0:
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny" | "ask",
                            "permissionDecisionReason": "<shown to Claude>"}}
No output + exit 0 means "no opinion": the normal permission flow continues.
Unreadable input exits 2 (blocking), so a broken hook fails closed.

Which context is "prod":
  - an explicit `--context X` / `--context=X` on the command line, else
  - the current kubectl context (`kubectl config current-context`), overridable for tests
    with HOOK_KUBE_CURRENT_CONTEXT.
  - names matching PROD_CONTEXT_PATTERN (default: a `prod`/`production` segment).
If the context can't be determined, the hook asks a human instead of guessing.

This is a guardrail against mistakes, not a security boundary: an agent determined to delete
can write a Python script that calls the API. Real protection is RBAC on the agent's
credentials (see ../16-security-and-containment/).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

PROD_PATTERN = re.compile(os.environ.get("PROD_CONTEXT_PATTERN", r"(^|[-_./:@])prod(uction)?($|[-_./:@])"), re.I)
SEPARATORS = {"&&", "||", ";", "|", "&", "\n", "(", ")"}
SHELLS = {"sh", "bash", "zsh", "dash"}
WRAPPERS = {"sudo", "env", "xargs", "timeout", "nohup", "time", "nice", "watch", "exec", "command", "doas"}
# kubectl global flags that consume the next token as their value
VALUE_FLAGS = {"--context", "--namespace", "-n", "--kubeconfig", "--cluster", "--user", "-s", "--server",
               "--token", "--as", "--request-timeout", "-l", "--selector", "-o", "--output", "-f", "--filename"}


def segments(command: str) -> list[list[str]]:
    """Split a shell command into simple commands, recursing into `bash -c '...'`."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace_split = True
    out: list[list[str]] = [[]]
    for tok in lex:
        if tok in SEPARATORS or set(tok) <= set(";&|()\n"):
            out.append([])
        else:
            out[-1].append(tok)
    result: list[list[str]] = []
    for seg in filter(None, out):
        base = os.path.basename(seg[0])
        if base in SHELLS and "-c" in seg[1:] and seg.index("-c") + 1 < len(seg):
            result.extend(segments(seg[seg.index("-c") + 1]))
        else:
            result.append(seg)
    return result


def kubectl_invocation(seg: list[str]) -> list[str] | None:
    """Return kubectl's argv (after `kubectl`) if this simple command runs kubectl, else None.

    Skips known wrappers (`sudo`, `env A=B`, `xargs -n1`, `timeout 30s`, ...) before the binary, so
    `echo kubectl delete` (an argument, not an invocation) is not flagged. Unknown wrappers are a
    false-negative risk; add them to WRAPPERS when you see them in transcripts.
    """
    for i, tok in enumerate(seg):
        base = os.path.basename(tok)
        if base in ("kubectl", "kubectl.exe"):
            return seg[i + 1:]
        is_assignment = "=" in tok and not tok.startswith("-")
        is_wrapper_arg = i > 0 and (tok.startswith("-") or re.fullmatch(r"\d+[smhd]?", tok) is not None)
        if not (base in WRAPPERS or is_assignment or is_wrapper_arg):
            return None
    return None


def parse_kubectl(args: list[str]) -> tuple[str | None, str | None, str | None]:
    """Return (verb, explicit_context, dry_run_value)."""
    verb = context = dry_run = None
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--context="):
            context = a.split("=", 1)[1]
        elif a == "--context" and i + 1 < len(args):
            context = args[i + 1]; i += 1
        elif a.startswith("--dry-run"):
            dry_run = a.split("=", 1)[1] if "=" in a else "client"
        elif a in VALUE_FLAGS:
            i += 1
        elif not a.startswith("-") and verb is None:
            verb = a
        i += 1
    return verb, context, dry_run


def current_context() -> str | None:
    if "HOOK_KUBE_CURRENT_CONTEXT" in os.environ:
        return os.environ["HOOK_KUBE_CURRENT_CONTEXT"] or None
    try:
        r = subprocess.run(["kubectl", "config", "current-context"], capture_output=True, text=True, timeout=3)
        return (r.stdout.strip() or None) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def decide(command: str) -> tuple[str, str] | None:
    """Return (decision, reason) or None for no opinion."""
    try:
        segs = segments(command)
    except ValueError:  # unbalanced quotes etc.: only care if it smells like a kubectl delete
        if "kubectl" in command and "delete" in command:
            return "ask", "Could not parse this command to check whether it deletes in prod. A human must approve it."
        return None
    for seg in segs:
        args = kubectl_invocation(seg)
        if args is None:
            continue
        verb, ctx, dry_run = parse_kubectl(args)
        if verb != "delete" or dry_run in ("client", "server"):
            continue
        ctx = ctx or current_context()
        if ctx is None:
            return "ask", ("kubectl delete with an unknown kube context (no --context, and the current context could "
                           "not be read). A human must approve it.")
        if PROD_PATTERN.search(ctx):
            return "deny", (f"Blocked by policy: `kubectl delete` in production context {ctx!r}. Do not retry with "
                            "different syntax. Instead: (1) run the same command with --dry-run=server and show the "
                            "output, then (2) give the user the exact command to run themselves.")
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"block_kubectl_delete: invalid hook input: {e}", file=sys.stderr)
        return 2  # fail closed: blocks the tool call, stderr is shown to Claude
    if event.get("tool_name") != "Bash":
        return 0
    verdict = decide(str(event.get("tool_input", {}).get("command", "")))
    if verdict:
        decision, reason = verdict
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # an uncaught crash exits 1, which Claude Code treats as NON-blocking: fail closed instead
        print(f"block_kubectl_delete: internal error: {e!r}", file=sys.stderr)
        sys.exit(2)
