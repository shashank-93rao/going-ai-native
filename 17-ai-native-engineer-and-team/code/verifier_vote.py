"""N independent reviewers, a majority vote per finding, style findings dropped.

    python verifier_vote.py data/diffs/raft_election.diff --n 3
    python verifier_vote.py data/diffs/raft_election.diff --n 5 --review-md templates/REVIEW.md

Each reviewer gets a fresh context: the diff plus REVIEW.md, nothing from the
other reviewers. That is what makes the votes (roughly) independent, in the
same way replicas in a quorum must not share a failure domain.

Pipeline:
  1. N reviewer calls, each returning JSON findings (malformed output = abstain).
  2. Drop findings with no file/line evidence, or in REVIEW.md skip paths.
  3. Cluster findings that point at the same place (same file, lines within a
     window (default 2), same category bucket).
  4. Drop clusters that are style/nit only. Post a cluster only if a strict
     majority of the N configured reviewers support it.
  5. If too few reviewers answered to ever reach a majority, mark the run
     degraded: the caller should treat it as "no machine review happened".

This is the "independent replicas" variant. Anthropic's Claude Code reviewer
separates bug hunters from verifiers that vote on each candidate; see
exercises.md for building that two-phase variant on top of this file.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, Tracer, get_client, text

SUBSTANTIVE = {"bug", "security", "perf", "concurrency", "durability"}
STYLE = {"style", "nit", "naming", "docs"}
SEVERITY_ORDER = {"nit": 0, "pre-existing": 1, "important": 2}

SYSTEM = """You are one of several independent code reviewers for this repository.
Follow REVIEW.md exactly. Report everything you find; a later pass filters by
severity and agreement, so do not self-censor.

Return ONLY a JSON object, no prose:
{"findings": [{"file": "<path>", "line": <int, line in the new file>,
  "category": "bug|security|perf|concurrency|durability|style|nit",
  "severity": "important|nit|pre-existing",
  "summary": "<one sentence: what breaks and when>",
  "evidence": "<the exact line(s) you are pointing at>"}]}
