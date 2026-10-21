# Code for Module 11: LLM-as-judge

Everything runs offline by default. With `ANTHROPIC_API_KEY` set (and `AINATIVE_FAKE` unset), the scripts call the real API through `ainative_kit.get_client()`. Otherwise they use the heuristic fakes in `judge_fakes.py`.

**The fakes are not models.** They are small heuristics with deliberate, known flaws, so the calibration and bias code has something realistic to measure. Every number printed in offline mode describes those heuristics, not Claude.

Run from the course root:

```bash
.venv/bin/python -m pytest -q 11-llm-as-judge/code       # all tests, offline
cd 11-llm-as-judge/code
../../.venv/bin/python judge.py                          # binary judge over the incident data
../../.venv/bin/python calibrate.py                      # TPR/TNR with CIs + corrected pass rate
../../.venv/bin/python compare_judges.py                 # Likert vs binary v1 vs binary v2, confusion matrices
../../.venv/bin/python pairwise.py                       # blinded, position-swapped pairwise A/B
../../.venv/bin/python bias_probes.py                    # position / verbosity / run-to-run probes
```

(The course's `conftest.py` puts `shared/` on the path for pytest. When running a script directly, either set `PYTHONPATH=../../shared` or install the kit with `pip install -e .` from the root.)

## Files

| File | What it does |
|---|---|
| `judge.py` | `Rubric` (one question, checkable PASS claims, FAIL-if triggers, out-of-scope list), `record_verdict` tool schema with `critique` before `verdict`, `judge()`, `judge_many()`, `with_few_shot()` (train split only), `fingerprint()`. Two rubrics: `INCIDENT_IMPACT` and `CODE_REVIEW_BUG`. Unparseable output raises `JudgeOutputError`; it is never a pass. `--fake v1|v2` picks the offline stand-in, and `--write-labels` writes `id/split/human_label/judge_label` JSONL. |
| `calibrate.py` | `confusion()` / `Confusion` (TPR, TNR, accuracy, kappa), `wilson_interval()`, `rogan_gladen()`, `bootstrap_true_pass_rate()` (resamples labels *and* production verdicts), `assign_split()` (hash-stable), `drift_alarms()`, `simulate_judge_verdicts()` (demo only), `report()`. Convention: positive = PASS. |
| `pairwise.py` | `compare()` runs (A, B) and (B, A) blind and combines them; a flip becomes a tie. `summarize()` gives the win rate with ties as half and the inconsistency rate; `sign_test_p()`. |
| `bias_probes.py` | `verbosity_probe_pointwise`, `verbosity_probe_pairwise`, `position_probe`, `swap_consistency`, `double_run_consistency`, `self_preference_gap`. Each takes a plain callable, so it works with fakes or a real client. |
| `compare_judges.py` | The worked example from [02](../02-binary-rubrics-and-critiques.md): an unanchored 1-5 judge (with its threshold chosen on dev) against two binary judges, on dev and test. |
| `judge_fakes.py` | FakeClient responders: `incident_keyword_judge` (v1: exact count only), `incident_rules_judge` (v2: count with rounding, plus scope/severity contradiction rules written from **dev** disagreements only), `likert_length_judge`, `first_position_judge`, `longer_response_judge`, `content_pairwise_judge`, `padded_lenient_judge`. |

## Data

| File | Rows | Notes |
|---|---|---|
| `data/incident_summaries.jsonl` | 60 | 10 synthetic incidents (Kafka rebalance, rate limiter, schema-migration lock, TLS cert, cache stampede, DNS, idempotency bug, batch export, token refresh, email) × 6 candidate summaries. Fields: `facts`, `summary`, `human_label` (pass/fail, 30/30), `human_critique`, `split` (8 train / 27 dev / 25 test, hash-assigned). Hand-written by the module author; the "human" labels are the author's. |
| `data/code_review_comments.jsonl` | 20 | Diffs in Go/Java/Python/SQL with one review comment each. `human_label` pass = identifies a real bug. Includes confident false alarms (CR-006, CR-013, CR-014) and a context-dependent case (CR-009). No splits assigned; exercise 4 does that. |
| `data/incident_judge_labels.jsonl` | 52 | Output of `judge.py --fake v2 --write-labels` on dev+test. `test_committed_judge_labels_match_current_v2_judge` fails if it goes stale. Regenerate with `AINATIVE_FAKE=1 PYTHONPATH=../../shared ../../.venv/bin/python judge.py --write-labels data/incident_judge_labels.jsonl`. |

## Notes on the real API

- The judge forces the verdict tool with `tool_choice={"type": "tool", "name": "record_verdict"}` where supported. If a model still answers in text, `parse_verdict` tries a JSON object in the text, then raises. Count these errors; `judge_many` records them as `"error"`.
- `judge()` doesn't set a temperature. Measure run-to-run consistency with `double_run_consistency` instead of assuming it.
- Use a judge model different from the generator, and record both in the calibration report alongside `fingerprint(rubric, model)`.
