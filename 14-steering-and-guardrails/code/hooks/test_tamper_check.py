"""Detect test tampering in a diff: deleted tests, skips, removed or weakened assertions.

This is Beck's third warning sign ("cheating, for example by disabling or deleting
tests") turned into a deterministic check. It is a heuristic over diff lines, not a
proof: it is tuned to catch the common moves an agent makes under test pressure.

    git diff HEAD | python test_tamper_check.py            # exit 1 on findings
    python test_tamper_check.py --base main --json          # machine-readable

Human-approved test changes: list paths (one per line) in .agent/approved-test-changes.txt.
Findings on those paths are downgraded to "info". The PreToolUse guard denies agent writes
to that file, so the agent cannot approve its own test edits.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unified_diff import FileDiff, parse_unified_diff  # noqa: E402

APPROVALS_FILE = ".agent/approved-test-changes.txt"

TEST_PATH = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$|Test\.java$|(^|/)conftest\.py$"
)
TEST_CONFIG_PATH = re.compile(r"(^|/)(pytest\.ini|setup\.cfg|tox\.ini|pyproject\.toml|conftest\.py|jest\.config\.[jt]s)$")

ASSERTION = re.compile(
    r"\bassert\b|self\.assert\w+\(|\bassert\w*\.\w+\(|\brequire\.\w+\(|\bexpect\(|assertThat\(|\bt\.(Error|Fatal)f?\(|pytest\.raises\("
)
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)|^\s*func\s+(Test\w+)\(|^\s*(?:it|test)\(\s*['\"]([^'\"]+)")
SKIP = re.compile(
    r"@pytest\.mark\.(skip|skipif|xfail)\b|@unittest\.skip|\bpytest\.skip\(|\bt\.Skip(Now|f)?\(|"
    r"\b(it|describe|test)\.skip\(|\bxit\(|@Disabled\b|@Ignore\b"
)
COMMENTED_ASSERT = re.compile(r"^\s*(#|//)\s*(assert\b|self\.assert|expect\(|require\.|assert\w*\.)")
SWALLOW = re.compile(r"except\s+(AssertionError|Exception|BaseException)\b|except\s*:")
VACUOUS = re.compile(r"\s*(assert\s+(True|1)|self\.assertTrue\(True\))\s*(#.*)?$")
CONFIG_EXCLUSION = re.compile(r"collect_ignore|--deselect|--ignore|addopts.*-k\s|testPathIgnorePatterns")

WEAKER_ASSERT_METHOD = {
    "assertEqual": {"assertTrue", "assertIsNotNone", "assertIn", "assertGreaterEqual", "assertLessEqual", "assertAlmostEqual"},
    "assertRaises": {"assertTrue"},
    "assertIs": {"assertTrue", "assertIsNotNone"},
}


@dataclass
class Finding:
    rule: str
    severity: str  # "high" | "medium" | "info"
    path: str
    line: int
    detail: str


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def _test_names(lines: list[tuple[int, str]]) -> dict[str, int]:
    out = {}
    for no, text in lines:
        m = TEST_DEF.match(text)
        if m:
            out[next(g for g in m.groups() if g)] = no
    return out


def _weakening(old: str, new: str) -> str | None:
    """Return a description if `new` is a weaker form of assertion `old`."""
    o, n = old.strip(), new.strip()
    if re.search(r"(?<![<>!=])==(?!=)", o) and not re.search(r"(?<![<>!=])==(?!=)", n):
        if re.search(r">=|<=|(?<![-=])>(?!=)|(?<![<=])<(?!=)|!=|\bin\b", n):
            return "exact equality replaced by a looser comparison"
        if re.match(r"assert\s+[\w.\[\]()]+\s*(,|$)", n):
            return "comparison dropped: assertion now only checks truthiness"
    for strong, weak in WEAKER_ASSERT_METHOD.items():
        if f".{strong}(" in o and any(f".{w}(" in n for w in weak):
            return f"{strong} replaced by a weaker method"
    if re.search(r"pytest\.raises\((?!Exception\b)\w+", o) and re.search(r"pytest\.raises\((Exception|BaseException)\b", n):
        return "specific exception widened to Exception"
    if "ANY" not in o and re.search(r"\b(mock\.)?ANY\b", n):
        return "concrete expected value replaced by ANY"
    tol_o = re.search(r"(abs|rel|delta|places)\s*=\s*([\d.e-]+)", o)
    tol_n = re.search(r"(abs|rel|delta)\s*=\s*([\d.e-]+)", n)
    if tol_o and tol_n and tol_o.group(1) == tol_n.group(1):
        try:
            if float(tol_n.group(2)) > float(tol_o.group(2)):
                return f"tolerance loosened ({tol_o.group(1)} {tol_o.group(2)} -> {tol_n.group(2)})"
        except ValueError:
            pass
    return None


def _check_file(fd: FileDiff) -> list[Finding]:
    f: list[Finding] = []
    if TEST_CONFIG_PATH.search(fd.path):
        for no, line in fd.added:
            if CONFIG_EXCLUSION.search(line):
                f.append(Finding("test_config_exclusion", "high", fd.path, no, line.strip()))
    if not is_test_path(fd.path):
        return f
    if fd.status == "deleted":
        return f + [Finding("test_file_deleted", "high", fd.path, 0, f"{len(fd.removed)} lines removed")]

    removed_tests, added_tests = _test_names(fd.removed), _test_names(fd.added)
    for name, no in removed_tests.items():
        if name not in added_tests:
            f.append(Finding("test_removed", "high", fd.path, no, f"test {name} deleted"))

    for no, line in fd.added:
        if SKIP.search(line):
            f.append(Finding("skip_added", "high", fd.path, no, line.strip()))
        elif COMMENTED_ASSERT.match(line):
            f.append(Finding("assertion_commented_out", "high", fd.path, no, line.strip()))
        elif SWALLOW.search(line):
            f.append(Finding("exception_swallowed", "medium", fd.path, no, line.strip()))
        elif VACUOUS.match(line):
            f.append(Finding("vacuous_assertion", "high", fd.path, no, line.strip()))

    rem_asserts = [(n, t) for n, t in fd.removed if ASSERTION.search(t) and not COMMENTED_ASSERT.match(t)]
    add_asserts = [(n, t) for n, t in fd.added
                   if ASSERTION.search(t) and not COMMENTED_ASSERT.match(t) and not VACUOUS.match(t)]
    unmatched_added = list(add_asserts)
    for no, old in rem_asserts:
        best, best_ratio = None, 0.0
        for cand in unmatched_added:
            r = difflib.SequenceMatcher(None, old.strip(), cand[1].strip()).ratio()
            if r > best_ratio:
                best, best_ratio = cand, r
        if best is not None and best_ratio >= 0.55:
            unmatched_added.remove(best)
            why = _weakening(old, best[1])
            if why:
                f.append(Finding("assertion_weakened", "high", fd.path, best[0], f"{why}: '{old.strip()}' -> '{best[1].strip()}'"))
    net = len(rem_asserts) - len(add_asserts)
    if net > 0:
        f.append(Finding("assertions_removed", "medium" if add_asserts else "high", fd.path, 0,
                         f"{len(rem_asserts)} assertion lines removed, {len(add_asserts)} added (net -{net})"))
    return f


def check_diff(diff_text: str, approved_paths: set[str] | None = None) -> list[Finding]:
    approved = approved_paths or set()
    findings: list[Finding] = []
    for fd in parse_unified_diff(diff_text):
        for finding in _check_file(fd):
            if finding.path in approved:
                finding.severity = "info"
            findings.append(finding)
    return findings


def blocking(findings: list[Finding]) -> list[Finding]:
    return [x for x in findings if x.severity in ("high", "medium")]


def format_findings(findings: list[Finding]) -> str:
    return "\n".join(f"- [{x.severity}] {x.rule} {x.path}:{x.line} {x.detail}" for x in findings)


def load_approvals(root: Path) -> set[str]:
    p = root / APPROVALS_FILE
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")}


def git_diff(root: Path, base: str = "HEAD") -> str:
    r = subprocess.run(["git", "diff", base, "--"], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git diff failed: {r.stderr.strip()}")
    return r.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff", help="diff file; '-' for stdin. Default: run git diff against --base")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.diff == "-":
        diff = sys.stdin.read()
    elif args.diff:
        diff = Path(args.diff).read_text()
    else:
        diff = git_diff(root, args.base)
    findings = check_diff(diff, load_approvals(root))
    if args.json:
        print(json.dumps([asdict(x) for x in findings], indent=2))
    elif findings:
        print(format_findings(findings))
    return 1 if blocking(findings) else 0


if __name__ == "__main__":
    sys.exit(main())
