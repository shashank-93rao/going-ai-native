"""Flag agent runs that drift from the plan: out-of-plan files, oversized diffs, loops.

Inputs:
  --plan    plan.json ({"files": [globs], "may_create": [globs], "max_changed_lines": N, ...})
            or PLAN.md (paths listed as bullets under a "## Files" heading)
  --diff    a unified diff file (default: `git diff HEAD`)
  --events  optional JSONL of tool events: {"tool": "Edit", "file": "..."} /
            {"tool": "Bash", "command": "...", "exit_code": 1}

Verdict: ok (exit 0), warn (exit 1, show a human), stop (exit 2, halt the run).

    python drift_monitor.py --plan data/plan.json --diff data/drift_run.diff --events data/run_events.jsonl

--hook mode reads a Stop-hook event on stdin, uses .agent/plan.json, and emits
{"decision": "block"} only on a "stop" verdict; "warn" goes to the human as a systemMessage.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Works both from code/ (helpers in ./hooks) and when copied into .claude/hooks/ next to them.
sys.path[:0] = [str(Path(__file__).resolve().parent / "hooks"), str(Path(__file__).resolve().parent)]
from test_tamper_check import is_test_path  # noqa: E402
from unified_diff import FileDiff, parse_unified_diff  # noqa: E402

DEPENDENCY_FILES = re.compile(r"(^|/)(requirements[\w.-]*\.txt|pyproject\.toml|setup\.py|package\.json|go\.mod|pom\.xml|build\.gradle(\.kts)?|Cargo\.toml|Gemfile)$")
CI_FILES = re.compile(r"(^|/)(\.github/workflows/|\.gitlab-ci\.yml$|Jenkinsfile$|\.circleci/|buildkite)")
SEVERITY = {"ok": 0, "warn": 1, "stop": 2}


@dataclass
class Plan:
    files: list[str]
    may_create: list[str] = field(default_factory=list)
    max_changed_lines: int = 300
    allow_dependency_changes: bool = False
    allow_test_deletions: bool = False
    edit_limit_per_file: int = 6
    repeat_failure_limit: int = 3


@dataclass
class Flag:
    level: str  # "warn" | "stop"
    check: str
    detail: str


@dataclass
class DriftReport:
    verdict: str
    flags: list[Flag]
    changed_files: int
    changed_lines: int

    def render(self) -> str:
        head = f"drift verdict: {self.verdict.upper()}  ({self.changed_files} files, {self.changed_lines} lines changed)"
        return "\n".join([head] + [f"  [{f.level}] {f.check}: {f.detail}" for f in self.flags])


def load_plan(path: Path) -> Plan:
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        known = {k: v for k, v in data.items() if k in Plan.__dataclass_fields__}
        return Plan(**known)
    files, in_section = [], False
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            in_section = line.lstrip("#").strip().lower() == "files"
            continue
        m = re.match(r"\s*[-*]\s+`?([^`\s]+)`?", line)
        if in_section and m:
            files.append(m.group(1))
    return Plan(files=files)


def _matches(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) or path == g for g in globs)


def check_diff(plan: Plan, diffs: list[FileDiff]) -> list[Flag]:
    flags: list[Flag] = []
    for fd in diffs:
        in_plan = _matches(fd.path, plan.files) or (fd.status == "added" and _matches(fd.path, plan.may_create))
        if CI_FILES.search(fd.path) and not in_plan:
            flags.append(Flag("stop", "ci_config_changed", f"{fd.path} is CI config and not in the plan"))
        elif DEPENDENCY_FILES.search(fd.path) and not in_plan and not plan.allow_dependency_changes:
            flags.append(Flag("stop", "dependency_change", f"{fd.path} changed; the plan does not allow new dependencies"))
        elif fd.status == "deleted" and is_test_path(fd.path) and not plan.allow_test_deletions:
            flags.append(Flag("stop", "test_deleted", f"{fd.path} deleted"))
        elif not in_plan:
            flags.append(Flag("warn", "out_of_plan_file", f"{fd.path} ({fd.status}, {fd.churn} lines) is not in the plan"))

    total = sum(fd.churn for fd in diffs)
    if total > 2 * plan.max_changed_lines:
        flags.append(Flag("stop", "diff_size", f"{total} lines changed, more than 2x the budget of {plan.max_changed_lines}"))
    elif total > plan.max_changed_lines:
        flags.append(Flag("warn", "diff_size", f"{total} lines changed, over the budget of {plan.max_changed_lines}"))

    out_of_plan = [f for f in flags if f.check == "out_of_plan_file"]
    if len(out_of_plan) >= 3:
        flags.append(Flag("stop", "scope_creep", f"{len(out_of_plan)} files outside the plan (Beck: functionality nobody asked for)"))
    return flags


def check_events(plan: Plan, events: list[dict]) -> list[Flag]:
    """Beck's first warning sign, loops, from the tool-call stream."""
    flags: list[Flag] = []
    edits = Counter(e.get("file") for e in events if e.get("tool") in ("Edit", "Write", "MultiEdit") and e.get("file"))
    for path, n in edits.items():
        if n > plan.edit_limit_per_file:
            flags.append(Flag("warn", "edit_loop", f"{path} edited {n} times (limit {plan.edit_limit_per_file})"))
    streak, last = 0, None
    for e in events:
        if e.get("tool") != "Bash":
            continue
        key = (e.get("command"), e.get("exit_code"))
        if e.get("exit_code", 0) != 0 and key == last:
            streak += 1
        else:
            streak = 1 if e.get("exit_code", 0) != 0 else 0
        last = key
        if streak == plan.repeat_failure_limit:
            flags.append(Flag("stop", "repeated_failure", f"`{e.get('command')}` failed {streak} consecutive runs; the edits in between are not converging"))
    return flags


