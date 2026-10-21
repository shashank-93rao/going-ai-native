"""A prompt linter for ambiguity smells.

It is a heuristic, like a code linter: cheap, fast, and wrong sometimes. It
catches the smells that recur in prompt reviews, so humans can spend review
time on intent. Every message says how to fix the problem, because a lint
message is itself a prompt (to you, or to the agent fixing the file).

Rules
  PL001 error    missing-output-format   nothing says what shape the answer takes
  PL002 error    contradiction           two instructions pull in opposite directions
  PL003 warning  unbounded-absolute      ALWAYS/NEVER/MUST with no reason or scope
  PL004 warning  shouting                3+ all-caps emphasis words
  PL005 warning  expired-technique       advice tuned for older models
  PL006 info     vague-term              words a smart new hire would read differently than you
  PL007 error    unbalanced-xml          an opened tag is never closed (or vice versa)

    python prompt_lint.py prompts/*/v*.md     # exit 1 if any error
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.line:>4}: {self.severity:<7} {self.rule} {self.message}"


# ---------------------------------------------------------------- helpers

def _body_lines(text: str) -> list[tuple[int, str]]:
    """(line_no, line) pairs, 1-based, skipping a leading `---` front-matter block."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    return [(i + 1, lines[i]) for i in range(start, len(lines))]


