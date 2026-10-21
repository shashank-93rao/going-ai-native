"""Online evals: sample production traces, run code checks and a judge, compute SLIs, raise alerts.

Pipeline (run it on a schedule, e.g. every 5 minutes over the last window):

    traces --summarize--> TraceSummary --sample--> checks (+ judge on a subsample)
           --> SLIs with confidence intervals --> SLO threshold alerts + burn-rate alerts

Code checks are cheap and deterministic, so run them on 100% of traffic.
Judges cost money and need calibration, so run them on a consistent-hash sample and
report the judge's pass rate corrected for its measured TPR/TNR.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from ainative_kit import LLMClient
from pricing import cache_hit_rate, cached_input_share, cost_usd


@dataclass
class TraceSummary:
    trace_id: str
    ts: float
    model: str
    prompt_version: str
    latency_s: float
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    output: str
    input_service: str | None = None
    feedback: int | None = None
    followup: str | None = None
    guardrail_blocked: bool = False
    error: str | None = None

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.model, input_tokens=self.input_tokens, output_tokens=self.output_tokens,
                        cache_read_tokens=self.cache_read_tokens, cache_write_tokens=self.cache_write_tokens)


def summarize(spans: list[dict[str, Any]]) -> TraceSummary:
    """Collapse one trace (root agent_run + llm_call children) into a row you can evaluate."""
    root = next(s for s in spans if s["parent_id"] is None)
    llms = [s for s in spans if s["name"] == "llm_call"]
    last = llms[-1]["attrs"] if llms else {}
    tot = lambda k: sum(int(s["attrs"].get(k, 0)) for s in llms)  # noqa: E731
    ra = root["attrs"]
    return TraceSummary(
        trace_id=root["trace_id"], ts=root["start"], model=last.get("model", "unknown"),
        prompt_version=ra.get("prompt_version") or last.get("prompt_version", "unknown"),
        latency_s=(root["end"] or root["start"]) - root["start"],
        input_tokens=tot("input_tokens"), cache_read_tokens=tot("cache_read_tokens"),
        cache_write_tokens=tot("cache_write_tokens"), output_tokens=tot("output_tokens"),
        output=last.get("output", ""), input_service=ra.get("input_service"), feedback=ra.get("feedback"),
        followup=ra.get("followup"), guardrail_blocked=bool(ra.get("guardrail_blocked")),
        error=root.get("error") or next((s["error"] for s in spans if s.get("error")), None),
    )


# ---------- sampling ----------

def in_sample(trace_id: str, rate: float, salt: str = "judge-v1") -> bool:
    """Consistent hash sampling: the same trace is always in or out for a given salt.

    Unlike random.random(), this lets two independent jobs (judge, human review queue)
    agree on the sample without coordination, and makes reruns reproducible.
    """
    h = int(hashlib.sha256(f"{salt}:{trace_id}".encode()).hexdigest()[:8], 16)
    return h / 0xFFFFFFFF < rate


def select_for_judge(rows: Iterable[TraceSummary], rate: float, salt: str = "judge-v1") -> list[TraceSummary]:
    """Uniform sample only, so the judged pass rate estimates the population.

    Do NOT add 'always judge thumbs-down traces' here: that biases the SLI. Send those to a
    human review queue instead (see review_queue).
    """
    return [r for r in rows if in_sample(r.trace_id, rate, salt)]


def review_queue(rows: Iterable[TraceSummary], results: dict[str, dict[str, bool | None]]) -> list[str]:
    """Traces a human should read: negative feedback, guardrail blocks, or any failed check."""
    out = []
    for r in rows:
        failed = any(v is False for v in results.get(r.trace_id, {}).values())
        if r.feedback == -1 or r.guardrail_blocked or r.error or failed:
            out.append(r.trace_id)
    return out


# ---------- checks ----------

Check = Callable[[TraceSummary], "bool | None"]  # None = not applicable
REQUIRED = {"service", "severity", "summary", "runbook"}
NEG_FOLLOWUP = re.compile(r"\b(wrong|useless|not (what|the)|again)\b", re.I)
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}|AKIA[0-9A-Z]{16}")


def _parse(out: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(out)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def check_schema(r: TraceSummary) -> bool:
    obj = _parse(r.output)
    return obj is not None and REQUIRED <= obj.keys() and obj["severity"] in {"sev1", "sev2", "sev3"}


def check_grounded_service(r: TraceSummary) -> bool | None:
    obj = _parse(r.output)
    if obj is None or r.input_service is None:
        return None  # schema check already counts this failure; don't double count
    return obj.get("service") == r.input_service


def check_no_secret(r: TraceSummary) -> bool:
    return not SECRET.search(r.output)


def check_no_negative_followup(r: TraceSummary) -> bool | None:
    """Implicit feedback: the user's next message says the answer was wrong."""
    return None if r.followup is None else not NEG_FOLLOWUP.search(r.followup)


