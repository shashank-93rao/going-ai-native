# 06: CI eval gates

## The idea

A hill-climb raises the number once. A **CI eval gate** keeps it there. It turns the eval into infrastructure: every change that can move model behavior (prompts, tool descriptions, harness code, model IDs, effort settings) runs through the eval before it merges, and the merge is blocked when the result is a confident regression.

Two design decisions matter more than anything else:

1. **Tier the gate by cost.** Cheap deterministic checks run on every push. A mocked or replayed run of the full eval pipeline runs on every PR. The real-model eval runs when it can matter: on PRs that touch prompts or config, on a label, and nightly. Hamel Husain and Shreya Shankar teach this tiering as deterministic checks, then mocked integration tests, then full agent evals, with a GitHub Actions gate ([Maven, AI Evals for Engineers & PMs](https://maven.com/parlance-labs/evals), syllabus L6).
2. **Threshold on confidence bounds, not point estimates.** Fail when the *lower* bound of accuracy is below the floor. Fail when the *paired* difference against the baseline is a significant regression or drops by more than a set amount. A point-estimate gate on a noisy eval is a flaky test, and engineers learn to re-run flaky tests until they pass.

## Why it matters

Anthropic's April 2026 Claude Code postmortem describes a diffuse quality regression from three harness and product changes. The default effort was lowered from high to medium, a thinking-history bug cleared history every turn, and a system-prompt line about verbosity cost about 3% on a broader eval. The bug "passed code review, unit and e2e tests, and dogfooding". The remediation it lists is a broad per-model eval suite plus line-by-line ablations for every system-prompt change ([Anthropic, "An update on recent Claude Code quality reports"](https://www.anthropic.com/engineering/april-23-postmortem)). That is precisely the class of change a unit-test suite cannot see and an eval gate can.

For a senior engineer this is familiar territory. A prompt change is a deploy of behavior with no compiler, no type checker, and a nondeterministic runtime. [Module 02](../02-prompting-as-specification/README.md) treats prompt changes as deploys, and [Module 15](../15-observability-and-production/README.md) adds canaries and online evals. The CI gate is the pre-merge half of that pipeline.

## How it works

### The tiers

| Tier | Runs on | What it checks | Cost and time | Router implementation |
|---|---|---|---|---|
| **1. Deterministic** | Every push and PR | Parser, tool loop, grader, stats, config schema, leak check | $0, seconds | `pytest` over `code/` with `FakeClient` |
| **2. Mocked / replayed** | Every PR | The whole eval pipeline end to end: loading, routing loop, grading, stats, gate logic. Catches plumbing breaks | $0, seconds | `ci_gate.py run --client sim`, or `--client replay:<cassette>` with `ainative_kit.ReplayClient` |
| **3. Full** | PRs touching prompts/config/router code; the `run-evals` label; nightly | Real behavior on the real model, test split, with repeats | Dollars, minutes | `ci_gate.py run --client real`, then `check` against a committed real baseline |

Two notes on tier 2. A **replay** cassette (`RecordingClient` / `ReplayClient`) keys on the exact request, so *any* prompt change misses the cassette and raises `KeyError`. That is a feature: a prompt change cannot be vouched for by replay, which is exactly why prompt paths trigger tier 3. A **simulated** model (this module's `sim_model.py`) tests the plumbing, not the behavior. Never report a tier-2 number as a quality number.

The **nightly** tier-3 run catches drift with no code change: a provider-side model update, an infrastructure change, a dependency bump in a tool. If the nightly fails with no merged diff, your incident process should start from "what changed outside the repo?"

### The checks in `ci_gate.py check`

| Check | Fails when | Why this form |
|---|---|---|
| Same frozen evaluator | Fingerprint or item IDs differ from the baseline's | A comparison across different evals is meaningless. Re-baseline explicitly |
| Absolute floor | Lower 95% bound of clustered accuracy < `--floor` | "We are confident we're above the floor", not "this run happened to be" |
| No regression | Paired, clustered Δ vs baseline has CI upper < 0, **or** point Δ < −`--max-drop` | The first catches confident small regressions; the second catches large, noisy ones |
| Cost | cost per item > `--max-cost-ratio` × baseline | Quality gates without a cost gate let effort and model creep in silently |

### Choosing thresholds

- **Floor.** Set it at what the business needs, then check that the gate is *passable*. With n ≈ 480 test items and 3 repeats, the router's clustered CI half-width is about 2.6 points. A floor of 0.85 under a true accuracy of 0.895 passes reliably. A floor of 0.88 would fail a correct build often, because the lower bound sits around 0.87. If the business floor is close to current performance, the eval has to be bigger, not the gate looser.
- **max-drop.** A paired SE of about 0.8 points means that, for a good build, a point drop beyond 2 points is rare. Choose it from the noise check.
- **Baseline.** Produce the baseline with the same command on `main`. Commit it (as here, `ci/baseline_results.json`), or download it as an artifact from main's last green run. Regenerate it whenever the evaluator fingerprint changes. `test_pareto_ci.py::test_committed_baseline_matches_frozen_evaluator` fails if someone changes the dataset and forgets.
- **Seeds.** Use a new seed per CI run (the workflow uses `github.run_number`) so the gate sees real run-to-run variance, not a lucky fixed draw.

## Worked example

### Bad: the point-estimate gate

```yaml
- run: |
    ACC=$(python eval.py --n 50)            # 50 items, 1 run
    python -c "import sys; sys.exit(0 if $ACC >= 0.85 else 1)"
```

On 50 items at ~0.89, the 95% CI is about ±9 points. This gate fails a correct build about a fifth of the time and passes a 5-point regression often. Within a month people re-run it until it goes green, and it is no longer a gate.

### Good: the three PRs this gate sees

All three were produced by `ci_gate.py` against the committed baseline (simulated model, test split, 3 repeats):

**A no-op PR (refactor, same config, new seed): PASS**

| check | result | detail |
|---|---|---|
| accuracy floor (lower 95% bound) | pass | 89.5 [86.9, 92.1] vs floor 85.0 |
| same frozen evaluator as baseline | pass | 11d8d01305ec2280 vs 11d8d01305ec2280 |
| no regression vs baseline (paired, clustered) | pass | 0.0 [-1.6, 1.6] pts; fail if CI < 0 or drop > 2.0 |
| cost per item | pass | x1.00 vs limit x1.5 |

**PR #1234, "trim prompt: tie-break section seems redundant": FAIL**

| check | result | detail |
|---|---|---|
| accuracy floor (lower 95% bound) | **FAIL** | 85.1 [81.5, 88.6] vs floor 85.0 |
| no regression vs baseline (paired, clustered) | **FAIL** | -4.4 [-7.4, -1.4] pts; fail if CI < 0 or drop > 2.0 |

The *point estimate* of 85.1 would have passed the naive gate. Only the lower bound and the paired regression check catch it. (On the new model in concept 04, that same section *was* redundant. The gate is what tells you which model you are on.)

**PR #1301, "bump effort to xhigh for safety": FAIL on cost alone**

| check | result | detail |
|---|---|---|
| accuracy floor | pass | 89.5 [87.1, 91.9] vs floor 85.0 |
| no regression | pass | -0.0 [-1.5, 1.5] pts |
| cost per item | **FAIL** | x1.65 vs limit x1.5 |

That is a 65% cost increase for nothing measurable, which is exactly what the effort sweep in concept 01 found.

### The workflow

The full file is [code/ci/.github/workflows/eval-gate.yml](code/ci/.github/workflows/eval-gate.yml). Its skeleton:

```yaml
on:
  pull_request:
  push: { branches: [main] }
  schedule: [{ cron: "17 3 * * *" }]   # nightly drift check

jobs:
  deterministic:            # tier 1: every push/PR, $0
    steps:
      - run: python -m pytest -q "$CODE_DIR"
        env: { AINATIVE_FAKE: "1" }

  mocked:                   # tier 2: every PR, $0, pipeline end to end
    needs: deterministic
    steps:
      - run: |
          python ci_gate.py run --config data/climbed_config.json --split test \
            --repeats 3 --seed 1 --client sim --out mocked_results.json
          python ci_gate.py check --results mocked_results.json \
            --baseline ci/baseline_results.json --floor 0.82 --max-drop 0.02

  full:                     # tier 3: prompts/config changed, label, or nightly
    needs: [mocked, changes]
    if: >-
      github.event_name == 'schedule' || needs.changes.outputs.prompts == 'true' ||
      contains(github.event.pull_request.labels.*.name, 'run-evals')
    environment: evals      # secret lives here; fork PRs never see it
    steps:
      - run: python ci_gate.py run ... --client real --seed ${{ github.run_number }} --out full_results.json
      - run: python ci_gate.py check --results full_results.json \
               --baseline ci/baseline_real_results.json --floor 0.85 --max-drop 0.02 --max-cost-ratio 1.5
```

`check` appends its markdown table to `$GITHUB_STEP_SUMMARY`, so the result shows up on the PR's checks page. The action versions (`actions/checkout@v4`, `actions/setup-python@v5`, `dorny/paths-filter@v3`, `actions/upload-artifact@v4`) were current major versions as of writing. Pin to SHAs in a real repo.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Point-estimate thresholds | Gate re-runs that flip red to green with no diff |
| Gating on a judge you haven't calibrated | Gate failures that humans disagree with; see [Module 11](../11-llm-as-judge/README.md) |
| Baseline from a different eval version | Fingerprint mismatch. The gate should fail closed, as `ci_gate.py` does |
| Full tier on every PR | The eval bill scales with commit count; people start skipping it |
| Full tier never runs | `paths` filter misses where prompts actually live (templates in code, tool descriptions) |
| Secrets exposed to fork PRs | The full tier runs on `pull_request` from forks with the API key; use a protected environment |
| Treating the mocked tier's number as quality | Dashboards plotting sim accuracy over time |
| No nightly | A provider-side change surfaces first as user complaints |

## In your day job
- Add the three tiers to the repo that owns your LLM feature this sprint. Tier 1 and tier 2 cost nothing, and tier 2 alone catches the "eval script silently broke" class of incident.
- Put prompt and tool-description paths into the tier-3 trigger. Review that list whenever someone moves a prompt into code.
- Write the floor, max-drop, and cost limit into the eval README with the noise-check numbers that justify them.
- When the nightly fails with no diff, open an incident. That is drift, and it is what the gate is for.
