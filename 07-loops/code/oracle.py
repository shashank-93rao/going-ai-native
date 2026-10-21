"""Oracles: the deterministic checks a loop consumes, and a test that the oracle can fail.

An oracle answers "is this done?" with a fact the agent cannot write itself. Before you
trust one inside a loop, prove it can fail: apply known-bad changes (mutants) to a copy
of the workspace and confirm the oracle rejects every one. A mutant that survives is a
hole the loop will eventually find and walk through.

    oracle = PytestOracle(["spec_tokenbucket.py"])
    r = oracle.run(workspace)              # OracleResult(passed, failed, ...)
    survivors = prove_it_can_fail(oracle, workspace, MUTANTS)
    assert not survivors
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# pytest exit codes: 0 all passed, 1 some failed, 2 interrupted, 3 internal error,
# 4 usage error, 5 no tests collected. Only 0 and 1 are verdicts; the rest mean the
# oracle itself is broken, and a broken oracle must never read as "pass".
_PYTEST_VERDICT_CODES = {0, 1}


@dataclass
class OracleResult:
    passed: int
    failed: int
    exit_code: int
    output: str
    broken: bool = False

    @property
    def ok(self) -> bool:
        return not self.broken and self.exit_code == 0 and self.failed == 0 and self.passed > 0

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def score(self) -> float:
        """Fraction passing, 0.0 when broken. Higher is better, so governors can track it."""
        return 0.0 if self.broken or self.total == 0 else self.passed / self.total

    def summary_for_agent(self, max_lines: int = 15) -> str:
        """Short, greppable feedback: verdict line first, then only the failure lines."""
        if self.broken:
            head = f"ORACLE BROKEN (exit {self.exit_code}): fix the test setup, not the code"
        elif self.ok:
            head = f"PASS {self.passed}/{self.total}"
        else:
            head = f"FAIL {self.failed}/{self.total} failing"
        lines = self.output.splitlines()
        verdicts = [ln for ln in lines if ln.startswith(("FAILED", "ERROR"))]
        details = [ln for ln in lines if ln.startswith("E ") and ln[1:].strip() and "Use -v" not in ln]
        return "\n".join([head, *verdicts, *details][: max_lines + 1])


_COUNT_RE = re.compile(r"(\d+) (passed|failed|error|errors)\b")


class PytestOracle:
    """Runs pytest on explicit files in a workspace and parses the summary line."""

    def __init__(self, files: list[str], timeout_s: float = 60.0):
        self.files = files
        self.timeout_s = timeout_s

    def run(self, workspace: str | Path) -> OracleResult:
        cmd = [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", *self.files]
        try:
            proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return OracleResult(0, 0, -1, f"oracle timed out after {self.timeout_s}s", broken=True)
        out = proc.stdout + proc.stderr
        passed = failed = 0
        for n, kind in _COUNT_RE.findall(out):
            if kind == "passed":
                passed += int(n)
            else:
                failed += int(n)
        broken = proc.returncode not in _PYTEST_VERDICT_CODES or (passed + failed == 0)
        return OracleResult(passed, failed, proc.returncode, out, broken=broken)


class CommandOracle:
    """Any shell command whose exit code is the verdict (make check, tsc, a parity script)."""

    def __init__(self, cmd: str, timeout_s: float = 300.0):
        self.cmd = cmd
        self.timeout_s = timeout_s

    def run(self, workspace: str | Path) -> OracleResult:
        try:
            proc = subprocess.run(
                self.cmd, shell=True, cwd=workspace, capture_output=True, text=True, timeout=self.timeout_s
            )
        except subprocess.TimeoutExpired:
            return OracleResult(0, 0, -1, "timed out", broken=True)
        ok = proc.returncode == 0
        return OracleResult(int(ok), int(not ok), proc.returncode, proc.stdout + proc.stderr)


# ---- prove it can fail ---------------------------------------------------------

Mutant = Callable[[Path], None]  # mutates a *copy* of the workspace in place


def replace_in(path: str, old: str, new: str) -> Mutant:
    """Build a mutant that swaps one snippet in one file. Fails loudly if the snippet is gone."""

    def apply(root: Path) -> None:
        f = root / path
        src = f.read_text()
        if old not in src:
            raise ValueError(f"mutant snippet not found in {path}: {old!r}")
        f.write_text(src.replace(old, new, 1))

    apply.__name__ = f"{path}: {old.strip()[:30]!r} -> {new.strip()[:30]!r}"
    return apply


def prove_it_can_fail(oracle, workspace: str | Path, mutants: dict[str, Mutant]) -> list[str]:
    """Return the names of mutants the oracle did NOT reject (survivors). Empty list = good.

    Also asserts the unmutated workspace passes, so a permanently red oracle cannot
    masquerade as a strict one.
    """
    base = oracle.run(workspace)
    if not base.ok:
        raise AssertionError(f"oracle must pass on the known-good workspace first:\n{base.summary_for_agent()}")
    survivors = []
    for name, mutate in mutants.items():
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "ws"
            shutil.copytree(workspace, copy)
            mutate(copy)
            if oracle.run(copy).ok:
                survivors.append(name)
    return survivors


if __name__ == "__main__":
    # Demo on the toy task: strong spec vs a smoke test that only checks the import works.
    here = Path(__file__).parent
    sys.path.insert(0, str(here / "examples"))
    from toy_task import MUTANTS, make_workspace

    with tempfile.TemporaryDirectory() as tmp:
        ws = make_workspace(Path(tmp), fixed=True)
        for files in (["spec_tokenbucket.py"], ["spec_smoke.py"]):
            surv = prove_it_can_fail(PytestOracle(files), ws, MUTANTS)
            print(f"{files[0]:22s} caught {len(MUTANTS) - len(surv)}/{len(MUTANTS)} mutants; survivors: {surv}")
