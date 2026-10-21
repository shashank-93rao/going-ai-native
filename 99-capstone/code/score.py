"""Field-level precision/recall for the postmortem extraction pipeline (capstone variant B).

Counting rules (write these into your labeling guide, they are part of the spec):
- Scalar field: correct value -> TP. Wrong non-null value -> FP *and* FN (you asserted
  something false and missed the truth). Null when gold is non-null -> FN. Non-null when
  gold is null -> FP.
- Set field (services_affected): each element is scored separately.
- Free-text fields (summary, action_items) are NOT scored here; they need a judge (M5).

    python score.py runs/preds.jsonl                       # report vs data/labels.jsonl
    python score.py runs/preds_v2.jsonl --baseline runs/preds_v1.jsonl   # paired bootstrap on micro F1
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCALAR_FIELDS = ["severity", "root_cause_category", "detection_minutes", "duration_minutes", "customer_impact"]
SET_FIELDS = ["services_affected"]
JUDGE_FIELDS = ["summary", "action_items"]
NUMERIC = {"detection_minutes", "duration_minutes"}
LABELS_PATH = Path(__file__).parent / "data" / "labels.jsonl"


def load_jsonl(path: str | Path) -> dict[str, dict[str, Any]]:
    return {r["doc_id"]: r for r in (json.loads(l) for l in Path(path).read_text().splitlines() if l.strip())}


def _norm(f: str, v: Any) -> Any:
    if v is None or v == "":
        return None
    if f in NUMERIC:
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None
    if f == "customer_impact":
        return v if isinstance(v, bool) else str(v).strip().lower() in ("true", "yes", "1")
    return str(v).strip().lower()


def field_counts(f: str, pred: dict[str, Any], gold: dict[str, Any], tol: int = 0) -> tuple[int, int, int]:
    """(tp, fp, fn) for one field on one document."""
    if f in SET_FIELDS:
        p = {str(x).strip().lower() for x in (pred.get(f) or [])}
        g = {str(x).strip().lower() for x in (gold.get(f) or [])}
        return len(p & g), len(p - g), len(g - p)
    p, g = _norm(f, pred.get(f)), _norm(f, gold.get(f))
    if p is None and g is None:
        return 0, 0, 0
    if p is None:
        return 0, 0, 1
    if g is None:
        return 0, 1, 0
    ok = abs(p - g) <= tol if f in NUMERIC else p == g
    return (1, 0, 0) if ok else (0, 1, 1)


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


@dataclass
class Report:
    per_field: dict[str, dict[str, float]]
    micro: dict[str, float]
    errors: list[dict[str, Any]] = field(default_factory=list)  # one row per (doc, field) mistake


def score(preds: dict[str, dict[str, Any]], labels: dict[str, dict[str, Any]], tol: int = 0) -> Report:
    """Score predictions against labels. Docs missing from `preds` count as all-null predictions."""
    fields = SCALAR_FIELDS + SET_FIELDS
    totals = {f: [0, 0, 0] for f in fields}
    errors = []
    for doc_id, gold in labels.items():
        pred = preds.get(doc_id, {})
        for f in fields:
            tp, fp, fn = field_counts(f, pred, gold, tol)
            for i, v in enumerate((tp, fp, fn)):
                totals[f][i] += v
            if fp or fn:
                errors.append({"doc_id": doc_id, "field": f, "pred": pred.get(f), "gold": gold.get(f),
                               "hard_features": gold.get("hard_features", [])})
    per = {f: _prf(*t) for f, t in totals.items()}
    micro = _prf(*(sum(t[i] for t in totals.values()) for i in range(3)))
    return Report(per, micro, errors)


def bootstrap_ci(preds, labels, n_boot: int = 1000, seed: int = 0, tol: int = 0) -> tuple[float, float]:
    """95% CI on micro F1, resampling documents (the unit of independence)."""
    rng, ids = random.Random(seed), list(labels)
    vals = []
    for _ in range(n_boot):
        sample = _resample(labels, ids, rng)
        vals.append(score({k: preds.get(v["_src"], {}) for k, v in sample.items()}, sample, tol).micro["f1"])
    vals.sort()
    return vals[int(0.025 * n_boot)], vals[int(0.975 * n_boot) - 1]


def _resample(labels, ids, rng) -> dict[str, dict[str, Any]]:
    # Keys must stay unique, so duplicates get a suffix but keep the same gold row.
    out = {}
    for k, i in enumerate(rng.choice(ids) for _ in ids):
        out[f"{i}#{k}"] = {**labels[i], "_src": i}
    return out


def paired_bootstrap(a, b, labels, n_boot: int = 1000, seed: int = 0, tol: int = 0) -> dict[str, float]:
    """Micro-F1 difference (b - a) with a paired 95% CI: both systems scored on the same resampled docs."""
    rng, ids = random.Random(seed), list(labels)
    diffs = []
    for _ in range(n_boot):
        sample = _resample(labels, ids, rng)
        pa = {k: a.get(v["_src"], {}) for k, v in sample.items()}
        pb = {k: b.get(v["_src"], {}) for k, v in sample.items()}
        diffs.append(score(pb, sample, tol).micro["f1"] - score(pa, sample, tol).micro["f1"])
    diffs.sort()
    point = score(b, labels, tol).micro["f1"] - score(a, labels, tol).micro["f1"]
    return {"delta_f1": round(point, 4), "ci95": [round(diffs[int(0.025 * n_boot)], 4),
                                                  round(diffs[int(0.975 * n_boot) - 1], 4)],
            "p_b_not_better": round(sum(d <= 0 for d in diffs) / n_boot, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("preds")
    ap.add_argument("--labels", default=str(LABELS_PATH))
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--tol", type=int, default=0, help="tolerance in minutes for numeric fields")
    args = ap.parse_args()
    labels, preds = load_jsonl(args.labels), load_jsonl(args.preds)
    rep = score(preds, labels, args.tol)
    print(json.dumps({"micro": rep.micro, "per_field": rep.per_field, "n_errors": len(rep.errors)}, indent=2))
    if args.baseline:
        print(json.dumps({"vs_baseline": paired_bootstrap(load_jsonl(args.baseline), preds, labels, tol=args.tol)},
                         indent=2))


if __name__ == "__main__":
    main()
