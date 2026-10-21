"""PreToolUse guard for Claude Code: deny dangerous commands, ask on risky ones.

Wire it in .claude/settings.json under hooks.PreToolUse with matcher "Bash|Edit|Write|MultiEdit".
It reads the hook event JSON on stdin and, when a rule matches, prints:

    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny" | "ask",
                            "permissionDecisionReason": "..."}}

For "deny" the reason is shown to Claude, so every reason says what to do instead.
No match means no output and exit 0: normal permission rules decide.

Scope, honestly: regexes over a shell string catch an *overeager* agent's mistakes
(the auto-mode threat model's first two items). They do not stop an adversary,
who can write `python -c`, base64, or a script file. Containment is module 16's job.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    decision: str  # "deny" | "ask"
    reason: str


def _r(p: str) -> re.Pattern[str]:
    return re.compile(p.replace("GIT ", _GIT), re.IGNORECASE)


# "git", then optional global options (-C dir, -c k=v, --no-pager...), then the subcommand.
# Without this, `git -C . push` slips past a naive `git\s+push` (the docs' own example).
_GIT = r"\bgit(?:\s+-[Cc]\s+\S+|\s+--[\w-]+(?:=\S+)?)*\s+['\"]?"


BASH_RULES: list[Rule] = [
    Rule("rm_rf_broad", _r(r"\brm\s+(-[a-z]*r[a-z]*f[a-z]*|-[a-z]*f[a-z]*r[a-z]*|-r\s+-f|-f\s+-r)\s+(--\s+)?(/|~|\$HOME|\.{1,2}|\*)(/?\*?)?(\s|$|;|&)"),
         "deny", "Recursive force-delete of a root, home, parent or wildcard path. Delete specific paths instead."),
    Rule("force_push_main", _r(r"GIT push\b.*(--force\b|-f\b|--force-with-lease\b).*\b(main|master|release[\w/-]*)\b|GIT push\b.*\+(main|master)\b"),
         "deny", "Force-push to a protected branch. Push to a feature branch and open a PR."),
    Rule("force_push", _r(r"GIT push\b.*(--force\b|-f\b)"),
         "ask", "Force-push rewrites remote history; a human should confirm."),
    Rule("no_verify", _r(r"--no-verify\b|GIT commit\b.*\s-n\b|HUSKY=0|SKIP=\S*pre-commit"),
         "deny", "Bypassing git hooks is not allowed. Fix what the hook reports, then commit normally."),
    Rule("reset_hard", _r(r"GIT (reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s+\.|restore\s+(--staged\s+)?\.(\s|$))"),
         "deny", "This discards uncommitted work. Use `git stash` or revert specific files."),
    Rule("pipe_to_shell", _r(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b"),
         "deny", "Piping a download into a shell runs unreviewed code. Download, inspect, then run."),
    Rule("chmod_777", _r(r"\bchmod\s+(-R\s+)?0?777\b"),
         "deny", "World-writable permissions. Grant the narrowest mode that works."),
    Rule("sql_destructive", _r(r"\b(drop\s+(table|database|schema)|truncate\s+table)\b|\bdelete\s+from\s+\w+\s*(;|$|\"|')"),
         "deny", "Destructive SQL. Write a migration with a rollback and get it reviewed."),
    Rule("test_deselect", _r(r"\b(pytest|py\.test)\b.*(--deselect\b|\s-k\s+['\"]?not\b|--ignore\b)|\bgo\s+test\b.*-skip\b"),
         "deny", "Deselecting tests hides failures. Run the full suite and fix the failing test's cause."),
    Rule("read_secrets", _r(r"\b(cat|less|head|tail|grep|base64)\b[^|;&]*(\.env(?!\.example)\b|id_rsa|\.pem\b|credentials\.json)|^\s*(printenv|env)\s*$"),
         "deny", "Reading secrets into the transcript. Reference the variable name; never print its value."),
    Rule("infra_change", _r(r"\b(terraform\s+(apply|destroy)|kubectl\s+(apply|delete|drain|scale|rollout\s+undo)|helm\s+(install|upgrade|uninstall|rollback))\b"),
         "ask", "Infrastructure change: this is a human-approval tier action."),
    Rule("git_push", _r(r"GIT push\b"), "ask", "Publishing to a remote; confirm the branch and contents."),
]

# Paths the agent must never write: secrets, VCS internals, lockfiles, and its own guardrails.
PROTECTED_PATHS: list[tuple[re.Pattern[str], str]] = [
    (_r(r"(^|/)\.env(\.(?!example)[\w.]+)?$|\.pem$|(^|/)id_rsa|(^|/)secrets?/"), "Secrets file. Edit the template (.env.example) instead."),
    (_r(r"(^|/)\.git/"), "Git internals. Use git commands."),
    (_r(r"(^|/)\.claude/(settings(\.local)?\.json|hooks/|state/)"), "The agent may not edit its own guardrails or their state. Ask the human."),
    (_r(r"(^|/)\.agent/approved-test-changes\.txt$"), "Test-change approvals are written by a human only."),
    (_r(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock|go\.sum|Cargo\.lock)$"),
     "Lockfile. Change dependencies with the package manager, not by hand."),
]
_WRITE_OPS = _r(r"(>>?|\btee\b|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b|\btruncate\b|\bchmod\b|\bln\b)")
_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _protected(path: str) -> str | None:
    for pat, reason in PROTECTED_PATHS:
        if pat.search(path):
            return reason
    return None


def decide(event: dict) -> tuple[str, str, str] | None:
    """Return (decision, rule_name, reason) or None. Deny wins over ask (most restrictive first)."""
    tool = event.get("tool_name", "")
    tin = event.get("tool_input", {}) or {}
    hits: list[tuple[str, str, str]] = []
    if tool == "Bash":
        cmd = str(tin.get("command", ""))
        for rule in BASH_RULES:
            if rule.pattern.search(cmd):
                hits.append((rule.decision, rule.name, rule.reason))
        if _WRITE_OPS.search(cmd):
            for token in re.split(r"[\s;&|<>'\"]+", cmd):
                reason = _protected(token)
                if reason:
                    hits.append(("deny", "protected_path_shell", f"{token}: {reason}"))
                    break
    elif tool in _FILE_TOOLS:
        path = str(tin.get("file_path") or tin.get("notebook_path") or "")
        reason = _protected(path)
        if reason:
            hits.append(("deny", "protected_path", f"{path}: {reason}"))
    if not hits:
        return None
    hits.sort(key=lambda h: 0 if h[0] == "deny" else 1)
    return hits[0]


def hook_output(decision: str, rule: str, reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[guard:{rule}] {reason}",
        }
    }


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        # Fail closed: a guard that can't read its input must not wave the call through.
        print(f"pre_tool_guard: unreadable hook input ({e}); blocking", file=sys.stderr)
        return 2
    result = decide(event)
    if result:
        print(json.dumps(hook_output(*result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
