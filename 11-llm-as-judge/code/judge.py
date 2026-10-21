"""A binary LLM judge with structured output (critique first, then verdict).

One judge = one failure mode. The rubric is a short list of checkable claims, the
model must call a `record_verdict` tool whose schema puts `critique` before
`verdict`, and anything we cannot parse is an error, never a silent pass.

    python judge.py                      # incident-summary judge over data/, offline fake unless a key is set
    python judge.py --write-labels out.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from ainative_kit import FakeClient, LLMClient, Response, get_client

DATA = Path(__file__).parent / "data"

VERDICT_TOOL: dict[str, Any] = {
    "name": "record_verdict",
    "description": "Record your critique and your binary verdict for this one check. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            # Order matters: the critique is generated before the verdict, so the
            # verdict is conditioned on the reasoning rather than rationalised after it.
            "critique": {
                "type": "string",
                "description": "2-5 sentences. Quote the specific text you checked and say which claim held or broke.",
            },
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
        },
        "required": ["critique", "verdict"],
    },
}


@dataclass(frozen=True)
class Rubric:
    """A single-failure-mode rubric made of checkable claims."""

    name: str
    question: str                      # the one thing this judge decides
    inputs: tuple[str, ...]            # item fields shown to the judge, in order
    pass_claims: tuple[str, ...]       # all must hold for PASS
    fail_if: tuple[str, ...] = ()      # any one of these forces FAIL
    out_of_scope: tuple[str, ...] = () # things this judge must NOT grade
    few_shot: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass
class Verdict:
    passed: bool
    critique: str
    raw: Response | None = None


class JudgeOutputError(ValueError):
    """The judge did not return a parseable verdict. Count it as an error, not a pass."""


INCIDENT_IMPACT = Rubric(
    name="incident_customer_impact",
    question="Does the summary state the customer impact correctly, as given in the incident facts?",
    inputs=("facts", "summary"),
    pass_claims=(
        "If the facts say there was customer impact, the summary states who was affected "
        "(a count, or a segment such as a tier, region or platform) and what they experienced.",
        "Every customer-impact claim in the summary is supported by the facts: the scope (region, tier, "
        "platform, email type) matches, and the severity matches (delayed is not lost, slow is not failed, "
        "partial is not total).",
        "If the facts say there was no customer impact, the summary says so explicitly.",
    ),
    fail_if=(
        "The summary describes only root cause or internal impact (tickets, dashboards, deploys paused).",
        "The summary hedges ('may have affected customers') where the facts are definite.",
        "A count differs from the facts by more than ordinary rounding (3,412 -> 'about 3,400' is fine).",
    ),
    out_of_scope=("tone, length, or writing quality", "whether the root cause is explained well", "timeline accuracy"),
)

CODE_REVIEW_BUG = Rubric(
    name="review_comment_real_bug",
    question="Does the review comment identify a real bug that this diff introduces or leaves in the changed lines?",
    inputs=("language", "diff", "comment"),
    pass_claims=(
        "The comment names a concrete defect: wrong behaviour, data loss, a race, a leak, a security hole, "
        "or an operational hazard (lock, unbounded wait, retry storm).",
        "The defect is actually present in the post-diff code shown. Trace the code; do not take the comment's word for it.",
    ),
    fail_if=(
        "The comment is a style, naming or convention remark.",
        "The comment is a question or a suggestion with no identified defect.",
        "The claimed defect is not real (for example it misreads a language or library guarantee), "
        "or the diff fixes rather than introduces it.",
    ),
    out_of_scope=("whether the comment is polite", "whether there are other bugs the comment missed"),
)


def render_system(rubric: Rubric) -> str:
    """The judge's system prompt: one question, checkable claims, critique-then-verdict."""
    lines = [
        "You are a strict evaluator. You answer exactly one question with PASS or FAIL.",
        f"Question: {rubric.question}",
        "",
        "PASS only if ALL of these hold:",
        *[f"  {i}. {c}" for i, c in enumerate(rubric.pass_claims, 1)],
    ]
    if rubric.fail_if:
        lines += ["", "FAIL if ANY of these is true:", *[f"  - {c}" for c in rubric.fail_if]]
    if rubric.out_of_scope:
        lines += ["", "Do NOT consider (another check covers these): " + "; ".join(rubric.out_of_scope) + "."]
    lines += [
        "",
        "Procedure: check each claim against the inputs, quoting the text you relied on. Write the critique first, "
        "then decide. Length and fluency are not evidence. If you cannot verify a claim from the inputs, it fails.",
        "Respond only by calling the record_verdict tool once.",
    ]
    for ex in rubric.few_shot:
        lines += ["", "<example>", render_item(rubric, ex),
                  f"<expected_critique>{ex['human_critique']}</expected_critique>",
                  f"<expected_verdict>{ex['human_label']}</expected_verdict>", "</example>"]
    return "\n".join(lines)


