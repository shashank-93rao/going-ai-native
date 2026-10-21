"""Worked example: orchestrator-workers for a cross-repo dependency audit.

Why orchestrator-workers and not a fixed fan-out: which manifests exist, and in which
ecosystem, is only known after looking. The orchestrator (an LLM) proposes subtasks; code
validates and caps them. Workers are READ-ONLY: they extract dependencies and return data.
Matching against advisories is deterministic code, and exactly one writer (synthesize)
produces the report.

Run:  python dependency_audit.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, Response, get_client
from patterns import ask, orchestrator_workers, parse_json

DATA = Path(__file__).parent / "data"
MANIFEST_ECOSYSTEM = {"requirements.txt": "pypi", "package.json": "npm", "go.mod": "go"}

PLAN_SYSTEM = (
    "You plan a dependency audit. You get a listing of repositories and their files. "
    "Emit one subtask per dependency manifest as JSON: "
    '{"subtasks": [{"repo": "<repo>", "manifest": "<file name>", "ecosystem": "pypi|npm|go"}]}. '
    "Only list files that appear in the listing. Output JSON only."
)

WORKER_SYSTEM = (
    "You read one dependency manifest and list its direct runtime dependencies as JSON: "
    '[{"name": "<package exactly as written>", "version": "<version exactly as written>"}]. '
    "Skip comments, the module's own name, and toolchain lines. Output JSON only."
)


@dataclass
class Finding:
    repo: str
    package: str
    version: str
    advisory: str
    fixed_in: str


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v.lstrip("v^~=<>"))[:3])


def listing(repos_dir: Path) -> str:
    rows = []
    for repo in sorted(p for p in repos_dir.iterdir() if p.is_dir()):
        files = sorted(f.name for f in repo.iterdir() if f.is_file())
        rows.append(f"{repo.name}: {', '.join(files)}")
    return "\n".join(rows)


def make_validator(repos_dir: Path):
    def validate(sub: dict[str, Any]) -> bool:
        repo, manifest, eco = sub.get("repo", ""), sub.get("manifest", ""), sub.get("ecosystem")
        if "/" in repo or ".." in repo or "/" in manifest:      # no path traversal from a plan
            return False
        if MANIFEST_ECOSYSTEM.get(manifest) != eco:
            return False
        return (repos_dir / repo / manifest).is_file()
    return validate


def make_worker(client: LLMClient, repos_dir: Path, advisories: list[dict[str, str]]):
    def work(sub: dict[str, Any]) -> dict[str, Any]:
        text = (repos_dir / sub["repo"] / sub["manifest"]).read_text()
        deps = parse_json(ask(client, f"<manifest name='{sub['manifest']}'>\n{text}\n</manifest>",
                              system=WORKER_SYSTEM))
        grounded = [d for d in deps if d["name"] in text and d["version"] in text]
        ungrounded = [d for d in deps if d not in grounded]
        findings = []
        for d in grounded:
            for adv in advisories:
                if adv["ecosystem"] == sub["ecosystem"] and adv["package"] == d["name"] \
                        and version_tuple(d["version"]) < version_tuple(adv["fixed_in"]):
                    findings.append(Finding(sub["repo"], d["name"], d["version"], adv["id"], adv["fixed_in"]))
        return {"subtask": sub, "deps": grounded, "ungrounded": ungrounded, "findings": findings}
    return work


def synthesize(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """The single writer: one place that turns worker data into the report."""
    findings = sorted((f for o in outputs for f in o["findings"]), key=lambda f: (f.repo, f.package))
    lines = ["| repo | package | version | advisory | fixed in |", "|---|---|---|---|---|"]
    lines += [f"| {f.repo} | {f.package} | {f.version} | {f.advisory} | {f.fixed_in} |" for f in findings]
    warnings = [f"{o['subtask']['repo']}/{o['subtask']['manifest']}: dropped ungrounded {o['ungrounded']}"
                for o in outputs if o["ungrounded"]]
    return {"findings": findings, "report": "\n".join(lines), "warnings": warnings,
            "manifests_audited": len(outputs)}


def audit(client: LLMClient, repos_dir: Path = DATA / "repos", max_subtasks: int = 10) -> dict[str, Any]:
    advisories = json.loads((DATA / "advisories.json").read_text())
    result = orchestrator_workers(
        client, f"<listing>\n{listing(repos_dir)}\n</listing>", plan_system=PLAN_SYSTEM,
        validate=make_validator(repos_dir), worker=make_worker(client, repos_dir, advisories),
        synthesize=synthesize, max_subtasks=max_subtasks)
    return {**result.final, "dropped_subtasks": result.dropped}


# --------------------------------------------------------------------------- offline stand-in

def fake_audit_model(messages: list[dict[str, Any]], kw: dict[str, Any]) -> Response:
    """Deterministic stand-in for the planner and the extraction workers. Not a model."""
    system, user = kw.get("system") or "", messages[-1]["content"]
    if system.startswith("You plan"):
        subs = []
        for line in user.splitlines():
            if ":" in line and not line.startswith("<"):
                repo, files = line.split(":", 1)
                for f in (x.strip() for x in files.split(",")):
                    if f in MANIFEST_ECOSYSTEM:
                        subs.append({"repo": repo.strip(), "manifest": f, "ecosystem": MANIFEST_ECOSYSTEM[f]})
        return Response(text=json.dumps({"subtasks": subs}))
    name = re.search(r"<manifest name='([^']+)'>", user).group(1)
    body = user.split(">", 1)[1]
    if name == "requirements.txt":
        deps = [{"name": re.sub(r"\[.*\]", "", n), "version": v}
                for n, v in re.findall(r"^([A-Za-z0-9_.\-\[\]]+)==(\S+)", body, re.M)]
    elif name == "package.json":
        deps = [{"name": n, "version": v}
                for n, v in json.loads(body.rsplit("</manifest>", 1)[0])["dependencies"].items()]
    else:
        deps = [{"name": n, "version": v} for n, v in re.findall(r"^\s+(\S+)\s+(v[\d.]+)", body, re.M)]
    return Response(text=json.dumps(deps))


def main() -> None:
    out = audit(get_client(fake=FakeClient(fake_audit_model)))
    print(f"audited {out['manifests_audited']} manifests\n")
    print(out["report"])
    for w in out["warnings"]:
        print("WARN", w)


if __name__ == "__main__":
    main()
