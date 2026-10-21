# Module 12 code: hill-climbing the incident router

Everything runs offline against a **simulated model** (`sim_model.py`). That is a seeded `FakeClient` responder with a known response to each lever, so the full climb, the noise check, the frontier, and the gate run in seconds and reproduce exactly. It does not measure Claude. With `ANTHROPIC_API_KEY` set (and `AINATIVE_FAKE` unset), the scripts that accept a client use the real API through `ainative_kit`.

Standard library only (plus `ainative_kit`). PyYAML is used for `.yaml` variant files if it is installed; the JSON form needs nothing.

## Run

From the course root:

```bash
.venv/bin/python -m pytest -q 12-hill-climbing/code        # 58 tests, offline, a few seconds
```

From this directory (so `ainative_kit` is importable):

```bash
export PYTHONPATH=../../shared AINATIVE_FAKE=1
python stats.py                                   # the textbook numbers (Eugene Yan's CIs, McNemar, sample sizes)
python router_eval.py                             # baseline on dev, naive vs clustered CI, accuracy by failure family
python noise_check.py --runs 6 --repeats 4        # noise check before round 1
python hillclimb.py data/variants.json --out runs/demo   # the full climb -> runs/demo/experiments.md, results.tsv
python pareto.py --drill candidate-model-x        # model x effort frontier, upgrade drill, ablation
python ci_gate.py run --config data/climbed_config.json --split test --out /tmp/r.json
python ci_gate.py check --results /tmp/r.json --baseline ci/baseline_results.json --floor 0.85
python make_incidents.py --clusters 160 --out data/small.jsonl   # a smaller eval for the power exercise
```

## Files

| File | What it is |
|---|---|
| `stats.py` | Mean/SE, binomial SE, clustered SE, paired difference, paired (cluster) bootstrap, McNemar, CI half-width, required-n calculators (margin, two proportions, paired), MDE, design effect |
| `incident_router.py` | The system under test: config-driven prompt assembly, a bounded tool loop (`lookup_owner`), `team:` parsing, list prices and cost |
| `sim_model.py` | The simulated model: responds to prompt sections, pasted examples, tools, effort, and model tier; clustered difficulty; per-alert latent difficulty with per-call jitter |
| `make_incidents.py` | Generates `data/incidents.jsonl`: 969 alerts in 320 incidents, split by incident, stratified by failure family, each with a plausible "decoy" wrong team |
| `router_eval.py` | The **frozen evaluator**: grader, runner, `RunResult` (per-item scores), fingerprint |
| `noise_check.py` | Runs the baseline N times; reports run SD, flip rate, naive/clustered SE, null paired SE, MDE, and a verdict |
| `hillclimb.py` | Experiment runner: variants file, one change per round, sweeps, fresh seeds, paired clustered deltas on dev and test, `decide()` rules, leak blocking, fingerprint guard, `experiments.md` + `results.tsv` + `best_config.json` writer |
| `pareto.py` | Model × effort grid, Pareto frontier with paired step tests, ASCII plot, upgrade drill, ablation |
| `ci_gate.py` | `run` (sim / replay / real client) and `check` (floor on lower bound, paired regression, fingerprint, cost) with `$GITHUB_STEP_SUMMARY` output |
| `ci/.github/workflows/eval-gate.yml` | Example three-tier GitHub Actions gate |
| `ci/baseline_results.json` | Baseline for the mocked tier (regenerate when the fingerprint changes) |
| `data/variants.json` | The canonical climb |
| `data/climbed_config.json` | The climb's winner |
| `data/targets.yaml` | Reliability targets: the stopping criterion |
| `data/prompts/*.md` | Prompt sections the configs compose |
| `runs/demo/` | Output of the canonical climb, committed as the reference log |
| `test_*.py` | Tests, including stats against hand-computed and published values |

## Regenerating artifacts

If you change `make_incidents.py`, `router_eval.py`, or the simulator, regenerate in this order:

```bash
python make_incidents.py
python hillclimb.py data/variants.json --out runs/demo && cp runs/demo/best_config.json data/climbed_config.json
python ci_gate.py run --config data/climbed_config.json --split test --repeats 3 --seed 0 --out ci/baseline_results.json
```

`test_pareto_ci.py::test_committed_baseline_matches_frozen_evaluator` fails if you forget the last step.

## Using the real API, and forwarding effort

`route()` passes each variant's `effort` to `client.complete(effort=...)`, and `ainative_kit.AnthropicClient` sends it as `output_config={"effort": ...}`. Allowed values are `"low" | "medium" | "high" | "xhigh" | "max"`. That shape was checked against the claude-api skill reference cached 2026-10; verify it against current docs. With `ANTHROPIC_API_KEY` set, the default factory uses the real API:

```python
from ainative_kit import AnthropicClient

real_factory = lambda cfg, seed: AnthropicClient(model=cfg["model"])
# Climb(spec, client_factory=real_factory).run()
```

Notes for real runs:
- Do not set `temperature` on current models; non-default sampling parameters are rejected on several of them.
- Check `stop_reason` for `"refusal"` as well as `"max_tokens"` before parsing. The router scores both as misses; count them separately.
- Cost: the full canonical climb is about 10 evaluations × 2 splits × 4 repeats × ~480 alerts, roughly 40k calls. Shrink the splits and repeats first (exercise 7).
