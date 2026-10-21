# Module 10 code

Everything runs offline with deterministic fakes. With `ANTHROPIC_API_KEY` set (and `AINATIVE_FAKE` unset), the scripts call the real model through `ainative_kit.get_client`. Tests always run offline: `conftest.py` forces `AINATIVE_FAKE=1`.

Run all commands from this directory with the course venv active (`source ../../.venv/bin/activate`). The venv has `ainative_kit` installed in editable mode, so no `PYTHONPATH` is needed.

## Files
| File | What it is |
|---|---|
| `ticket_router.py` | The single-turn system under test: alert in, `{decision, team, severity, rationale}` JSON out. Includes the system prompt, `prompt_hash`, a strict parser, tracing, and `fake_router_client`, a deterministic fake with planted flaws (keyword over-matching, severity under-calls and over-calls, overconfident guessing, secret echoing, fenced JSON on one source, random tie-breaking). `cautious=True` gives a variant that abstains on ambiguity. |
| `graders.py` | Code graders: schema, exact match, ordinal distance, regex (secret patterns), the three-way outcome (correct, abstain, wrong), and agentic graders (file hash, pytest in a subprocess, claim vs outcome). |
| `eval_harness.py` | Dataset JSONL → n trials per case → graders → `results.jsonl` + `results.summary.json` + a printed table with pass rate, pass@k, pass^k, correct/abstain/wrong, abstention-aware score, per split and per slice. Optional `--traces` writes `ainative_kit.Tracer` spans. |
| `coding_task.py` | The agentic eval: a tool-loop agent fixes a token-bucket rate limiter in a fresh temp dir per trial. Graded on visible-test integrity (hash), hidden tests written after the run, and whether the agent's claim matches the outcome. Three fake trajectories: `full_fix`, `partial_fix`, `test_editor`. |
| `error_analysis.py` | Loads traces, renders one trace per screen (grader verdict hidden), samples (optionally stratified), writes a label CSV, runs an interactive, resumable labeling loop, counts axial codes, prints a saturation curve and a transition failure matrix, compares human labels with grader verdicts, and can ask a model to propose axial codes. |
| `synth_data.py` | Dimension-tuple synthetic data: cross product, filter rules, stratified sampling, one writer prompt per tuple, rule-drafted labels marked `needs_review`. |
| `data/router_cases.jsonl` | 43 router cases (fictional but realistic): 37 route, 6 abstain; slices per team plus `abstain`, `negative_control`, `misleading_keyword`, `secret_in_body`; 29 dev, 14 test. |
| `data/synth_cases.jsonl` | 24 synthetic draft cases produced by `synth_data.py` with the offline fake writer. |
| `test_*.py` | Tests for all of the above. |

## Run
```bash
# Router suite, 5 trials per case, with traces
python eval_harness.py --trials 5 --k 1 3 5 --traces traces.jsonl
python eval_harness.py --trials 5 --cautious --out cautious.jsonl      # compare variants
python eval_harness.py --split test --trials 3 --model claude-haiku-5-5  # real API, test split only

# Agentic suite
python coding_task.py --trials 10 --traces coding_traces.jsonl

# Error analysis
python error_analysis.py sample  --traces traces.jsonl --n 100 --stratify slice --out labels.csv
python error_analysis.py label   --traces traces.jsonl --csv labels.csv --labeler you
python error_analysis.py propose --csv labels.csv
python error_analysis.py report  --csv labels.csv --results results.jsonl

# Synthetic data
python synth_data.py --n 24 --out synth.jsonl
python eval_harness.py --dataset synth.jsonl --trials 1 --k 1
```

## Test
From the course root:

```bash
.venv/bin/python -m pytest -q 10-evals-fundamentals/code
```

The coding-task tests start pytest subprocesses for the hidden and visible tests, so the suite takes about 20 seconds.

## Notes
- Real-API runs cost one call per case per trial for the router (43 × trials), and up to 8 calls per trial for the coding agent.
- `sample` refuses to overwrite an existing label sheet; pass `--force` if you mean it.
- The labeling loop saves after every label with an atomic rename, so you can quit (`q`) and resume.
- No packages beyond the course venv are needed.
