"""Cost vs accuracy frontier across model x effort, and the model-upgrade drill.

    python pareto.py                      # grid over models x efforts on the climbed config
    python pareto.py --drill candidate-model-x

A config is on the frontier if no other config is at least as accurate AND at
least as cheap (and strictly better on one). Means alone over-trust the
frontier, so each frontier step is also tested with a PAIRED, clustered
difference against the next-cheaper frontier point (same items, so pairing is
valid). A step whose CI spans 0 is "not distinguishable from cheaper": you would
be paying for noise.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from router_eval import ClientFactory, evaluate, load_split, sim_factory
from stats import Estimate, clustered_se, paired_diff

MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
EFFORTS = ["low", "medium", "high"]
CLIMBED = Path(__file__).parent / "data" / "climbed_config.json"


@dataclass(frozen=True)
class Point:
    name: str
    cost: float  # $ per 1k items
    acc: float
    lo: float
    hi: float
    config: dict[str, Any] | None = None
    scores: tuple[float, ...] = ()
    clusters: tuple[str, ...] = ()


def dominates(a: Point, b: Point) -> bool:
    return a.acc >= b.acc and a.cost <= b.cost and (a.acc > b.acc or a.cost < b.cost)


def frontier(points: list[Point]) -> list[Point]:
    """Non-dominated points, sorted by cost."""
    keep = [p for p in points if not any(dominates(q, p) for q in points if q is not p)]
    return sorted(keep, key=lambda p: p.cost)


def step_gain(p: Point, cheaper: Point) -> Estimate:
    """Paired, clustered accuracy gain of p over a cheaper config on the same items."""
    return paired_diff(list(cheaper.scores), list(p.scores), list(p.clusters))


def _point(cfg: dict[str, Any], r: Any) -> Point:
    est = clustered_se(r.item_scores, r.clusters)
    return Point(cfg["name"], 1000 * r.cost_per_item, est.mean, est.lo, est.hi, cfg,
                 tuple(r.item_scores), tuple(r.clusters))


def grid(base: dict[str, Any], items: list[dict], models: list[str], efforts: list[str],
         repeats: int = 3, seed: int = 5, factory: ClientFactory = sim_factory) -> list[Point]:
    pts = []
    for i, m in enumerate(models):
        for j, e in enumerate(efforts):
            cfg = copy.deepcopy(base)
            cfg.update(model=m, effort=e, name=f"{m.removeprefix('claude-')}/{e}")
            r = evaluate(cfg, items, repeats, seed + 31 * (i * 10 + j), factory)
            pts.append(_point(cfg, r))
    return pts


def table(points: list[Point]) -> str:
    front = frontier(points)
    names = {p.name for p in front}
    prev = {b.name: a for a, b in zip(front, front[1:])}
    rows = ["| config | $/1k | accuracy [95% CI] | frontier | gain over next-cheaper frontier point |",
            "|---|---|---|---|---|"]
    for p in sorted(points, key=lambda p: p.cost):
        note = ""
        if p.name in prev and p.scores:
            g = step_gain(p, prev[p.name])
            verdict = "real" if g.lo > 0 else "not distinguishable"
            note = f"{g.fmt()} pts vs {prev[p.name].name}: {verdict}"
        rows.append(f"| {p.name} | {p.cost:.2f} | {100 * p.acc:.1f} [{100 * p.lo:.1f}, {100 * p.hi:.1f}] "
                    f"| {'yes' if p.name in names else ''} | {note} |")
    return "\n".join(rows)


def ascii_plot(points: list[Point], width: int = 64, height: int = 16) -> str:
    """Accuracy (y) vs log cost (x). '*' = frontier, 'o' = dominated, labels by index."""
    front = {p.name for p in frontier(points)}
    xs = [math.log10(p.cost) for p in points]
    ys = [p.acc for p in points]
    x0, x1 = min(xs), max(xs) + 1e-9
    y0, y1 = min(ys) - 0.01, max(ys) + 0.01
    canvas = [[" "] * width for _ in range(height)]
    legend = []
    for k, (p, x, y) in enumerate(zip(points, xs, ys)):
        cx = int((x - x0) / (x1 - x0) * (width - 4))
        cy = height - 1 - int((y - y0) / (y1 - y0) * (height - 1))
        mark = "*" if p.name in front else "o"
        label = f"{mark}{k}"
        for d, ch in enumerate(label):
            if cx + d < width:
                canvas[cy][cx + d] = ch
        legend.append(f"{k}={p.name}")
    lines = [f"{100 * (y1 - (y1 - y0) * r / (height - 1)):5.1f} |" + "".join(row) for r, row in enumerate(canvas)]
    lines.append("      +" + "-" * width)
    lines.append(f"       ${10 ** x0:.2f}/1k  (log cost)  ${10 ** x1:.2f}/1k")
    lines.append("       " + "  ".join(legend))
    return "\n".join(lines)


def upgrade_drill(front: list[Point], new_model: str, items: list[dict], repeats: int = 3,
                  seed: int = 9, factory: ClientFactory = sim_factory) -> list[tuple[Point, Point]]:
    """Re-run each frontier config with the model swapped. Returns (old, new) pairs."""
    out = []
    for k, p in enumerate(front):
        cfg = copy.deepcopy(p.config or {})
        cfg.update(model=new_model, name=f"{new_model}/{cfg.get('effort')}")
        r = evaluate(cfg, items, repeats, seed + 17 * k, factory)
        out.append((p, _point(cfg, r)))
    return out


def ablate(config: dict[str, Any], items: list[dict], repeats: int = 3, seed: int = 13,
           factory: ClientFactory = sim_factory) -> list[tuple[str, Estimate]]:
    """Remove each prompt section and tool in turn; report the paired accuracy change.

    Every scaffold encodes an assumption about a model's weakness. On a new model,
    a component whose removal costs nothing (CI spans 0) is a candidate to delete.
    """
    full = evaluate(config, items, repeats, seed, factory)
    out = []
    parts = [("section", s) for s in config["sections"] if s != "base"] + [("tool", t) for t in config.get("tools", [])]
    for k, (kind, name) in enumerate(parts):
        cfg = copy.deepcopy(config)
        if kind == "section":
            cfg["sections"] = [s for s in cfg["sections"] if s != name]
        else:
            cfg["tools"] = [t for t in cfg["tools"] if t != name]
        r = evaluate(cfg, items, repeats, seed + 101 * (k + 1), factory)
        out.append((f"-{kind}:{name}", paired_diff(full.item_scores, r.item_scores, r.clusters)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="cost/accuracy frontier")
    ap.add_argument("--config", default=str(CLIMBED))
    ap.add_argument("--split", default="dev")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--drill", metavar="NEW_MODEL", help="re-run frontier configs on a new model")
    args = ap.parse_args()
    base = json.loads(Path(args.config).read_text())
    items = load_split(args.split)
    pts = grid(base, items, MODELS, EFFORTS, args.repeats)
    print(table(pts))
    print()
    print(ascii_plot(pts))
    if args.drill:
        print(f"\n## Upgrade drill: frontier configs re-run on {args.drill}\n")
        print("| frontier config | old acc | new acc | paired gain [95% CI] | old $/1k | new $/1k |")
        print("|---|---|---|---|---|---|")
        for old, new in upgrade_drill(frontier(pts), args.drill, items, args.repeats):
            g = step_gain(new, old)
            print(f"| {old.name} | {100 * old.acc:.1f} | {100 * new.acc:.1f} | {g.fmt()} "
                  f"| {old.cost:.2f} | {new.cost:.2f} |")
        print(f"\n## Ablation on {args.drill} (low effort): remove one component at a time\n")
        print("| removed | paired change [95% CI] | verdict |\n|---|---|---|")
        for name, d in ablate(dict(base, model=args.drill, effort="low"), items, args.repeats):
            verdict = "still load-bearing" if d.hi < 0 else "no measurable value: candidate to delete"
            print(f"| {name} | {d.fmt()} | {verdict} |")


if __name__ == "__main__":
    main()
