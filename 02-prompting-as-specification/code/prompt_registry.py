"""A file-based prompt registry: versioned prompt files, content hashes, a changelog, channels.

Layout (see prompts/):

    prompts/
      prompts.lock.json        # {name: {version: sha256}}: the "migration history"
      channels.json            # {name: {"stable": 2, "canary": 3}}: what is deployed where
      log_triage/
        v1.md v2.md v3.md      # front matter + body; a published version is immutable
        CHANGELOG.md           # "## vN (date)" entry per version

The distributed-systems analogy is schema migrations: versions are append-only,
the lock file is the applied-migrations table, and editing a published version
in place is the equivalent of editing an already-applied migration.

CLI:
    python prompt_registry.py list
    python prompt_registry.py lock            # rewrite prompts.lock.json
    python prompt_registry.py verify          # exit 1 on drift (use in CI)
    python prompt_registry.py show log_triage --channel stable
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).parent / "prompts"
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FILE = re.compile(r"^v(\d+)\.md$")
_CHANGELOG_ENTRY = re.compile(r"^##\s+v(\d+)\b", re.MULTILINE)


class PromptError(Exception):
    pass


def normalize(raw: str) -> str:
    """Normalize line endings and trailing whitespace so the hash tracks meaning, not editor noise."""
    lines = raw.replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def content_hash(raw: str) -> str:
    return hashlib.sha256(normalize(raw).encode()).hexdigest()


def parse_prompt_file(raw: str) -> tuple[dict[str, str], str]:
    """Split `---` front matter (simple `key: value` lines) from the body."""
    text = normalize(raw)
    if not text.startswith("---\n"):
        raise PromptError("prompt file must start with '---' front matter")
    try:
        header, body = text[4:].split("\n---\n", 1)
    except ValueError as e:
        raise PromptError("unterminated front matter") from e
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise PromptError(f"bad front-matter line: {line!r}")
        meta[key.strip()] = value.strip()
    for required in ("name", "version", "model", "owner"):
        if not meta.get(required):
            raise PromptError(f"front matter missing {required!r}")
    return meta, body


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: int
    meta: dict[str, str]
    body: str
    sha256: str
    path: Path

    @property
    def variables(self) -> set[str]:
        declared = self.meta.get("variables", "")
        return {v.strip() for v in declared.split(",") if v.strip()}

    @property
    def ref(self) -> str:
        """Short identifier for traces and logs: name@vN#sha12."""
        return f"{self.name}@v{self.version}#{self.sha256[:12]}"

    def render(self, **values: str) -> str:
        """Fill {{placeholders}}. Missing and unexpected variables are both errors."""
        used = set(_VAR.findall(self.body))
        if used != self.variables:
            raise PromptError(f"{self.ref}: body uses {sorted(used)} but front matter declares {sorted(self.variables)}")
        missing = self.variables - values.keys()
        extra = values.keys() - self.variables
        if missing or extra:
            raise PromptError(f"{self.ref}: missing={sorted(missing)} unexpected={sorted(extra)}")
        return _VAR.sub(lambda m: values[m.group(1)], self.body)


@dataclass
class Registry:
    root: Path
    prompts: dict[str, dict[int, PromptVersion]] = field(default_factory=dict)
    changelogs: dict[str, set[int]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | Path = DEFAULT_ROOT) -> "Registry":
        reg = cls(Path(root))
        for d in sorted(p for p in reg.root.iterdir() if p.is_dir()):
            versions: dict[int, PromptVersion] = {}
            for f in sorted(d.iterdir()):
                m = _FILE.match(f.name)
                if not m:
                    continue
                raw = f.read_text()
                meta, body = parse_prompt_file(raw)
                v = int(m.group(1))
                if meta["name"] != d.name or int(meta["version"]) != v:
                    raise PromptError(f"{f}: front matter says {meta['name']} v{meta['version']}")
                versions[v] = PromptVersion(d.name, v, meta, body, content_hash(raw), f)
            reg.prompts[d.name] = versions
            cl = d / "CHANGELOG.md"
            reg.changelogs[d.name] = {int(x) for x in _CHANGELOG_ENTRY.findall(cl.read_text())} if cl.exists() else set()
        return reg

    def get(self, name: str, version: int | None = None) -> PromptVersion:
        if name not in self.prompts:
            raise PromptError(f"unknown prompt {name!r}")
        versions = self.prompts[name]
        v = max(versions) if version is None else version
        if v not in versions:
            raise PromptError(f"{name} has no v{v}; known: {sorted(versions)}")
        return versions[v]

    def channels(self) -> dict[str, dict[str, int]]:
        path = self.root / "channels.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def resolve(self, name: str, channel: str = "stable") -> PromptVersion:
        """What version is deployed on `channel`? Rollback = point the channel at an older version."""
        chans = self.channels().get(name, {})
        if channel not in chans:
            raise PromptError(f"{name} has no {channel!r} channel")
        return self.get(name, chans[channel])

    def lock(self) -> dict[str, dict[str, str]]:
        return {n: {str(v): pv.sha256 for v, pv in sorted(vs.items())} for n, vs in sorted(self.prompts.items())}

    def write_lock(self) -> Path:
        path = self.root / "prompts.lock.json"
        path.write_text(json.dumps(self.lock(), indent=2) + "\n")
        return path

    def verify(self) -> list[str]:
        """Return problems. CI fails if this is non-empty."""
        problems: list[str] = []
        lock_path = self.root / "prompts.lock.json"
        locked: dict[str, dict[str, str]] = json.loads(lock_path.read_text()) if lock_path.exists() else {}
        for name, versions in self.prompts.items():
            for v, pv in versions.items():
                old = locked.get(name, {}).get(str(v))
                if old is None:
                    problems.append(f"{pv.ref}: not in lock file (run `lock` after review)")
                elif old != pv.sha256:
                    problems.append(f"{name}@v{v}: content changed after publish (locked {old[:12]}, now {pv.sha256[:12]}); create v{max(versions) + 1} instead")
                if v not in self.changelogs.get(name, set()):
                    problems.append(f"{name}@v{v}: no '## v{v}' entry in CHANGELOG.md")
            gaps = sorted(set(range(1, max(versions) + 1)) - versions.keys())
            if gaps:
                problems.append(f"{name}: missing versions {gaps}; published versions are never deleted")
        for name, vs in locked.items():
            for v in vs:
                if int(v) not in self.prompts.get(name, {}):
                    problems.append(f"{name}@v{v}: in lock file but the file is gone")
        for name, chans in self.channels().items():
            for chan, v in chans.items():
                if v not in self.prompts.get(name, {}):
                    problems.append(f"channels.json: {name}.{chan} points at missing v{v}")
        return problems


def main(argv: list[str]) -> int:
    reg = Registry.load()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        chans = reg.channels()
        for name, versions in reg.prompts.items():
            for v, pv in versions.items():
                tags = [c for c, cv in chans.get(name, {}).items() if cv == v]
                print(f"{pv.ref:40} model={pv.meta['model']:18} {' '.join(tags)}")
        return 0
    if cmd == "lock":
        print(f"wrote {reg.write_lock()}")
        return 0
    if cmd == "verify":
        problems = reg.verify()
        for p in problems:
            print(f"FAIL {p}")
        print("OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if cmd == "show" and len(argv) >= 2:
        chan = argv[argv.index("--channel") + 1] if "--channel" in argv else None
        pv = reg.resolve(argv[1], chan) if chan else reg.get(argv[1])
        print(f"# {pv.ref}\n{pv.body}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
