"""Deterministic stand-ins for judge models, used by the scripts and tests offline.

These are NOT models. They are small heuristics with known, deliberate flaws, so
that the calibration and bias-probe code has something realistic to measure:

- incident_keyword_judge: passes a summary if it contains the exact affected-customer
  count from the facts. It misses faithful paraphrases ("about 3,400") and passes
  summaries that get the count right but the scope or severity wrong.
- likert_length_judge: a 1-5 "quality" scorer that mostly rewards length and digits.
- first_position_judge / longer_response_judge: pairwise judges with pure position
  or pure verbosity bias.
- content_pairwise_judge: a pairwise judge that compares on a content score only.

Each is a FakeClient responder: (messages, kwargs) -> Response.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ainative_kit import Response, text, tool

Responder = Callable[[list[dict[str, Any]], dict[str, Any]], Response]


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    content = messages[-1]["content"]
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def _tag(s: str, name: str) -> str:
    m = re.search(rf"<{name}>\n?(.*?)\n?</{name}>", s, re.S)
    return m.group(1).strip() if m else ""


def impact_count(facts: str) -> int | None:
    """Largest integer on the 'Customer impact:' line, or None if impact is 'none'."""
    line = next((ln for ln in facts.splitlines() if ln.startswith("Customer impact:")), "")
    if re.match(r"Customer impact:\s*none", line, re.I):
        return None
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?![\d.]*%)", line) if n.replace(",", "").isdigit()]
    return max(nums) if nums else None


def keyword_verdict(facts: str, summary: str) -> tuple[bool, str]:
    """The flawed heuristic behind incident_keyword_judge."""
    count = impact_count(facts)
    if count is None:
        ok = bool(re.search(r"no customer|customer-facing systems were unaffected|no customer-facing", summary, re.I))
        return ok, ("States no customer impact." if ok else "Does not state that customers were unaffected.")
    forms = {f"{count:,}", str(count)}
    ok = any(f in summary for f in forms)
    return ok, (f"Summary contains the affected count {count:,}." if ok else f"Affected count {count:,} not found in summary.")


def incident_keyword_judge(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    msg = _last_user_text(messages)
    ok, why = keyword_verdict(_tag(msg, "facts"), _tag(msg, "summary"))
    return tool("record_verdict", {"critique": why, "verdict": "pass" if ok else "fail"})


# v2: rules added after reading the v1 judge's DEV-split disagreements only.
# Each pair is (claim in summary, text in facts that contradicts that claim).
_SEVERITY = [
    (r"double-charged", r"no orders were double-charged"),
    (r"\bfailed\b", r"no requests failed"),
    (r"\blost\b", r"no (events|data) (were|was) lost"),
    (r"incorrect", r"complete and correct"),
    (r"\bpartial\b", r"100% of"),
]
_SCOPE = [
    (r"all regions|globally", r"^(?!.*all regions)"),
    (r"all (tiers|types)", r"unaffected|delivered normally"),
]
_NEGATORS = re.compile(r"\b(no|not|nothing|never|without|none)\b[^.;]{0,40}$", re.I)


def _asserted(summary: str, pattern: str) -> bool:
    """True if `pattern` occurs in `summary` and is not negated just before it."""
    for m in re.finditer(pattern, summary, re.I):
        if not _NEGATORS.search(summary[: m.start()]):
            return True
    return False


def _count_mentioned(count: int, summary: str) -> bool:
    if f"{count:,}" in summary or str(count) in summary:
        return True
    for m in re.finditer(r"(about|roughly|approximately|~)\s*(\d[\d,]*)(k)?", summary, re.I):
        n = int(m.group(2).replace(",", "")) * (1000 if m.group(3) else 1)
        if abs(n - count) <= 0.1 * count:
            return True
    return bool(re.search(rf"\b{round(count / 1000)}k\b", summary)) if count >= 1000 else False


def rules_verdict(facts: str, summary: str) -> tuple[bool, str]:
    """The v2 heuristic: count (with rounding) plus contradiction rules."""
    count = impact_count(facts)
    if count is None:
        return keyword_verdict(facts, summary)
    impact_line = next(ln for ln in facts.splitlines() if ln.startswith("Customer impact:"))
    for claim, contra in _SEVERITY + _SCOPE:
        if _asserted(summary, claim) and re.search(contra, impact_line, re.I):
            return False, f"Summary claims '{re.search(claim, summary, re.I).group(0)}', contradicted by the facts."
    if not _count_mentioned(count, summary):
        return False, f"Affected count {count:,} (or a fair rounding) not found."
    return True, f"Count {count:,} present and no contradicted scope or severity claim found."


def incident_rules_judge(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    msg = _last_user_text(messages)
    ok, why = rules_verdict(_tag(msg, "facts"), _tag(msg, "summary"))
    return tool("record_verdict", {"critique": why, "verdict": "pass" if ok else "fail"})


def likert_score(summary: str) -> int:
    """1-5 'quality', driven by surface specificity (numbers, regions, timestamps) and length.

    This is what an unanchored 1-5 scale tends to measure: how polished and detailed
    the text looks, not whether its customer-impact claims are true.
    """
    specifics = len(re.findall(r"\d[\d,.:]*", summary))
    specifics += len(re.findall(r"(us|eu|ap)-[a-z]+-\d|UTC|iOS|Pro-tier|enterprise", summary, re.I))
    score = 1 + (specifics >= 1) + (specifics >= 3) + (specifics >= 5) + (len(summary) > 150)
    return min(score, 5)


def likert_length_judge(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    return text(str(likert_score(_tag(_last_user_text(messages), "summary"))))


def _pair(messages: list[dict[str, Any]]) -> tuple[str, str]:
    msg = _last_user_text(messages)
    return _tag(msg, "response_1"), _tag(msg, "response_2")


def _pref(winner: str, why: str) -> Response:
    return tool("record_preference", {"critique": why, "winner": winner})


def first_position_judge(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """Always prefers whatever is shown first. Pure position bias."""
    return _pref("1", "Response 1 is more complete.")


def longer_response_judge(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """Always prefers the longer response. Pure verbosity bias."""
    r1, r2 = _pair(messages)
    if len(r1) == len(r2):
        return _pref("tie", "Equivalent.")
    return _pref("1" if len(r1) > len(r2) else "2", "The longer response is more thorough.")


def content_pairwise_judge(score: Callable[[str, str], float]) -> Responder:
    """A pairwise judge that compares score(task, response) and ignores order and length."""

    def responder(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
        task = _tag(_last_user_text(messages), "task")
        r1, r2 = _pair(messages)
        s1, s2 = score(task, r1), score(task, r2)
        if s1 == s2:
            return _pref("tie", "Both responses carry the same facts.")
        return _pref("1" if s1 > s2 else "2", "Preferred response states more of the required facts.")

    return responder


def padded_lenient_judge(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> Response:
    """Pointwise judge that applies the keyword rule but also passes anything long. Verbosity bias."""
    msg = _last_user_text(messages)
    summary = _tag(msg, "summary")
    ok, why = keyword_verdict(_tag(msg, "facts"), summary)
    if len(summary) > 220:
        ok, why = True, "Thorough, detailed summary."
    return tool("record_verdict", {"critique": why, "verdict": "pass" if ok else "fail"})
