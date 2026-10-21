"""Pareto frontier, upgrade drill, ablation, and the CI gate."""

import json
from pathlib import Path

import pytest

import ci_gate
from incident_router import DEFAULT_CONFIG
from pareto import Point, ablate, ascii_plot, dominates, frontier, grid, step_gain, table, upgrade_drill
from router_eval import load_split
from sim_model import NEW_MODEL

CLIMBED = json.loads((Path(__file__).parent / "data" / "climbed_config.json").read_text())


def P(name, cost, acc):
    return Point(name, cost, acc, acc - 0.03, acc + 0.03)


def test_frontier_by_hand():
    pts = [P("a", 1, 0.80), P("b", 2, 0.85), P("c", 3, 0.84), P("d", 4, 0.90), P("e", 4, 0.88)]
    assert [p.name for p in frontier(pts)] == ["a", "b", "d"]
    assert dominates(pts[1], pts[2]) and not dominates(pts[0], pts[1])


def test_equal_points_do_not_dominate_each_other():
    a, b = P("a", 1, 0.8), P("b", 1, 0.8)
    assert not dominates(a, b) and len(frontier([a, b])) == 2


def test_grid_table_plot_and_drill():
    items = load_split("dev")[:80]
    pts = grid(CLIMBED, items, ["claude-haiku-5-5", "claude-sonnet-5-5"], ["low", "high"], repeats=1)
    assert len(pts) == 4 and all(p.scores for p in pts)
    cheap = min(pts, key=lambda p: p.cost)
    assert "haiku" in cheap.name and "low" in cheap.name
    md = table(pts)
    assert md.count("\n") == 5 and "yes" in md
    assert "*" in ascii_plot(pts)
    pairs = upgrade_drill(frontier(pts), NEW_MODEL, items, repeats=1)
    assert len(pairs) == len(frontier(pts)) and all(n.name.startswith(NEW_MODEL) for _, n in pairs)
    g = step_gain(pairs[0][1], pairs[0][0])
    assert g.n == len(items)


def test_ablation_finds_dead_weight_on_new_model():
    items = load_split("dev")
    res = dict(ablate(dict(CLIMBED, model=NEW_MODEL, effort="low"), items, repeats=2))
    assert res["-section:queue_definitions"].hi < 0      # still load-bearing
    assert res["-section:tiebreak"].lo <= 0 <= res["-section:tiebreak"].hi + 0.01  # no measurable value


def result(scores, clusters=None, fp="f1", cost=0.005, name="x"):
    n = len(scores)
    return {"config": {"name": name}, "fingerprint": fp, "split": "test", "repeats": 1, "client": "sim",
            "ids": [str(i) for i in range(n)], "clusters": clusters or [str(i) for i in range(n)],
            "item_scores": scores, "accuracy": sum(scores) / n, "cost_per_item": cost}


def test_gate_uses_lower_bound_not_point_estimate():
    cand = result([1.0] * 86 + [0.0] * 14)  # 86% point estimate, lower bound ~79%
    ok, rows = ci_gate.check(cand, None, floor=0.85, max_drop=0.02, max_cost_ratio=None)
    assert not ok and "FAIL" not in rows[0][0] and rows[0][1] is False


def test_gate_regression_fingerprint_and_cost():
    base = result([1.0] * 180 + [0.0] * 20)
    same = result([1.0] * 180 + [0.0] * 20)
    worse = result([1.0] * 160 + [0.0] * 40)
    assert ci_gate.check(same, base, 0.8, 0.02, 1.5)[0]
    ok, rows = ci_gate.check(worse, base, 0.7, 0.02, 1.5)
    assert not ok and any("regression" in r[0] and not r[1] for r in rows)
    assert not ci_gate.check(result(same["item_scores"], fp="other"), base, 0.8, 0.02, 1.5)[0]
    assert not ci_gate.check(result(same["item_scores"], cost=0.02), base, 0.8, 0.02, 1.5)[0]


def test_gate_cli_end_to_end(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps(CLIMBED))
    base, cand = tmp_path / "base.json", tmp_path / "cand.json"
    assert ci_gate.main(["run", "--config", str(cfg), "--repeats", "1", "--seed", "0", "--out", str(base)]) == 0
    assert ci_gate.main(["run", "--config", str(cfg), "--repeats", "1", "--seed", "1", "--out", str(cand)]) == 0
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert ci_gate.main(["check", "--results", str(cand), "--baseline", str(base), "--floor", "0.80"]) == 0
    assert "Eval gate: PASS" in summary.read_text()
    bad = dict(DEFAULT_CONFIG)
    cfg.write_text(json.dumps(bad))
    assert ci_gate.main(["run", "--config", str(cfg), "--repeats", "1", "--out", str(cand)]) == 0
    assert ci_gate.main(["check", "--results", str(cand), "--baseline", str(base), "--floor", "0.80"]) == 1


def test_committed_baseline_matches_frozen_evaluator():
    from router_eval import fingerprint
    base = json.loads((Path(__file__).parent / "ci" / "baseline_results.json").read_text())
    assert base["fingerprint"] == fingerprint(), "dataset or grader changed: regenerate ci/baseline_results.json"


def test_make_factory_rejects_unknown():
    with pytest.raises(ValueError):
        ci_gate.make_factory("bogus")