def analyze(plan: Plan, diff_text: str, events: list[dict] | None = None) -> DriftReport:
    diffs = parse_unified_diff(diff_text)
    flags = check_diff(plan, diffs) + check_events(plan, events or [])
    verdict = max((f.level for f in flags), key=SEVERITY.__getitem__, default="ok")
    return DriftReport(verdict, flags, len(diffs), sum(fd.churn for fd in diffs))


def _read_events(path: Path | None) -> list[dict]:
    if not path:
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _git_diff(root: Path) -> str:
    return subprocess.run(["git", "diff", "HEAD", "--"], cwd=root, capture_output=True, text=True).stdout


def hook_main(stdin_text: str, root: Path) -> dict | None:
    event = json.loads(stdin_text or "{}")
    plan_path = root / ".agent" / "plan.json"
    if not plan_path.exists():
        return None
    report = analyze(load_plan(plan_path), _git_diff(root))
    if report.verdict == "stop" and not event.get("stop_hook_active"):
        return {"decision": "block", "reason": report.render() + "\nRevert the out-of-scope changes, or stop and ask the user to extend the plan."}
    if report.verdict != "ok":
        return {"systemMessage": report.render()}  # to the human, not the agent
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flag agent runs that drift from the plan")
    ap.add_argument("--plan")
    ap.add_argument("--diff")
    ap.add_argument("--events")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hook", action="store_true", help="run as a Claude Code Stop hook")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.hook:
        out = hook_main(sys.stdin.read(), root)
        if out:
            print(json.dumps(out))
        return 0
    if not args.plan:
        ap.error("--plan is required unless --hook")
    diff_text = Path(args.diff).read_text() if args.diff else _git_diff(root)
    report = analyze(load_plan(Path(args.plan)), diff_text, _read_events(Path(args.events) if args.events else None))
    print(json.dumps(asdict(report), indent=2) if args.json else report.render())
    return SEVERITY[report.verdict]


if __name__ == "__main__":
    sys.exit(main())
