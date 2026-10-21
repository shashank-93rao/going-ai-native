"""Seeded task suite: load task definitions, build per-task workspaces, apply edits.

A task lives in tasks/<id>/ with:
  task.toml       id, kind (feature|bug|incident), prompt, needs, and edit lists:
                  `inject` (the bug), `solution` (reference fix), `naive` (a plausible wrong fix,
                  or `naive_drops`: indexes of solution edits to leave out)
  hidden_checks.py  graded after the agent finishes; never visible to the agent
  incident.jsonl  (incidents only) logs from the incident window, placed at var/log/orders.jsonl

Edits are exact search/replace operations, so a stale edit fails loudly instead of
silently applying to the wrong code: {file, find, replace} | {file, append} | {file, create}.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SERVICE = HERE / "sample_service"
TASKS = HERE / "tasks"

# Harness components that can be removed for ablation runs. Paths are relative to the repo copy.
ABLATIONS: dict[str, list[str]] = {
    "agents_md": ["AGENTS.md", "orders/AGENTS.md"],
    "invariants": ["INVARIANTS.md"],
    "architecture": ["ARCHITECTURE.md", "docs"],
    "lint": ["tools/lint_invariants.py"],
    "diagnose": ["tools/diagnose.py"],
    "repro": ["tools/repro.py"],
    "skills": [".claude"],
}
PROTECTED = ["conftest.py", "tests/test_orders_api.py", "tests/test_orders_pipeline.py"]
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "var")


class EditError(Exception):
    pass


@dataclass
class Task:
    id: str
    kind: str
    prompt: str
    dir: Path
    needs: list[str] = field(default_factory=list)
    inject: list[dict[str, Any]] = field(default_factory=list)
    solution: list[dict[str, Any]] = field(default_factory=list)
    naive: list[dict[str, Any]] = field(default_factory=list)

    @property
    def hidden_test(self) -> Path:
        return self.dir / "hidden_checks.py"

    @property
    def incident_log(self) -> Path | None:
        p = self.dir / "incident.jsonl"
        return p if p.exists() else None

    def reference_fix(self) -> list[dict[str, Any]]:
        """Bugs and incidents default to reverting the injected edit."""
        return self.solution or invert(self.inject)


def load_tasks(tasks_dir: Path = TASKS, only: list[str] | None = None) -> list[Task]:
    tasks = []
    for f in sorted(tasks_dir.glob("*/task.toml")):
        d = tomllib.loads(f.read_text())
        solution = d.get("solution", [])
        naive = d.get("naive", [])
        if "naive_drops" in d:  # naive fix = reference fix minus the edits that preserve an invariant
            naive = [e for i, e in enumerate(solution) if i not in d["naive_drops"]]
        t = Task(id=d["id"], kind=d["kind"], prompt=d["prompt"].strip(), dir=f.parent, needs=d.get("needs", []),
                 inject=d.get("inject", []), solution=solution, naive=naive)
        if t.kind not in ("feature", "bug", "incident"):
            raise ValueError(f"{t.id}: unknown kind {t.kind}")
        if not only or t.id in only:
            tasks.append(t)
    return tasks


def invert(edits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in reversed(edits):
        if "find" not in e:
            raise EditError(f"cannot invert non-replace edit on {e['file']}")
        out.append({"file": e["file"], "find": e["replace"], "replace": e["find"]})
    return out


def apply_edits(root: Path, edits: list[dict[str, Any]]) -> None:
    for e in edits:
        path = root / e["file"]
        if "create" in e:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(e["create"])
            continue
        if not path.exists():
            raise EditError(f"{e['file']}: file not found")
        src = path.read_text()
        if "append" in e:
            path.write_text(src.rstrip("\n") + "\n\n\n" + e["append"].lstrip("\n"))
            continue
        n = src.count(e["find"])
        if n != 1:
            raise EditError(f"{e['file']}: expected exactly 1 match for edit, found {n}: {e['find'][:60]!r}")
        path.write_text(src.replace(e["find"], e["replace"]))


def build_workspace(task: Task, dest: Path, ablate: list[str] | None = None) -> Path:
    """Copy the service, inject the bug, place incident logs, remove ablated components."""
    repo = dest / "repo"
    shutil.copytree(SERVICE, repo, ignore=IGNORE)
    apply_edits(repo, task.inject)
    if task.incident_log:
        (repo / "var/log").mkdir(parents=True, exist_ok=True)
        shutil.copy(task.incident_log, repo / "var/log/orders.jsonl")
    for name in ablate or []:
        if name not in ABLATIONS:
            raise ValueError(f"unknown ablation {name!r}; choose from {sorted(ABLATIONS)}")
        for rel in ABLATIONS[name]:
            p = repo / rel
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
    (dest / "PROMPT.md").write_text(task.prompt + "\n")
    return repo
