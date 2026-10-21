"""Error analysis over ainative_kit traces: sample -> read -> label -> count.

    python error_analysis.py sample  --traces traces.jsonl --n 100 --stratify slice --out labels.csv
    python error_analysis.py label   --traces traces.jsonl --csv labels.csv --labeler alice
    python error_analysis.py propose --csv labels.csv          # LLM *suggests* axial codes; you decide
    python error_analysis.py report  --csv labels.csv [--results results.jsonl]

The workflow is Hamel Husain and Shreya Shankar's: read whole traces, write a
free-text *open code* for the first thing that went wrong, group open codes into
a small set of *axial codes* (binary failure modes), count them, and stop when new
traces stop producing new codes (saturation). For agents, also record the last
state that went right and the first state that went wrong; the counts form a
transition failure matrix. The label sheet is a CSV on purpose: a spreadsheet is
a fine first trace viewer.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from ainative_kit import FakeClient, LLMClient, get_client, load_traces, text

LABEL_COLUMNS = ["trace_id", "case_id", "trial", "slice", "state_path", "pass_fail", "open_code",
                 "axial_code", "last_good_state", "first_failure_state", "labeler"]


def summarize_traces(path: str | Path) -> dict[str, dict[str, Any]]:
    """One summary per trace: identity, prompt hash, input/output, and the agent state path."""
    out = {}
    for trace_id, spans in load_traces(path).items():
        root = next((s for s in spans if s["parent_id"] is None), spans[0])
        merged: dict[str, Any] = {}
        for s in spans:  # child attrs first, root attrs win
            if s is not root:
                merged.update({k: v for k, v in s["attrs"].items() if k not in merged})
        merged.update(root["attrs"])
        states: list[str] = []
        for s in spans:  # agent states, minus model-call 'plan' noise, consecutive repeats collapsed
            st = s["attrs"].get("state")
            if st not in (None, "start", "plan") and (not states or states[-1] != st):
                states.append(st)
        if merged.get("final_text"):
            states.append("report")
        out[trace_id] = {
            "trace_id": trace_id, "case_id": merged.get("case_id") or merged.get("task_id"),
            "trial": merged.get("trial"), "slice": merged.get("slice"),
            "prompt_hash": merged.get("prompt_hash"), "input": merged.get("input"),
            "output": merged.get("output", merged.get("final_text")),
            "errors": [s["error"] for s in spans if s.get("error")],
            "state_path": states, "spans": spans,
        }
    return out


def sample_traces(traces: dict[str, dict[str, Any]], n: int, seed: int = 0,
                  stratify_key: str | None = None) -> list[dict[str, Any]]:
    """Random sample, optionally round-robin across strata so rare slices are not drowned out.

    Deliberately ignores grader verdicts: you want passes in the sample too, because
    graders miss failures (that is one of the things you are looking for).
    """
    rng = random.Random(seed)
    items = sorted(traces.values(), key=lambda t: t["trace_id"])
    if not stratify_key:
        rng.shuffle(items)
        return items[:n]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in items:
        buckets[str(t.get(stratify_key))].append(t)
    for b in buckets.values():
        rng.shuffle(b)
    picked: list[dict[str, Any]] = []
    while len(picked) < n and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(picked) < n:
                picked.append(buckets[key].pop())
    return picked


def render_trace(t: dict[str, Any]) -> str:
    """Everything a labeler needs on one screen: input, every span, output."""
    lines = [f"=== trace {t['trace_id']}  case={t['case_id']} trial={t['trial']} "
             f"slice={t['slice']} prompt={t['prompt_hash']}"]
    if t.get("input") is not None:
        lines.append("INPUT:  " + json.dumps(t["input"]))
    depth: dict[str, int] = {}
    for s in t["spans"]:
        d = depth.get(s["parent_id"], -1) + 1 if s["parent_id"] else 0
        depth[s["span_id"]] = d
        shown = {k: v for k, v in s["attrs"].items() if k in ("state", "args", "result", "text", "stop_reason")}
        lines.append("  " * d + f"- {s['name']} {json.dumps(shown)[:240]}" + (f"  ERROR {s['error']}" if s.get("error") else ""))
    lines.append("OUTPUT: " + json.dumps(t.get("output"))[:400])
    if t["state_path"]:
        lines.append("STATES: " + " -> ".join(t["state_path"]))
    return "\n".join(lines)


def write_label_sheet(sampled: list[dict[str, Any]], path: str | Path) -> None:
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        for t in sampled:
            w.writerow({"trace_id": t["trace_id"], "case_id": t["case_id"], "trial": t["trial"],
                        "slice": t["slice"], "state_path": " > ".join(t["state_path"])})


def read_labels(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def _save(rows: list[dict[str, str]], path: str | Path) -> None:
    tmp = Path(str(path) + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)  # atomic: a Ctrl-C mid-session never corrupts the sheet


def label_interactive(csv_path: str | Path, traces: dict[str, dict[str, Any]], labeler: str,
                      input_fn: Callable[[str], str] = input, print_fn: Callable[[str], None] = print) -> int:
    """Walk unlabeled rows; save after every label so the session is resumable. Returns rows labeled."""
    rows = read_labels(csv_path)
    done = 0
    for row in rows:
        if row["pass_fail"]:
            continue
        print_fn(render_trace(traces[row["trace_id"]]))
        verdict = input_fn("[p]ass / [f]ail / [s]kip / [q]uit > ").strip().lower()
        if verdict == "q":
            break
        if verdict not in ("p", "f"):
            continue
        row["pass_fail"] = "pass" if verdict == "p" else "fail"
        row["open_code"] = input_fn("open code (first thing that went wrong, free text) > ").strip()
        if verdict == "f":
            row["axial_code"] = input_fn("axial code (blank = decide later) > ").strip()
            if " > " in row["state_path"]:  # multi-step (agent) trace
                row["last_good_state"] = input_fn("last state that went right > ").strip()
                row["first_failure_state"] = input_fn("first state that went wrong > ").strip()
        row["labeler"] = labeler
        _save(rows, csv_path)
        done += 1
    return done


def axial_counts(labels: list[dict[str, str]]) -> Counter:
    """Failure-mode frequencies. Failures with no axial code yet are counted as '(uncoded)'."""
    return Counter((r["axial_code"] or "(uncoded)") for r in labels if r["pass_fail"] == "fail")


def saturation_curve(labels: list[dict[str, str]]) -> list[tuple[int, int]]:
    """(traces labeled so far, distinct axial codes so far). A flat tail means you can stop."""
    seen: set[str] = set()
    curve = []
    labeled = [r for r in labels if r["pass_fail"]]
    for i, r in enumerate(labeled, 1):
        if r["axial_code"]:
            seen.add(r["axial_code"])
        curve.append((i, len(seen)))
    return curve


def transition_matrix(labels: list[dict[str, str]]) -> dict[str, Counter]:
    """rows = last good state, cols = first failing state, cells = failure counts."""
    m: dict[str, Counter] = defaultdict(Counter)
    for r in labels:
        if r["pass_fail"] == "fail" and r["first_failure_state"]:
            m[r["last_good_state"] or "(none)"][r["first_failure_state"]] += 1
    return m


def grader_agreement(labels: list[dict[str, str]], results: list[dict[str, Any]]) -> dict[str, int]:
    """Human verdict vs code-grader verdict, joined on trace_id. Code graders need checking too."""
    by_trace = {r["trace_id"]: r["passed"] for r in results}
    cm = Counter()
    for r in labels:
        if r["pass_fail"] and r["trace_id"] in by_trace:
            human, grader = r["pass_fail"] == "pass", by_trace[r["trace_id"]]
            cm[f"human_{'pass' if human else 'fail'}/grader_{'pass' if grader else 'fail'}"] += 1
    return dict(cm)


PROPOSE_PROMPT = """Here are open-coded notes from reviewing failed traces of an alert-routing system.
Group them into at most {k} failure modes. Each failure mode must be binary (a trace either has it or not),
specific enough that two engineers would agree, and named in snake_case.
Return only JSON: {{"codes": {{"<name>": "<one-line definition>"}}, "assignments": {{"<note>": "<name>"}}}}

