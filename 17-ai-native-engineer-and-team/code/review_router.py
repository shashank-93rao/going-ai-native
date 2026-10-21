"""Route a diff to a review tier: how many humans, which owners, how many verifiers.

    python review_router.py data/diffs/raft_election.diff
    git diff main... | python review_router.py - --untrusted

The policy (data/review_policy.json) is a list of rules. A rule matches a file
when its path globs match AND, if it has content patterns, at least one changed
line matches. A file's tier is the highest tier among its matching rules; a file
no rule matches gets `default_tier` (fail safe: unknown means medium, not low).
The diff's tier is the highest file tier, then escalations apply.

This is deterministic on purpose. Anthropic's Claude Code team uses a model to
pick the tier; a path-and-pattern router is the floor under that model: it is
cheap, explainable, and testable, and a model classifier may only raise its tier.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

TIER_ORDER = {"low": 0, "medium": 1, "high": 2}
DEFAULT_POLICY = Path(__file__).parent / "data" / "review_policy.json"
_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


@dataclass
class FileChange:
    path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def changed_lines(self) -> int:
        return len(self.added) + len(self.removed)


@dataclass
class Rule:
    name: str
    tier: str
    paths: list[str] = field(default_factory=list)
    added_patterns: list[str] = field(default_factory=list)
    removed_patterns: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    always_human: bool = False
    reason: str = ""

    def matches(self, fc: FileChange) -> bool:
        if self.paths and not any(fnmatch.fnmatch(fc.path, g) for g in self.paths):
            return False
        if not self.added_patterns and not self.removed_patterns:
            return True
        hit_added = any(re.search(p, line) for p in self.added_patterns for line in fc.added)
        hit_removed = any(re.search(p, line) for p in self.removed_patterns for line in fc.removed)
        return hit_added or hit_removed


@dataclass
class RoutingDecision:
    tier: str
    human_approvals: int
    verifiers: int
    round_cap: int
    owners: list[str]
    reasons: list[str]
    file_tiers: dict[str, str]
    # Fixed rules from the course policy, carried in the output so tooling can enforce them.
    agent_approval_counts_as_human: bool = False
    approval_scope: str = "commit"  # a new commit needs a new approval

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_prefix(p: str) -> str:
    p = p.split("\t")[0].strip()
    return p[2:] if p.startswith(("a/", "b/")) else p


def parse_unified_diff(diff: str) -> list[FileChange]:
    """Parse `git diff` or plain unified diff text into per-file added/removed lines.

    Hunk line counts are tracked, so a removed SQL comment ("--- foo") inside a
    hunk is not mistaken for a file header.
    """
    files: list[FileChange] = []
    cur: FileChange | None = None
    old_path: str | None = None
    git_header_open = False
    old_left = new_left = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:  # inside a hunk
            tag, body = line[:1], line[1:]
            if tag == "+":
                new_left -= 1
                cur.added.append(body)  # type: ignore[union-attr]
            elif tag == "-":
                old_left -= 1
                cur.removed.append(body)  # type: ignore[union-attr]
            elif tag == "\\":  # "\ No newline at end of file"
                pass
            else:
                old_left -= 1
                new_left -= 1
            continue
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            cur = FileChange(m.group(2) if m else line.split()[-1])
            files.append(cur)
            git_header_open = True
        elif line.startswith("--- "):
            old_path = _strip_prefix(line[4:])
        elif line.startswith("+++ "):
            new_path = _strip_prefix(line[4:])
            if not git_header_open:
                path = old_path if new_path == "/dev/null" and old_path else new_path
                cur = FileChange(path)
                files.append(cur)
            git_header_open = False
        elif (m := _HUNK.match(line)) and cur is not None:
            old_left = int(m.group(1)) if m.group(1) is not None else 1
            new_left = int(m.group(2)) if m.group(2) is not None else 1
            git_header_open = False
    return files


def load_policy(path: str | Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _rules(policy: dict[str, Any]) -> list[Rule]:
    return [Rule(**r) for r in policy["rules"]]


def _max_tier(a: str, b: str) -> str:
    return a if TIER_ORDER[a] >= TIER_ORDER[b] else b


def route(diff: str | list[FileChange], policy: dict[str, Any] | None = None, *, trusted_author: bool = True) -> RoutingDecision:
    """Classify a diff and return the review it requires."""
    policy = policy or load_policy()
    files = parse_unified_diff(diff) if isinstance(diff, str) else diff
    rules = _rules(policy)
    default = policy.get("default_tier", "medium")
    reasons: list[str] = []
    owners: set[str] = set()
    file_tiers: dict[str, str] = {}
    always_human = False
    tier = "low"

    if not files:
        tier = default
        reasons.append(f"no parseable file changes: default tier {default}")
    for fc in files:
        hits = [r for r in rules if r.matches(fc)]
        if not hits:
            ftier = default
            reasons.append(f"{fc.path}: no rule matched -> default {default}")
        else:
            ftier = "low"
            for r in hits:
                ftier = _max_tier(ftier, r.tier)
                owners.update(r.owners)
                always_human = always_human or r.always_human
                reasons.append(f"{fc.path}: {r.name} ({r.tier}) - {r.reason}")
        file_tiers[fc.path] = ftier
        tier = _max_tier(tier, ftier)

    total = sum(f.changed_lines for f in files)
    if tier == "low" and total > policy.get("large_diff_lines", 400):
        tier = "medium"
        reasons.append(f"escalated: {total} changed lines exceeds large_diff_lines")
    if tier == "low" and not trusted_author:
        tier = "medium"
        reasons.append("escalated: the zero-human path is only for trusted authors")

    req = policy["tiers"][tier]
    humans = req["human_approvals"]
    if always_human and humans < 1:
        humans = 1
        reasons.append("always-human path touched: at least one human approval")
    return RoutingDecision(
        tier=tier,
        human_approvals=humans,
        verifiers=req["verifiers"],
        round_cap=req["round_cap"],
        owners=sorted(owners),
        reasons=reasons,
        file_tiers=file_tiers,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("diff", help="path to a unified diff, or - for stdin")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--untrusted", action="store_true", help="author is outside the owning team")
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text()
    decision = route(text, load_policy(args.policy), trusted_author=not args.untrusted)
    print(json.dumps(decision.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
