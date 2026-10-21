"""Worked example: a broken multi-writer design, its failure modes, and the single-writer fix.

Two failure modes, deliberately separated:
  1. LOST UPDATE: two writers edit the same file from the same snapshot; last write wins.
     Optimistic concurrency (compare-and-set on a version) fixes this one.
  2. CONFLICTING IMPLICIT DECISIONS (Cognition, 2025): writers edit DIFFERENT files, each
     consistent with a snapshot that the other is invalidating. No byte-level conflict
     exists, so OCC passes, and the merged result is still broken.
The fix: one writer applies all changes serially against the current state; helpers are
read-only and contribute notes. A check runs after every write.

Run:  python single_writer.py
"""

from __future__ import annotations

import builtins
import json
import keyword
import re
from dataclasses import dataclass, field
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, get_client
from patterns import ask, parse_json

SEED_FILES = {
    "client.py": 'def fetch_user(user_id):\n    return {"id": user_id}\n',
    "api.py": 'from client import fetch_user\n\n\ndef handle_get_user(req):\n    return fetch_user(req["id"])\n',
    "jobs.py": "def nightly_sync(ids):\n    return [str(i) for i in ids]\n",
}

TASK_RENAME = "Rename fetch_user to get_user everywhere."
TASK_SYNC = "Make nightly_sync fetch each user through the client module and return the users."
TASK_LOGGING = "Add request logging (print) to handle_get_user."
TASK_AUTH = "Reject requests without a token in handle_get_user."

WRITER_SYSTEM = ("You edit a small Python codebase. Output only JSON: "
                 '{"edits": [{"path": "<file>", "content": "<full new file content>"}]}. '
                 "Edit only what the task needs.")
HELPER_SYSTEM = "You are a read-only research helper. Report facts about the code. Never propose edits."


class Conflict(Exception):
    pass


@dataclass
class Repo:
    files: dict[str, str] = field(default_factory=lambda: dict(SEED_FILES))
    versions: dict[str, int] = field(default_factory=dict)

    def version(self, path: str) -> int:
        return self.versions.get(path, 0)

    def snapshot(self) -> dict[str, tuple[str, int]]:
        return {p: (c, self.version(p)) for p, c in self.files.items()}

    def write(self, path: str, content: str, expected_version: int | None = None) -> None:
        """expected_version=None is a blind write (last writer wins). Otherwise compare-and-set."""
        if expected_version is not None and self.version(path) != expected_version:
            raise Conflict(f"{path}: expected v{expected_version}, found v{self.version(path)}")
        self.files[path] = content
        self.versions[path] = self.version(path) + 1


def undefined_calls(files: dict[str, str]) -> list[str]:
    """The check: every bare call must resolve to a def in the repo or a builtin."""
    defined = {m for c in files.values() for m in re.findall(r"^def (\w+)\(", c, re.M)}
    ok = defined | set(dir(builtins)) | set(keyword.kwlist)
    problems = []
    for path, content in sorted(files.items()):
        body = re.sub(r"^def \w+\(", "", content, flags=re.M)
        for name in re.findall(r"(?<![.\w])([A-Za-z_]\w*)\(", body):
            if name not in ok:
                problems.append(f"{path}: call to undefined {name}()")
        for mod, names in re.findall(r"^from (\w+) import (.+)$", content, re.M):
            src = files.get(f"{mod}.py", "")
            for n in (x.strip() for x in names.split(",")):
                if not re.search(rf"^def {n}\(", src, re.M):
                    problems.append(f"{path}: imports {n} which {mod}.py does not define")
    return problems


def render(snapshot: dict[str, tuple[str, int]]) -> str:
    return "\n".join(f'<file path="{p}">\n{c}</file>' for p, (c, _) in sorted(snapshot.items()))


def propose(client: LLMClient, task: str, snapshot: dict[str, tuple[str, int]], notes: str = "") -> list[dict]:
    prompt = f"TASK: {task}\n\n{render(snapshot)}" + (f"\n\n<notes>\n{notes}\n</notes>" if notes else "")
    return parse_json(ask(client, prompt, system=WRITER_SYSTEM))["edits"]


@dataclass
class Outcome:
    files: dict[str, str]
    problems: list[str]
    conflicts: int = 0
    log: list[str] = field(default_factory=list)