def render_item(rubric: Rubric, item: dict[str, Any]) -> str:
    """Wrap each input field in an XML tag so the judge can quote it unambiguously."""
    return "\n".join(f"<{k}>\n{item[k]}\n</{k}>" for k in rubric.inputs)


def with_few_shot(rubric: Rubric, rows: Iterable[dict[str, Any]], k: int = 4) -> Rubric:
    """Return a copy of `rubric` with up to k labelled TRAIN rows as few-shot examples (balanced pass/fail)."""
    train = [r for r in rows if r.get("split") == "train"]
    passes = [r for r in train if r["human_label"] == "pass"][: k // 2]
    fails = [r for r in train if r["human_label"] == "fail"][: k - len(passes)]
    return replace(rubric, few_shot=tuple(passes + fails))


def parse_verdict(resp: Response) -> Verdict:
    """Prefer the tool call; fall back to a JSON object in text; otherwise raise."""
    payload: dict[str, Any] | None = None
    for tc in resp.tool_calls:
        if tc.name == VERDICT_TOOL["name"]:
            payload = tc.input
            break
    if payload is None:
        m = re.search(r"\{.*\}", resp.text, re.S)
        if m:
            try:
                payload = json.loads(m.group(0))
            except json.JSONDecodeError:
                payload = None
    if not payload or payload.get("verdict") not in ("pass", "fail"):
        raise JudgeOutputError(f"unparseable judge output: tool_calls={resp.tool_calls!r} text={resp.text[:200]!r}")
    return Verdict(passed=payload["verdict"] == "pass", critique=str(payload.get("critique", "")), raw=resp)


def judge(client: LLMClient, rubric: Rubric, item: dict[str, Any], *, model: str | None = None) -> Verdict:
    """Run one binary judgement. Raises JudgeOutputError rather than guessing."""
    resp = client.complete(
        [{"role": "user", "content": render_item(rubric, item)}],
        system=render_system(rubric),
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": VERDICT_TOOL["name"]},
        model=model,
        max_tokens=1024,
    )
    return parse_verdict(resp)


def judge_many(client: LLMClient, rubric: Rubric, items: Iterable[dict[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    """Judge every item; record errors explicitly instead of dropping them."""
    out = []
    for it in items:
        try:
            v = judge(client, rubric, it, **kw)
            out.append({"id": it["id"], "judge_label": "pass" if v.passed else "fail", "judge_critique": v.critique})
        except JudgeOutputError as e:
            out.append({"id": it["id"], "judge_label": "error", "judge_critique": str(e)})
    return out


def fingerprint(rubric: Rubric, model: str) -> str:
    """Hash of everything that defines the judge. Any change means the calibration is stale."""
    import hashlib

    blob = json.dumps({"system": render_system(rubric), "tool": VERDICT_TOOL, "model": model}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def main() -> None:
    from judge_fakes import incident_keyword_judge, incident_rules_judge  # offline stand-ins for a model

    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA / "incident_summaries.jsonl"))
    ap.add_argument("--fake", choices=["v1", "v2"], default="v2", help="offline stand-in to use when no API key is set")
    ap.add_argument("--write-labels", default=None, help="write id/split/human_label/judge_label JSONL here")
    args = ap.parse_args()

    rows = load_jsonl(args.data)
    fake = incident_rules_judge if args.fake == "v2" else incident_keyword_judge
    client = get_client(fake=FakeClient(fake))
    rubric = with_few_shot(INCIDENT_IMPACT, rows)
    eval_rows = [r for r in rows if r["split"] != "train"]  # never score the judge on its own few-shot examples
    results = judge_many(client, rubric, eval_rows)
    by_id = {r["id"]: r for r in eval_rows}
    agree = sum(res["judge_label"] == by_id[res["id"]]["human_label"] for res in results)
    for res in results[:5]:
        print(f"{res['id']:<14} human={by_id[res['id']]['human_label']:<4} judge={res['judge_label']:<5} {res['judge_critique'][:90]}")
    print(f"... raw agreement {agree}/{len(results)} on dev+test (see calibrate.py for TPR/TNR)")
    if args.write_labels:
        with open(args.write_labels, "w") as f:
            for res in results:
                r = by_id[res["id"]]
                f.write(json.dumps({"id": r["id"], "split": r["split"], "human_label": r["human_label"], **res}) + "\n")
        print(f"wrote {len(results)} rows to {args.write_labels}")


if __name__ == "__main__":
    main()