def _sentences(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    out = []
    for n, line in lines:
        for s in re.split(r"(?<=[.!?])\s+", line.strip()):
            if s:
                out.append((n, s))
    return out


_STOP = set("""a an the and or but of to in on for with by at from as is are be this that these those it its
your you our we they them their any all each every there here than then into over under about not no""".split())


def _content_words(sentence: str) -> set[str]:
    words = re.findall(r"[a-z][a-z_\-]+", sentence.lower())
    return {w for w in words if len(w) > 3 and w not in _STOP and w not in _POLARITY_WORDS}


# ---------------------------------------------------------------- rules

_OUTPUT_SIGNALS = re.compile(
    r"output[_ ]format|<output|respond (only )?with|respond only|return (only )?(a |an |the )?(json|yaml|list|object|table)"
    r"|\bjson\b|\bschema\b|headed\b|in (exactly )?\w+ (short )?(paragraphs|bullets|sentences)",
    re.IGNORECASE,
)


def rule_output_format(lines):
    if any(_OUTPUT_SIGNALS.search(line) for _, line in lines):
        return []
    first = lines[0][0] if lines else 1
    return [Finding("PL001", "error", first,
                    "No output format. Say exactly what comes back (JSON fields, sections, length) and who parses it.")]


_BREVITY = re.compile(r"\b(concise|brief|succinct|terse|under \d+ words|\d+ words at most)\b", re.I)
_EXHAUSTIVE = re.compile(r"\b(thorough|comprehensive|exhaustive|in depth|in detail|all relevant details|every single)\b", re.I)
_SELECTIVE = re.compile(r"\b(only report|only (the )?important|be conservative|only high[- ]severity)\b", re.I)
_POSITIVE = re.compile(r"\b(always|must|make sure to|be sure to)\b", re.I)
_NEGATIVE = re.compile(r"\b(never|do not|don't|must not|avoid)\b", re.I)
_POLARITY_WORDS = {"always", "must", "make", "sure", "never", "don't", "avoid"}


def rule_contradiction(lines):
    findings = []
    sents = _sentences(lines)

    def first_line(rx):
        return next((n for n, s in sents if rx.search(s)), None)

    for a, b, label in ((_BREVITY, _EXHAUSTIVE, "brevity vs exhaustiveness"),
                        (_EXHAUSTIVE, _SELECTIVE, "report everything vs report only some")):
        la, lb = first_line(a), first_line(b)
        if la and lb:
            where = f"line {la}" if la == lb else f"lines {min(la, lb)} and {max(la, lb)}"
            findings.append(Finding("PL002", "error", min(la, lb),
                                    f"Contradiction ({label}) on {where}. Pick one, or say which wins "
                                    "and when (e.g. 'report every finding with a severity; a later step filters').",))
    pos = [(n, s, _content_words(s)) for n, s in sents if _POSITIVE.search(s) and not _NEGATIVE.search(s)]
    neg = [(n, s, _content_words(s)) for n, s in sents if _NEGATIVE.search(s)]
    for n1, s1, w1 in pos:
        for n2, s2, w2 in neg:
            shared = w1 & w2
            if len(shared) >= 2:
                findings.append(Finding("PL002", "error", min(n1, n2),
                                        f"Line {n1} requires and line {n2} forbids {sorted(shared)}. "
                                        "State the condition that separates the two cases."))
    return findings


_ABSOLUTE = re.compile(r"\b(always|never)\b|\bMUST\b|under no circumstances|without exception", re.I)
_MUST_LOWER = re.compile(r"\bmust\b")
_SCOPE = re.compile(r"\b(because|since|so that|unless|except|when|if|otherwise|so the|so it)\b", re.I)


def rule_unbounded_absolute(lines):
    findings = []
    for n, s in _sentences(lines):
        m = _ABSOLUTE.search(s)
        if not m or (_MUST_LOWER.fullmatch(m.group(0))):
            continue  # lowercase "must" in ordinary prose is fine
        if _SCOPE.search(s):
            continue
        findings.append(Finding("PL003", "warning", n,
                                f"Unbounded '{m.group(0)}' in: {s[:70]!r}. Add the reason or the scope, or enforce "
                                "it in code. Reserve absolutes for true invariants."))
    return findings


_SHOUT = re.compile(r"\b(CRITICAL|IMPORTANT|MUST|ALWAYS|NEVER|NOT|EXACTLY|ONLY)\b")


def rule_shouting(lines):
    hits = [(n, m.group(0)) for n, line in lines for m in _SHOUT.finditer(line)]
    if len(hits) < 3:
        return []
    words = ", ".join(sorted({w for _, w in hits}))
    return [Finding("PL004", "warning", hits[0][0],
                    f"{len(hits)} shouted words ({words}). Current models over-trigger on aggressive emphasis; "
                    "use normal case and explain why the rule matters.")]


_EXPIRED = [
    (re.compile(r"think (it through )?step[- ]by[- ]step|let'?s think", re.I),
     "'Think step by step' is redundant on reasoning models; use the effort setting and state success criteria."),
    (re.compile(r"plan extensively|reflect extensively", re.I),
     "GPT-4.1-era planning reminder. Current models plan on their own; re-measure before keeping it."),
    (re.compile(r"double[- ]check|re-?verify|verify every", re.I),
     "Explicit re-check instructions cause over-verification on Opus 5. Give it a check to run instead."),
    (re.compile(r"\bthink tool\b|use the think tool", re.I),
     "The think tool was superseded by extended/adaptive thinking (Anthropic, 2025-12 update)."),
]


def rule_expired(lines):
    findings = []
    for n, line in lines:
        for rx, msg in _EXPIRED:
            if rx.search(line):
                findings.append(Finding("PL005", "warning", n, msg))
    return findings


_VAGUE = re.compile(r"\b(appropriate(ly)?|as needed|relevant|properly|important stuff|any issues|"
                    r"figure out|etc\.?|carefully|world-class|expert)\b", re.I)


def rule_vague(lines):
    findings = []
    for n, line in lines:
        for m in _VAGUE.finditer(line):
            findings.append(Finding("PL006", "info", n,
                                    f"Vague '{m.group(0)}'. Would a smart new hire know what you mean? Define it or give an example."))
    return findings


_TAG = re.compile(r"<(/?)([a-z][a-z0-9_]*)>")


def rule_xml_balance(lines):
    stack: list[tuple[str, int]] = []
    findings = []
    for n, line in lines:
        for close, name in _TAG.findall(line):
            if not close:
                stack.append((name, n))
            elif stack and stack[-1][0] == name:
                stack.pop()
            else:
                findings.append(Finding("PL007", "error", n, f"</{name}> closes a tag that is not open."))
    for name, n in stack:
        findings.append(Finding("PL007", "error", n, f"<{name}> is never closed; the model cannot tell where it ends."))
    return findings


RULES = [rule_output_format, rule_contradiction, rule_unbounded_absolute, rule_shouting,
         rule_expired, rule_vague, rule_xml_balance]


def lint(text: str) -> list[Finding]:
    lines = _body_lines(text)
    findings = [f for rule in RULES for f in rule(lines)]
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.line, f.rule))


def main(paths: list[str]) -> int:
    worst = 0
    for p in paths:
        findings = lint(Path(p).read_text())
        print(f"{p}: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        if any(f.severity == "error" for f in findings):
            worst = 1
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