def run_parallel_writers(client: LLMClient, repo: Repo, tasks: list[str], *, occ: bool) -> Outcome:
    """Every worker reads the same snapshot, edits independently, then writes. The broken design."""
    snap = repo.snapshot()
    proposals = [(t, propose(client, t, snap)) for t in tasks]   # conceptually concurrent
    conflicts, log = 0, []
    for task, edits in proposals:
        for e in edits:
            try:
                repo.write(e["path"], e["content"], snap[e["path"]][1] if occ else None)
                log.append(f"{task[:30]!r} wrote {e['path']}")
            except Conflict as c:
                conflicts += 1
                log.append(f"{task[:30]!r} CONFLICT {c}; re-reading and retrying")
                fresh = repo.snapshot()
                for e2 in propose(client, task, fresh):
                    if e2["path"] == e["path"]:
                        repo.write(e2["path"], e2["content"], fresh[e2["path"]][1])
    return Outcome(dict(repo.files), undefined_calls(repo.files), conflicts, log)


def run_single_writer(client: LLMClient, repo: Repo, tasks: list[str], helper_questions: list[str]) -> Outcome:
    """Helpers read in parallel; one writer applies tasks serially on current state, checked after each."""
    notes = "\n".join(ask(client, f"QUESTION: {q}\n\n{render(repo.snapshot())}", system=HELPER_SYSTEM)
                      for q in helper_questions)
    log = []
    for task in tasks:
        snap = repo.snapshot()                     # the writer always sees the latest state
        for e in propose(client, task, snap, notes):
            repo.write(e["path"], e["content"], snap.get(e["path"], ("", 0))[1])
        problems = undefined_calls(repo.files)
        log.append(f"{task[:30]!r} applied; check: {problems or 'clean'}")
        if problems:
            snap = repo.snapshot()
            fix = f"{task}\nThe check failed: {problems}. Fix it."
            for e in propose(client, fix, snap, notes):
                repo.write(e["path"], e["content"], snap.get(e["path"], ("", 0))[1])
    return Outcome(dict(repo.files), undefined_calls(repo.files), 0, log)


# --------------------------------------------------------------------------- offline stand-in

def _files(prompt: str) -> dict[str, str]:
    return dict(re.findall(r'<file path="([^"]+)">\n(.*?)</file>', prompt, re.S))


def fake_coder(messages: list[dict[str, Any]], kw: dict[str, Any]) -> Response:
    """Deterministic stand-in: applies each task's edit to WHATEVER STATE IT IS SHOWN.
    That is the point: the same 'competent' worker produces a broken merge from a stale snapshot."""
    prompt = messages[-1]["content"]
    files = _files(prompt)
    if (kw.get("system") or "").startswith("You are a read-only"):
        sites = [f"{p}:{i + 1}" for p, c in files.items() for i, l in enumerate(c.splitlines()) if "fetch_user" in l]
        return Response(text=f"fetch_user appears at: {', '.join(sites)}. A rename is planned to get_user.")
    task = prompt.split("\n", 1)[0]
    edits = []
    if TASK_RENAME in task:
        edits = [{"path": p, "content": c.replace("fetch_user", "get_user")} for p, c in files.items() if "fetch_user" in c]
    elif TASK_SYNC in task:
        fn = re.search(r"^def (\w+_user)\(", files["client.py"], re.M).group(1)
        edits = [{"path": "jobs.py", "content": f"from client import {fn}\n\n\ndef nightly_sync(ids):\n"
                                                f"    return [{fn}(i) for i in ids]\n"}]
    elif TASK_LOGGING in task:
        edits = [{"path": "api.py", "content": files["api.py"].replace(
            "def handle_get_user(req):\n", 'def handle_get_user(req):\n    print("get_user", req["id"])\n')}]
    elif TASK_AUTH in task:
        edits = [{"path": "api.py", "content": files["api.py"].replace(
            "def handle_get_user(req):\n",
            'def handle_get_user(req):\n    if not req.get("token"):\n        raise PermissionError("no token")\n')}]
    return Response(text=json.dumps({"edits": edits}))


def main() -> None:
    client = get_client(fake=FakeClient(fake_coder))
    for label, fn in [
        ("parallel writers, blind writes", lambda: run_parallel_writers(client, Repo(), [TASK_RENAME, TASK_SYNC], occ=False)),
        ("parallel writers, with OCC", lambda: run_parallel_writers(client, Repo(), [TASK_RENAME, TASK_SYNC], occ=True)),
        ("single writer + read-only helper", lambda: run_single_writer(
            client, Repo(), [TASK_RENAME, TASK_SYNC], ["Where is fetch_user used?"])),
    ]:
        out = fn()
        print(f"== {label}: conflicts={out.conflicts} problems={out.problems or 'none'}")
        print(out.files["jobs.py"])


if __name__ == "__main__":
    main()