CODE_CHECKS: dict[str, Check] = {
    "schema_valid": check_schema,
    "grounded_service": check_grounded_service,
    "no_secret_in_output": check_no_secret,
    "no_negative_followup": check_no_negative_followup,
}


class LLMJudge:
    """Binary judge. Frozen prompt, separate model from the one being judged, calibrated offline."""

    def __init__(self, client: LLMClient, rubric: str, *, model: str | None = None, tpr: float = 1.0, tnr: float = 1.0):
        self.client, self.rubric, self.model = client, rubric, model
        self.tpr, self.tnr = tpr, tnr  # measured on a human-labelled set (Module 11)

    def __call__(self, r: TraceSummary) -> bool | None:
        prompt = f"{self.rubric}\n\n<output>\n{r.output}\n</output>\n\nAnswer with exactly PASS or FAIL on the first line."
        resp = self.client.complete([{"role": "user", "content": prompt}], model=self.model, max_tokens=50, temperature=0)
        first = (resp.text.strip().splitlines() or [""])[0].strip().upper()
        return True if first == "PASS" else False if first == "FAIL" else None  # unparseable -> unknown


def run_checks(rows: Iterable[TraceSummary], checks: dict[str, Check]) -> dict[str, dict[str, bool | None]]:
    return {r.trace_id: {name: fn(r) for name, fn in checks.items()} for r in rows}


# ---------- statistics ----------

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion. Behaves at small n and near 0/1, unlike Wald."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def corrected_pass_rate(observed: float, tpr: float, tnr: float) -> float:
    """Rogan-Gladen correction: true pass rate from a judge's observed pass rate.

    tpr = P(judge PASS | truly good), tnr = P(judge FAIL | truly bad).
    observed = tpr*theta + (1-tnr)*(1-theta)  =>  theta = (observed + tnr - 1) / (tpr + tnr - 1)
    """
    denom = tpr + tnr - 1
    if denom <= 0:
        raise ValueError("judge is no better than chance (tpr + tnr <= 1); fix it before trusting it")
    return min(1.0, max(0.0, (observed + tnr - 1) / denom))


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    idx = min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))
    return s[idx]


@dataclass
class SLI:
    name: str
    value: float
    n: int
    lo: float | None = None
    hi: float | None = None
    raw: float | None = None  # judge SLIs: the uncorrected observed pass rate


def compute_slis(rows: list[TraceSummary], results: dict[str, dict[str, bool | None]],
                 judge_results: dict[str, bool | None] | None = None, judge: LLMJudge | None = None) -> dict[str, SLI]:
    slis: dict[str, SLI] = {}
    names = {k for res in results.values() for k in res}
    for name in sorted(names):
        vals = [res[name] for res in results.values() if res.get(name) is not None]
        k, n = sum(1 for v in vals if v), len(vals)
        lo, hi = wilson(k, n)
        slis[name] = SLI(name, k / n if n else float("nan"), n, lo, hi)
    if judge_results:
        vals = [v for v in judge_results.values() if v is not None]
        k, n = sum(vals), len(vals)
        lo, hi = wilson(k, n)
        tpr, tnr = (judge.tpr, judge.tnr) if judge else (1.0, 1.0)
        corr = lambda x: corrected_pass_rate(x, tpr, tnr)  # noqa: E731
        slis["judge_faithful"] = SLI("judge_faithful", corr(k / n) if n else float("nan"), n, corr(lo), corr(hi), raw=k / n if n else None)
    lat = [r.latency_s for r in rows]
    slis["latency_p95_s"] = SLI("latency_p95_s", percentile(lat, 0.95), len(lat))
    slis["cost_per_request_usd"] = SLI("cost_per_request_usd", sum(r.cost_usd for r in rows) / max(1, len(rows)), len(rows))
    reads, writes = sum(r.cache_read_tokens for r in rows), sum(r.cache_write_tokens for r in rows)
    slis["cache_hit_rate"] = SLI("cache_hit_rate", cache_hit_rate(reads, writes), len(rows))
    slis["cached_input_share"] = SLI("cached_input_share", cached_input_share(sum(r.input_tokens for r in rows), reads, writes), len(rows))
    fb = [r.feedback for r in rows if r.feedback is not None]
    slis["thumbs_down_rate"] = SLI("thumbs_down_rate", sum(1 for f in fb if f < 0) / max(1, len(rows)), len(rows))
    slis["guardrail_block_rate"] = SLI("guardrail_block_rate", sum(r.guardrail_blocked for r in rows) / max(1, len(rows)), len(rows))
    return slis


# ---------- alerting ----------

@dataclass
class Threshold:
    sli: str
    op: str          # ">=" means the SLI must stay at or above `value`
    value: float
    severity: str = "ticket"
    min_n: int = 30  # do not alert on tiny samples
    use_bound: bool = True  # compare the CI bound in the alerting direction, not the point estimate


