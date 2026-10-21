"""Metamorphic testing for an LLM alert classifier.

You rarely know the right severity for a random alert (no oracle), but you do
know relations between inputs: rewording, re-casing, adding irrelevant context,
or reordering sentences must not change the label. Hypothesis generates the
transformations; the relation is the test.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ainative_kit import LLMClient, Response, text

LABELS = ("SEV1", "SEV2", "SEV3")
CLASSIFIER_SYSTEM = "Classify the alert. SEV1: customer-facing outage. SEV2: degraded. SEV3: no customer impact. Answer with the label only."

SEED_ALERTS = {
    "checkout is down for all users. error rate 100%.": "SEV1",
    "payments p99 latency is 2x baseline. some requests time out.": "SEV2",
    "nightly batch export finished 10 minutes late. no customer impact.": "SEV3",
}

SYNONYMS = {"down": ["unavailable", "offline"], "error rate": ["failure rate"], "users": ["customers"],
            "latency": ["response time"], "late": ["behind schedule"], "time out": ["fail with timeouts"]}

NOISE = ["FYI from the on-call bot.", "Ticket auto-created.", "See runbook RB-12."]


def classify_alert(client: LLMClient, alert: str) -> str:
    resp = client.complete([{"role": "user", "content": alert}], system=CLASSIFIER_SYSTEM, max_tokens=5)
    label = resp.text.strip().upper()
    return label if label in LABELS else "INVALID"


# ----- transformations that must preserve the label -------------------------
def t_case(s: str, _k: int) -> str:
    return s.upper()


def t_whitespace(s: str, k: int) -> str:
    return re.sub(" ", "  " if k % 2 else " \n", s, count=1 + k % 3)


def t_synonym(s: str, k: int) -> str:
    for word, alts in SYNONYMS.items():
        if word in s:
            return s.replace(word, alts[k % len(alts)], 1)
    return s


def t_noise(s: str, k: int) -> str:
    return f"{NOISE[k % len(NOISE)]} {s}"


def t_reorder(s: str, _k: int) -> str:
    parts = [p for p in s.split(". ") if p]
    return ". ".join(reversed(parts))


TRANSFORMS: dict[str, Callable[[str, int], str]] = {
    "case": t_case, "whitespace": t_whitespace, "synonym": t_synonym, "noise": t_noise, "reorder": t_reorder,
}


def apply(alert: str, chain: list[tuple[str, int]]) -> str:
    for name, k in chain:
        alert = TRANSFORMS[name](alert, k)
    return alert


# ----- two fake classifiers: one brittle, one robust ------------------------
def _alert_text(messages: list[dict[str, Any]]) -> str:
    return " ".join(messages[-1]["content"].lower().split())


def brittle_model(messages: list[dict[str, Any]], _kw: dict[str, Any]) -> Response:
    """Keys on exact surface words, the way an over-fitted few-shot prompt can."""
    a = _alert_text(messages)
    if "down" in a:
        return text("SEV1")
    if "latency" in a:
        return text("SEV2")
    return text("SEV3")


def robust_model(messages: list[dict[str, Any]], _kw: dict[str, Any]) -> Response:
    """Keys on meaning-bearing alternatives (a stand-in for a model that generalizes)."""
    a = _alert_text(messages)
    if re.search(r"\b(down|unavailable|offline)\b|100%", a):
        return text("SEV1")
    if re.search(r"latency|response time|time ?out|timeouts", a):
        return text("SEV2")
    return text("SEV3")
