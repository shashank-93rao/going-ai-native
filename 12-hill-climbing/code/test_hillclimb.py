"""Keep/revert rules, change application, guards, and the full logged climb."""

import json
from pathlib import Path

import pytest

import hillclimb
from hillclimb import Climb, Rules, apply_change, decide, leaked_items, load_variants, write_log
from incident_router import DEFAULT_CONFIG
from noise_check import grader_flip_rate, run_noise_check
from router_eval import load_split
from stats import Estimate

VARIANTS = Path(__file__).parent / "data" / "variants.json"


def E(mean, se=0.01):
    return Estimate(mean, se, 200)


@pytest.mark.parametrize("dev,test,want,why", [
    (E(0.01), E(0.01), "revert", "noise"),
    (E(-0.05), E(0.0), "revert", "regression"),
    (E(0.08), E(-0.05), "revert", "significantly DOWN"),
    (E(0.08), E(0.01), "revert", "flat"),       # test gain < half the dev gain
    (E(0.08), E(0.06), "keep", "significant"),
    (E(0.08, 0.02), E(0.05, 0.03), "keep", "directional"),
])
def test_decide_rules(dev, test, want, why):
    decision, reason = decide(dev, test, 1.0, Rules())
    assert decision == want and why in reason


def test_decide_cost_budget_and_strict_test():
    assert decide(E(0.08), E(0.06), 3.0, Rules(max_cost_ratio=2.0))[0] == "revert"
    assert decide(E(0.08), E(0.05, 0.03), 1.0, Rules(require_test_significant=True))[0] == "revert"


def test_apply_change_is_one_change_and_pure():
    best = dict(DEFAULT_CONFIG)
    c1 = apply_change(best, {"add_section": "tiebreak"}, [])
    c2 = apply_change(best, {"add_tool": "lookup_owner"}, [])
    c3 = apply_change(best, {"set": {"effort": "high"}}, [])
    assert c1["sections"] == ["base", "tiebreak"] and best["sections"] == ["base"]
    assert c2["tools"] == ["lookup_owner"] and c3["effort"] == "high"


def test_pasting_failures_is_detected_as_leak():
    dev = load_split("dev")
    cfg = apply_change(DEFAULT_CONFIG, {"paste_dev_failures": 3}, dev[:3])
    assert leaked_items(cfg, dev) == [d["id"] for d in dev[:3]]
    assert leaked_items(DEFAULT_CONFIG, dev) == []


def small_spec(**over):
    spec = load_variants(VARIANTS)
    spec.update(repeats=2, **over)
    return spec


def test_full_climb_reproduces_running_example(tmp_path):
    climb = Climb(load_variants(VARIANTS))
    climb.run()
    log = write_log(climb, tmp_path).read_text()
    by_name = {t.name: t for t in climb.trials}
    assert by_name["v1-step-by-step"].decision == "revert"
    assert by_name["v2-queue-defs"].decision == "keep"
    t3 = by_name["v3-fewshot-failures"]  # the dev-win / test-loss round
    assert t3.decision == "revert" and t3.d_dev.lo > 0 and t3.d_test.hi < 0 and "pasted" in t3.reason
    assert by_name["v6c-effort-xhigh"].decision == "revert" and by_name["v6d-effort-max"].decision == "revert"
    assert climb.best_cfg["effort"] == "high"
    s = climb.summary()
    assert 0.65 <= s["baseline_test"].mean <= 0.75 and s["best_test"].mean >= 0.85 and s["gain_test"].lo > 0
    assert "| **keep** |" in log and "overfit" in log
    assert (tmp_path / "results.tsv").read_text().count("\n") == len(climb.trials) + 1
    assert json.loads((tmp_path / "best_config.json").read_text())["name"] == climb.best_cfg["name"]


def test_block_leaks_blocks_without_running(tmp_path):
    spec = small_spec(rules={"block_leaks": True})
    spec["rounds"] = [r for r in spec["rounds"] if r["name"] == "v3-fewshot-failures"]
    climb = Climb(spec)
    climb.run()
    assert climb.trials[-1].decision == "blocked"
    assert "blocked" in write_log(climb, tmp_path).read_text()


def test_frozen_evaluator_guard(monkeypatch):
    spec = small_spec()
    spec["rounds"] = spec["rounds"][:1]
    climb = Climb(spec)
    monkeypatch.setattr(hillclimb, "fingerprint", lambda *a, **k: "tampered")
    with pytest.raises(RuntimeError, match="evaluator or dataset changed"):
        climb.run()


def test_yaml_variants(tmp_path):
    yaml = pytest.importorskip("yaml")
    p = tmp_path / "v.yaml"
    p.write_text(yaml.safe_dump(load_variants(VARIANTS)))
    assert load_variants(p)["rounds"][0]["name"] == "v1-step-by-step"


def test_noise_check_report():
    dev = load_split("dev")
    rep = run_noise_check(DEFAULT_CONFIG, dev, runs=4, planned_repeats=4, min_effect=0.05)
    assert rep.ok and abs(rep.null_diff) < 0.03 and 0 < rep.flip_rate < 0.5
    assert rep.clustered_se >= rep.naive_se * 0.9
    strict = run_noise_check(DEFAULT_CONFIG, dev, runs=4, planned_repeats=1, min_effect=0.01)
    assert not strict.ok and strict.repeats_needed() > 1
    assert "TOO NOISY" in strict.to_markdown()
    with pytest.raises(ValueError):
        run_noise_check(DEFAULT_CONFIG, dev, runs=3)


def test_grader_flip_rate():
    flips = iter([1, 0, 1, 1])
    assert grader_flip_rate(lambda o, r: next(flips), [("a", "a"), ("b", "b")]) == 0.5
    assert grader_flip_rate(lambda o, r: int(o == r), [("a", "a")]) == 0.0