@dataclass
class Alert:
    sli: str
    severity: str
    message: str


def evaluate_thresholds(slis: dict[str, SLI], rules: list[Threshold]) -> list[Alert]:
    """Alert only when the evidence is clear: for '>=' rules, page when even the CI *upper*
    bound is below target (we are confident it is bad), not when the point estimate dips."""
    alerts = []
    for rule in rules:
        s = slis.get(rule.sli)
        if s is None or s.n < rule.min_n or math.isnan(s.value):
            continue
        if rule.op == ">=":
            v = s.hi if (rule.use_bound and s.hi is not None) else s.value
            if v < rule.value:
                alerts.append(Alert(rule.sli, rule.severity, f"{rule.sli}={s.value:.3f} (n={s.n}, upper={v:.3f}) < {rule.value}"))
        else:
            v = s.lo if (rule.use_bound and s.lo is not None) else s.value
            if v > rule.value:
                alerts.append(Alert(rule.sli, rule.severity, f"{rule.sli}={s.value:.4g} (n={s.n}) > {rule.value}"))
    return alerts


@dataclass
class BurnWindow:
    long_s: float
    short_s: float
    factor: float
    severity: str


# Multiwindow, multi-burn-rate alerts as in the Google SRE Workbook, for a 30-day SLO.
DEFAULT_BURN_WINDOWS = [
    BurnWindow(3600, 300, 14.4, "page"),        # 2% of a 30-day budget in 1 hour
    BurnWindow(6 * 3600, 1800, 6.0, "page"),    # 5% in 6 hours
    BurnWindow(3 * 86400, 6 * 3600, 1.0, "ticket"),  # 10% in 3 days
]


def burn_rate(events: list[tuple[float, bool]], start: float, end: float, objective: float) -> tuple[float, int]:
    """(bad fraction / allowed bad fraction) over [start, end). events = (ts, good)."""
    win = [g for ts, g in events if start <= ts < end]
    if not win:
        return 0.0, 0
    bad = sum(1 for g in win if not g) / len(win)
    return bad / (1 - objective), len(win)


def burn_rate_alerts(sli: str, events: list[tuple[float, bool]], objective: float, now: float,
                     windows: list[BurnWindow] = DEFAULT_BURN_WINDOWS, min_n: int = 20) -> list[Alert]:
    """Fire when BOTH the long and short window burn faster than `factor` (long = significance,
    short = it is still happening, so the alert resets quickly after a rollback)."""
    alerts = []
    for w in windows:
        long_br, n_long = burn_rate(events, now - w.long_s, now, objective)
        short_br, _ = burn_rate(events, now - w.short_s, now, objective)
        if n_long >= min_n and long_br > w.factor and short_br > w.factor:
            alerts.append(Alert(sli, w.severity, f"{sli} burning {long_br:.1f}x over {w.long_s/3600:g}h "
                                                 f"(short {short_br:.1f}x), objective {objective}"))
    return alerts


if __name__ == "__main__":
    from ainative_kit import FakeClient, get_client, text
    from prod_fixtures import generate, group

    rows = [summarize(sp) for sp in group(generate()).values()]
    results = run_checks(rows, CODE_CHECKS)
    sample = select_for_judge(rows, rate=0.5)
    # Stand-in judge: fails ungrounded or truncated notes, and is wrong on ~5% of traces
    # (like a real judge with TPR/TNR around 0.95). With a key set, a real model judges.
    def fake_judge(msgs, kw):
        body = msgs[0]["content"]
        bad = "billing-legacy" in body or '"summary": "Lag."' in body
        noisy = int(hashlib.sha256(body.encode()).hexdigest(), 16) % 20 == 0
        return text("PASS" if bad == noisy else "FAIL")

    judge = LLMJudge(get_client(fake=FakeClient(fake_judge)), "Does the summary only state facts present in the alert?",
                     model="claude-haiku-5-5", tpr=0.95, tnr=0.95)
    judged = {r.trace_id: judge(r) for r in sample}
    slis = compute_slis(rows, results, judged, judge)
    for s in slis.values():
        ci = f" [{s.lo:.3f}, {s.hi:.3f}]" if s.lo is not None else ""
        raw = f"  (raw judge pass rate {s.raw:.3f})" if s.raw is not None else ""
        print(f"{s.name:24s} {s.value:10.4f}{ci}  n={s.n}{raw}")
    rules = [Threshold("schema_valid", ">=", 0.97, "page"), Threshold("cache_hit_rate", ">=", 0.85, "ticket", use_bound=False),
             Threshold("latency_p95_s", "<=", 3.0, "ticket", use_bound=False)]
    for a in evaluate_thresholds(slis, rules):
        print("ALERT", a.severity, a.message)
    print("review queue:", len(review_queue(rows, results)), "traces")