Return {"findings": []} if you find nothing."""


@dataclass
class Finding:
    file: str
    line: int
    category: str
    severity: str
    summary: str
    evidence: str
    reviewer: int

    @property
    def bucket(self) -> str:
        return "style" if self.category in STYLE else "substantive"


@dataclass
class Cluster:
    file: str
    line: int
    bucket: str
    members: list[Finding] = field(default_factory=list)

    @property
    def support(self) -> int:
        return len({f.reviewer for f in self.members})

    @property
    def severity(self) -> str:
        """Majority label wins for 'pre-existing'; otherwise the highest severity."""
        pre = sum(f.severity == "pre-existing" for f in self.members)
        if pre * 2 > len(self.members):
            return "pre-existing"
        return max((f.severity for f in self.members), key=lambda s: SEVERITY_ORDER.get(s, 0))

    @property
    def summary(self) -> str:
        return self.members[0].summary


@dataclass
class VoteResult:
    n_reviewers: int
    abstained: list[int]
    posted: list[Cluster]
    dropped_minority: list[Cluster]
    dropped_style: list[Cluster]
    dropped_no_evidence: list[Finding]
    dropped_skipped_path: list[Finding]

    @property
    def degraded(self) -> bool:
        """True if the answering reviewers can no longer form a strict majority."""
        answered = self.n_reviewers - len(self.abstained)
        return answered * 2 <= self.n_reviewers


def build_messages(diff: str, review_md: str) -> list[dict[str, Any]]:
    """One fresh conversation per reviewer: REVIEW.md + diff, nothing else."""
    return [{"role": "user", "content": f"<review_md>\n{review_md}\n</review_md>\n\n<diff>\n{diff}\n</diff>"}]


def _extract_json(raw: str) -> Any:
    raw = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON found")
    return json.loads(raw[start : max(raw.rfind("}"), raw.rfind("]")) + 1])


def parse_findings(raw: str, reviewer: int) -> list[Finding] | None:
    """Parse one reviewer's output. None means malformed (an abstention, not 'no bugs')."""
    try:
        data = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    items = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            line = int(it.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        out.append(Finding(
            file=str(it.get("file") or ""), line=line,
            category=str(it.get("category", "bug")).lower(),
            severity=str(it.get("severity", "important")).lower(),
            summary=str(it.get("summary", "")), evidence=str(it.get("evidence", "")),
            reviewer=reviewer,
        ))
    return out


def parse_skip_paths(review_md: str) -> list[str]:
    """Globs listed as bullets under a REVIEW.md heading that contains 'skip'."""
    globs, in_skip = [], False
    for line in review_md.splitlines():
        if line.startswith("#"):
            in_skip = "skip" in line.lower()
            continue
        m = re.match(r"\s*[-*]\s+`([^`]+)`", line)
        if in_skip and m:
            globs.append(m.group(1))
    return globs


def run_reviewers(client: LLMClient, diff: str, review_md: str, n: int, *, model: str | None = None,
                  tracer: Tracer | None = None) -> list[list[Finding] | None]:
    """Call N reviewers independently. Order of calls does not matter; no shared context."""
    tracer = tracer or Tracer()
    results: list[list[Finding] | None] = []
    for i in range(n):
        with tracer.span("reviewer", reviewer=i) as s:
            resp = client.complete(build_messages(diff, review_md), system=SYSTEM, model=model, max_tokens=2048)
            parsed = parse_findings(resp.text, i)
            s.attrs.update(findings=None if parsed is None else len(parsed), abstained=parsed is None,
                           output_tokens=resp.usage.output_tokens)
        results.append(parsed)
    return results


def cluster_findings(findings: list[Finding], line_window: int = 2) -> list[Cluster]:
    """Greedy clustering by (file, bucket) and line proximity."""
    clusters: list[Cluster] = []
    for f in sorted(findings, key=lambda f: (f.file, f.bucket, f.line, f.reviewer)):
        for c in clusters:
            if c.file == f.file and c.bucket == f.bucket and abs(c.line - f.line) <= line_window:
                c.members.append(f)
                break
        else:
            clusters.append(Cluster(file=f.file, line=f.line, bucket=f.bucket, members=[f]))
    return clusters


def vote(per_reviewer: list[list[Finding] | None], *, skip_paths: list[str] | None = None,
         line_window: int = 2) -> VoteResult:
    """Apply evidence, skip-path, style and majority filters. Denominator is N configured reviewers."""
    n = len(per_reviewer)
    abstained = [i for i, r in enumerate(per_reviewer) if r is None]
    kept, no_evidence, skipped = [], [], []
    for r in per_reviewer:
        for f in r or []:
            if not f.file or f.line <= 0:
                no_evidence.append(f)
            elif any(fnmatch.fnmatch(f.file, g) for g in skip_paths or []):
                skipped.append(f)
            else:
                kept.append(f)
    posted, minority, style = [], [], []
    for c in cluster_findings(kept, line_window):
        if c.bucket == "style":
            style.append(c)
        elif c.support * 2 > n:
            posted.append(c)
        else:
            minority.append(c)
    posted.sort(key=lambda c: (-SEVERITY_ORDER.get(c.severity, 0), c.file, c.line))
    return VoteResult(n, abstained, posted, minority, style, no_evidence, skipped)


def review(client: LLMClient, diff: str, review_md: str, n: int = 3, **kw: Any) -> VoteResult:
    per = run_reviewers(client, diff, review_md, n, model=kw.pop("model", None), tracer=kw.pop("tracer", None))
    return vote(per, skip_paths=parse_skip_paths(review_md), **kw)


def format_comment(res: VoteResult) -> str:
    """PR comment. Leads with a count and says plainly when there is nothing to fix (REVIEW.md rule)."""
    if res.degraded:
        return (f"Machine review DEGRADED: {len(res.abstained)} of {res.n_reviewers} reviewers returned "
                "unusable output. Treat this PR as unreviewed by machine; route to a human.")
    important = [c for c in res.posted if c.severity == "important"]
    if not res.posted:
        head = "0 findings. Nothing to fix."
    else:
        head = f"{len(important)} important, {len(res.posted) - len(important)} other finding(s)."
    lines = [head]
    for c in res.posted:
        lines.append(f"- [{c.severity.title()}] {c.file}:{c.line} ({c.support}/{res.n_reviewers} agree): {c.summary}")
    lines.append(f"(dropped: {len(res.dropped_minority)} minority, {len(res.dropped_style)} style, "
                 f"{len(res.dropped_no_evidence)} without file:line)")
    return "\n".join(lines)


def demo_client() -> FakeClient:
    """Three canned reviewers for the raft_election.diff sample."""
    bug = {"file": "internal/raft/election.go", "category": "durability", "severity": "important",
           "summary": "Vote is granted before votedFor is durable; a crash after replying lets this node vote twice in one term.",
           "evidence": "go n.storage.PersistHardState(n.currentTerm, n.votedFor)"}
    style = {"file": "internal/raft/election.go", "line": 42, "category": "style", "severity": "nit",
             "summary": "Comment should explain why, not what.", "evidence": "// persist off the hot path"}
    lonely = {"file": "internal/raft/election.go", "line": 39, "category": "bug", "severity": "important",
              "summary": "becomeFollower should reset the election timer.", "evidence": "n.becomeFollower(req.Term)"}
    return FakeClient([
        text(json.dumps({"findings": [{**bug, "line": 42}, style]})),
        text(json.dumps({"findings": [{**bug, "line": 43, "category": "concurrency"}, lonely]})),
        text("```json\n" + json.dumps({"findings": [{**bug, "line": 42}, style]}) + "\n```"),
    ])


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("diff")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--review-md", default=str(here / "templates" / "REVIEW.md"))
    args = ap.parse_args(argv)
    client = get_client(fake=demo_client())
    if isinstance(client, FakeClient) and args.n != 3:
        args.n = 3  # the canned demo has exactly three reviewers
    res = review(client, Path(args.diff).read_text(), Path(args.review_md).read_text(), n=args.n)
    print(format_comment(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