Notes:
{notes}"""


def propose_axial_codes(client: LLMClient, open_codes: list[str], k: int = 8) -> dict[str, Any]:
    """Ask a model to *suggest* a grouping. A human reviews and edits it before it becomes the taxonomy."""
    notes = "\n".join(f"- {c}" for c in sorted(set(open_codes)) if c)
    resp = client.complete([{"role": "user", "content": PROPOSE_PROMPT.format(k=k, notes=notes)}], max_tokens=1500)
    return json.loads(resp.text)


def format_report(labels: list[dict[str, str]], results: list[dict[str, Any]] | None = None) -> str:
    labeled = [r for r in labels if r["pass_fail"]]
    fails = [r for r in labeled if r["pass_fail"] == "fail"]
    out = [f"labeled {len(labeled)}/{len(labels)} traces, {len(fails)} failures"]
    out.append("\nfailure modes (axial code: count, share of failures):")
    for code, n in axial_counts(labels).most_common():
        out.append(f"  {code:<32} {n:>4}  {n / max(len(fails), 1):.0%}")
    curve = saturation_curve(labels)
    if curve:
        out.append(f"\nsaturation: distinct codes after each 10 labels: {[c for i, c in curve if i % 10 == 0 or i == len(curve)]}")
    m = transition_matrix(labels)
    if m:
        cols = sorted({c for row in m.values() for c in row})
        out.append("\ntransition failure matrix (rows: last good state, cols: first failure):")
        out.append(f"  {'':<12}" + "".join(f"{c:>10}" for c in cols))
        for r in sorted(m):
            out.append(f"  {r:<12}" + "".join(f"{m[r][c]:>10}" for c in cols))
    if results:
        out.append(f"\nhuman vs grader: {grader_agreement(labels, results)}")
    return "\n".join(out)


def _fake_proposer() -> FakeClient:
    """Offline stand-in: groups notes by keyword. Good enough to exercise the plumbing."""
    def responder(messages, kwargs):
        notes = [l[2:] for l in messages[-1]["content"].splitlines() if l.startswith("- ")]
        rules = [("keyword", "keyword_overmatch"), ("sev", "severity_miscalibrated"), ("json", "format_violation"),
                 ("secret", "secret_echo"), ("guess", "should_have_abstained"), ("test", "edited_tests")]
        assign = {n: next((code for kw, code in rules if kw in n.lower()), "other") for n in notes}
        return text(json.dumps({"codes": {c: c.replace("_", " ") for c in set(assign.values())}, "assignments": assign}))
    return FakeClient(responder)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample"); s.add_argument("--traces", required=True); s.add_argument("--n", type=int, default=100)
    s.add_argument("--seed", type=int, default=0); s.add_argument("--stratify", default=None)
    s.add_argument("--out", default="labels.csv"); s.add_argument("--force", action="store_true")
    lb = sub.add_parser("label"); lb.add_argument("--traces", required=True); lb.add_argument("--csv", required=True)
    lb.add_argument("--labeler", default="bdfl")
    p = sub.add_parser("propose"); p.add_argument("--csv", required=True); p.add_argument("--k", type=int, default=8)
    r = sub.add_parser("report"); r.add_argument("--csv", required=True); r.add_argument("--results", default=None)
    a = ap.parse_args(argv)

    if a.cmd == "sample":
        if Path(a.out).exists() and not a.force:
            print(f"{a.out} exists; refusing to overwrite labels (use --force)"); return 1
        picked = sample_traces(summarize_traces(a.traces), a.n, a.seed, a.stratify)
        write_label_sheet(picked, a.out)
        print(f"wrote {len(picked)} rows to {a.out}")
    elif a.cmd == "label":
        n = label_interactive(a.csv, summarize_traces(a.traces), a.labeler)
        print(f"labeled {n} traces this session")
    elif a.cmd == "propose":
        codes = [row["open_code"] for row in read_labels(a.csv) if row["pass_fail"] == "fail"]
        print(json.dumps(propose_axial_codes(get_client(fake=_fake_proposer()), codes, a.k), indent=2))
    elif a.cmd == "report":
        results = [json.loads(l) for l in Path(a.results).read_text().splitlines()] if a.results else None
        print(format_report(read_labels(a.csv), results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
