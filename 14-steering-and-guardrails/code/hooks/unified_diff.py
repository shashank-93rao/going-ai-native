"""Minimal unified-diff parser (the output of `git diff`). Stdlib only, so hooks stay dependency-free."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class FileDiff:
    path: str  # new path, or old path when the file was deleted
    old_path: str | None = None
    status: str = "modified"  # "modified" | "added" | "deleted" | "renamed"
    added: list[tuple[int, str]] = field(default_factory=list)  # (new line no, text)
    removed: list[tuple[int, str]] = field(default_factory=list)  # (old line no, text)

    @property
    def churn(self) -> int:
        return len(self.added) + len(self.removed)


def _strip_prefix(p: str) -> str:
    return p[2:] if p.startswith(("a/", "b/")) else p


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    old_no = new_no = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            cur = FileDiff(path=_strip_prefix(parts[-1]), old_path=_strip_prefix(parts[2]))
            files.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("new file mode"):
            cur.status = "added"
        elif line.startswith("deleted file mode"):
            cur.status = "deleted"
            cur.path = cur.old_path or cur.path
        elif line.startswith("rename from "):
            cur.status = "renamed"
        elif line.startswith("--- ") or line.startswith("+++ "):
            continue
        elif m := _HUNK.match(line):
            old_no, new_no = int(m.group(1)), int(m.group(2))
        elif line.startswith("+"):
            cur.added.append((new_no, line[1:]))
            new_no += 1
        elif line.startswith("-"):
            cur.removed.append((old_no, line[1:]))
            old_no += 1
        elif line.startswith(" "):
            old_no += 1
            new_no += 1
    return files
