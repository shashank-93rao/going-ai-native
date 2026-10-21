# Capstone starter code

Both scaffolds run offline with `FakeClient`, and switch to the real API when `ANTHROPIC_API_KEY` is set and `AINATIVE_FAKE` is not. All model calls go through `ainative_kit`.

Run the tests from the course root:

```bash
.venv/bin/python -m pytest -q 99-capstone/code
```

Run the scripts from this directory with the shared kit on the path:

```bash
cd 99-capstone/code
export PYTHONPATH=../../shared
```

## Variant A: ops agent

| File | What it is |
|---|---|
| `sim_env.py` | Deterministic simulated backend: 5 services, a dependency graph, 6 fault kinds, optional prompt injection in logs. `make_scenario(seed)`, `make_suite(n)`, `SimEnv.call(tool, args)`, `SimEnv.healthy()`, `oracle_actions(scenario)`, `TOOL_SCHEMAS` |
| `grade.py` | `grade(scenario, env)` returns outcome and trajectory checks, pass/fail and a `correct / abstain / wrong` label. `summarize(grades, k)` gives pass rate with a CI clustered by scenario, pass^k, pass@k, per-kind and per-check rates |
| `starter_agent.py` | The agent loop with governors (steps, tokens, identical-call repeats) and tracing. `baseline_responder` is a naive offline "model" with deliberate failure modes |
| `test_ops_scaffold.py` | Determinism; the oracle passes every kind with and without injection; known-bad trajectories (db restart, followed injection, decoy rollback, false-alarm mutation, unverified close, loops) fail on the right check; governors trip; stats helpers |

```bash
AINATIVE_FAKE=1 python starter_agent.py --n 48 --traces runs/traces.jsonl --out runs/grades.jsonl
python starter_agent.py --n 12 --trials 3          # real model, pass^3 reported
```

Offline baseline, measured 2026-10-19: pass rate 0.396, 95% CI [0.258, 0.534] on 48 scenarios.

## Variant B: LLM pipeline

| File | What it is |
|---|---|
| `make_postmortems.py` | Deterministic generator of synthetic postmortems and gold labels, with `hard_features` tags. Already run: output is in `data/` |
| `data/postmortems/pm-000.md` … `pm-019.md` | 20 documents |
| `data/labels.jsonl` | Gold labels, one row per document |
| `pipeline_v0.py` | Map (one extraction call per doc), reduce in code (stats), reduce by LLM (action-item themes). `naive_extractor_responder` is a regex "model" with realistic blind spots |
| `score.py` | Field-level precision/recall/F1, error rows for analysis, bootstrap CI on micro F1, paired bootstrap between two prediction files |
| `test_pipeline_scaffold.py` | Data present and reproducible from the generator; hard features really appear in the text; gold scores 1.0, empty scores 0 recall; counting rules; pipeline runs offline and fails where the hard features predict; paired bootstrap behaves |

```bash
AINATIVE_FAKE=1 python pipeline_v0.py --out runs/preds_v0.jsonl --traces runs/pipe_traces.jsonl
python score.py runs/preds_v0.jsonl
python score.py runs/preds_v1.jsonl --baseline runs/preds_v0.jsonl     # paired comparison
python make_postmortems.py --n 60 --seed 7 --out data_big                # more synthetic docs for M2
```

Offline baseline, measured 2026-10-19: micro P 0.619, R 0.836, F1 0.711.

## Rules for extending
- Keep grading code (`grade.py`, `score.py`, labels, splits) out of reach of any coding agent you use to build the system, or review every diff to it by hand.
- If you change the simulator or generator, rerun the tests: `test_committed_data_matches_generator` will tell you to regenerate `data/`, and the oracle tests will tell you if a scenario became unsolvable.
- No extra packages are required. `hypothesis` (in the course venv) is used in the M2 property-test example.
