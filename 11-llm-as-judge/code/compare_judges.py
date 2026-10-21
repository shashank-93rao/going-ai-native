"""Bad Likert judge vs binary judges, scored against the same human labels.

Prints confusion matrices, TPR/TNR and the best-case Likert threshold on dev,
then the frozen choices on test. Offline it uses the fakes in judge_fakes.py,
so the numbers describe those heuristics, not any real model.

    python compare_judges.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ainative_kit import FakeClient, LLMClient, get_client

from calibrate import Confusion, confusion
from judge import INCIDENT_IMPACT, judge, render_item
from judge_fakes import incident_keyword_judge, incident_rules_judge, likert_length_judge

DATA = Path(__file__).parent / "data"

# The "before" prompt: an unanchored 1-5 scale, number only, no critique.
LIKERT_PROMPT = (
    "Rate this incident summary on a scale of 1-5 for quality and accuracy.\n"
    "{item}\n"
    "1: Very poor  5: Excellent\n"
    "Output only the number."
)


def likert(client: LLMClient, item: dict[str, Any]) -> int:
    resp = client.complete([{"role": "user", "content": LIKERT_PROMPT.format(item=render_item(INCIDENT_IMPACT, item))}],
                           max_tokens=8)
    m = re.search(r"[1-5]", resp.text)
    if not m:
        raise ValueError(f"no score in {resp.text!r}")
    return int(m.group(0))


def best_threshold(scores: list[int], human: list[bool]) -> tuple[int, Confusion]:
    """Pick the Likert cut-off (score >= t means pass) that maximises TPR + TNR on these labels."""
    best: tuple[int, Confusion] | None = None
    for t in range(2, 6):
        cm = confusion(human, [s >= t for s in scores])
        if best is None or cm.tpr + cm.tnr > best[1].tpr + best[1].tnr:
            best = (t, cm)
    assert best is not None
    return best


def _fmt(name: str, cm: Confusion) -> str:
    return f"{name}\n{cm.table()}\n  TPR {cm.tpr:.2f}  TNR {cm.tnr:.2f}  accuracy {cm.accuracy:.2f}  kappa {cm.kappa:.2f}\n"


def run(rows: list[dict[str, Any]], likert_client: LLMClient, binaries: dict[str, LLMClient]) -> dict[str, Any]:
    """Return per-split confusion matrices for the Likert judge (dev-picked threshold) and each binary judge."""
    out: dict[str, Any] = {"likert_hist": {}}
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    scores = {r["id"]: likert(likert_client, r) for r in dev + test}
    for r in dev + test:
        key = (r["human_label"], scores[r["id"]])
        out["likert_hist"][key] = out["likert_hist"].get(key, 0) + 1
    t, cm_dev = best_threshold([scores[r["id"]] for r in dev], [r["human_label"] == "pass" for r in dev])
    out["likert_threshold"] = t
    out["likert"] = {"dev": cm_dev,
                     "test": confusion([r["human_label"] == "pass" for r in test], [scores[r["id"]] >= t for r in test])}
    for name, client in binaries.items():
        out[name] = {
            split: confusion([r["human_label"] == "pass" for r in rs], [judge(client, INCIDENT_IMPACT, r).passed for r in rs])
            for split, rs in (("dev", dev), ("test", test))
        }
    return out


def main() -> None:
    rows = [json.loads(line) for line in (DATA / "incident_summaries.jsonl").read_text().splitlines()]
    res = run(
        rows,
        get_client(fake=FakeClient(likert_length_judge)),
        {"binary v1 (count only)": get_client(fake=FakeClient(incident_keyword_judge)),
         "binary v2 (iterated on dev)": get_client(fake=FakeClient(incident_rules_judge))},
    )
    print("Likert score distribution (dev+test):")
    for label in ("pass", "fail"):
        print(f"  human={label}: " + "  ".join(f"{s}:{res['likert_hist'].get((label, s), 0)}" for s in range(1, 6)))
    print(f"\nLikert threshold chosen on dev: score >= {res['likert_threshold']} means pass\n")
    for name in ("likert", "binary v1 (count only)", "binary v2 (iterated on dev)"):
        for split in ("dev", "test"):
            print(_fmt(f"[{split}] {name}", res[name][split]))


if __name__ == "__main__":
    main()
