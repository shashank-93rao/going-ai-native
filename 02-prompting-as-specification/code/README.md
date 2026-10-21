# Code: prompts as versioned, linted, A/B-gated artifacts

Everything runs offline. Run commands from the course root.

```bash
# tests (deterministic, no API key needed)
.venv/bin/python -m pytest -q 02-prompting-as-specification/code

# scripts need the shared kit on the path
export PYTHONPATH=shared
.venv/bin/python 02-prompting-as-specification/code/prompt_registry.py list
.venv/bin/python 02-prompting-as-specification/code/prompt_registry.py verify      # CI check
.venv/bin/python 02-prompting-as-specification/code/prompt_lint.py 02-prompting-as-specification/code/prompts/*/v*.md
.venv/bin/python 02-prompting-as-specification/code/ab_harness.py log_triage 2 3
.venv/bin/python 02-prompting-as-specification/code/log_triage.py
```

The scripts use the real Claude API when `ANTHROPIC_API_KEY` is set and `AINATIVE_FAKE` is not. Otherwise they use `sim_model.simulated_model` through `FakeClient`. Set `AINATIVE_FAKE=1` to force the fake.

## Files

| File | What it does |
|---|---|
| `prompts/<name>/vN.md` | One immutable prompt version: `---` front matter (`name`, `version`, `model`, `owner`, `description`, `variables`) plus a body with `{{placeholders}}`. |
| `prompts/<name>/CHANGELOG.md` | One `## vN (date)` entry per version: what changed, and why. |
| `prompts/prompts.lock.json` | `{name: {version: sha256}}`. This is the record of published versions, like an applied-migrations table. |
| `prompts/channels.json` | Which version each channel serves (`stable`, optionally `canary`). A rollback is a one-line change here. |
| `prompt_registry.py` | Loads prompts, hashes them, renders with strict variable checking, resolves channels, and `verify()`s that nothing was edited in place, deleted, or published without a changelog entry. |
| `prompt_lint.py` | A heuristic linter for ambiguity smells (rules PL001 to PL007 in its docstring). It exits 1 on any error-level finding. |
| `mini_schema.py` | A ~70-line validator for the JSON Schema subset that structured outputs accept. |
| `log_triage.py` | The triage classifier: schema, strict parse, semantic checks, and one bounded retry that feeds the validator's errors back as a user turn. |
| `sim_model.py` | A scripted fake model that reacts to the spec in the system prompt. **Its numbers are not measurements**; it exists so the harness has something deterministic to compare. |
| `ab_harness.py` | A paired A/B of two prompt versions on `data/triage_eval.jsonl`, with an exact McNemar test and a gate (`promote`, `reject`, or `inconclusive`). |
| `data/triage_eval.jsonl` | 15 labelled log excerpts (Kafka, Postgres, Stripe 429s, OOMKills, schema mismatches...). One row is `must_pass`. |

## Simulated output (from `sim_model`, not a real model)

```text
$ python ab_harness.py log_triage 2 3
version                                   valid  correct
log_triage@v2#31ef56a113a4                 100%      87%
log_triage@v3#2c6132ef8f8c                 100%      93%
wins (candidate right, baseline wrong): ['kafka-lag', 'upstream-timeout']
losses (baseline right, candidate wrong): ['idempotency']
exact McNemar p = 1.0000
decision: REJECT (must_pass regression on ['idempotency'])
```

## Wiring it into CI

```yaml
# .github/workflows/prompts.yml (sketch)
- run: python prompt_registry.py verify          # no in-place edits, lock and changelog present
- run: python prompt_lint.py prompts/*/v*.md      # no error-level smells
- run: python ab_harness.py log_triage 2 3        # exit 0 only on "promote"
  env: { ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }} }
```

On real models, run the A/B several times or at a larger n before trusting it. Sampling noise on 15 rows is large. [Module 12](../../12-hill-climbing/README.md) covers noise checks and power.
