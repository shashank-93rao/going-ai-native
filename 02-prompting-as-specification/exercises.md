# Exercises

The offline exercises need no API key. Run commands from the course root with `export PYTHONPATH=shared`.

---

## 1. Lint, then fix, a prompt from your own job (offline, 30 min)

**Goal.** Feel how often production prompts carry mechanical ambiguity.

**Steps.**
1. Copy a real prompt your team uses (a review bot, a summariser, a classifier, a CLAUDE.md section) into `code/prompts/mine/v1.md`, with front matter.
2. Run `python 02-prompting-as-specification/code/prompt_lint.py 02-prompting-as-specification/code/prompts/mine/v1.md`.
3. Run the smart-new-hire questions from [02-removing-ambiguity.md](02-removing-ambiguity.md) by hand, and write down each question you can't answer from the prompt.
4. Write `v2.md` that answers them, plus a `CHANGELOG.md` entry, then run `prompt_registry.py lock` and `verify`.

**Done when.**
- `prompt_lint.py` reports zero errors and zero warnings on `v2.md`.
- `prompt_registry.py verify` prints `OK`.
- Your changelog entry lists every new-hire question and the line that answers it.

**Stretch.** Paste v1 into the new-hire meta-prompt in a fresh model session, and compare its questions with yours.

---

## 2. Add a lint rule (offline, 45 min)

**Goal.** Extend the linter the way you'd extend any linter: a rule, a fix message and tests.

**Steps.** Implement one of the following as rule PL008 in `prompt_lint.py`:
- **negative-only instruction**: a sentence with `don't`, `do not` or `avoid` and no positive alternative (`instead`, `use`, `write`) in the same or next sentence, or
- **enum drift**: given a schema dict, flag any enum value that never appears in the prompt text, and any backticked value in the prompt that looks like an enum member but isn't in the schema.

**Done when.**
- At least three positive and two negative test cases are in `test_prompt_lint.py`.
- `test_spec_prompts_are_clean` still passes, or you've justified a change to a v2 prompt in its changelog.
- The rule's message tells the author what to write instead.

---

## 3. Ship log_triage v4 through the gate (offline, 45 min)

**Goal.** Take a prompt change through the full deploy path, and learn what a 15-row gate can and can't tell you.

**Steps.**
1. Create `code/prompts/log_triage/v4.md` from `v3.md`, narrowing the signature `` `timeout` `` to `` `upstream timeout` ``. Add a `## v4` changelog entry that cites v3's rejection.
2. Run `prompt_registry.py lock` and `verify`, and lint the new file.
3. Run `python 02-prompting-as-specification/code/ab_harness.py log_triage 2 4`.
4. Read the decision. Explain in the changelog why it says what it says.
5. Point `channels.json` at `"canary": 4`, and run `verify` again.

**Done when.**
- The harness reports no `must_pass` regression and no losses.
- You can state the exact number of additional all-win discordant rows needed for `promote` at alpha 0.05, and you've checked it with `mcnemar_exact`.
- `verify` prints `OK` with the canary pointer in place.
- Revert your v4 and lock changes (or work on a copy of `prompts/`), so `test_repo_registry_is_clean` passes again.

**Stretch.** Add rows to the eval set until v4 promotes. Then write one paragraph on why those rows should come from a held-out incident archive and not be written by the person who wrote v4 ([Module 12](../12-hill-climbing/README.md)).

---

## 4. An instruction-conflict audit script (offline, 60 min)

**Goal.** Find conflicts across instruction layers mechanically.

**Steps.**
1. Write `code/conflict_audit.py`. It collects every sentence from `CLAUDE.md`, `AGENTS.md`, `.claude/rules/**/*.md` and `.claude/skills/*/SKILL.md` under a given root, and tags each with file and line.
2. Reuse `prompt_lint`'s polarity and content-word logic to flag pairs across *different files* that share two or more content words and have opposite polarity, or that mention the same backticked command with different verbs.
3. Build a fixture directory reproducing the three-way test conflict from [04-instruction-hierarchy.md](04-instruction-hierarchy.md), and a test that asserts the audit finds it.
4. Run it on a real repo you work in.

**Done when.**
- The fixture test passes offline.
- On your real repo, you've triaged every finding as conflict, false positive or redundant duplicate, and fixed at least one.

**Stretch.** Compare its findings with `/doctor prompt-audit` in Claude Code on the same repo.

---

## 5. Re-run the A/B on a real model (real API, 30 min)

**Goal.** See how the simulated results compare with a real model, and how noisy 15 rows are.

**Steps.**
1. Set `ANTHROPIC_API_KEY` and unset `AINATIVE_FAKE`.
2. Run `ab_harness.py log_triage 1 2` three times, and `ab_harness.py log_triage 2 3` three times. Save each report.
3. For each pair, record wins, losses and the decision on each run.

**Done when.**
- You have a six-row table of (pair, run, wins, losses, decision).
- You can say whether the decision was stable across runs, and which rows flipped between runs.
- You've written one sentence on where the simulated model's behaviour differed from the real model's.

**Stretch.** Wrap the client in `RecordingClient`, then re-run the harness offline from the cassette with `ReplayClient`.

---

## 6. The model-upgrade drill on a prompt you own (real API, 90 min)

**Goal.** Retire folklore from a real prompt with evidence.

**Steps.**
1. Choose a prompt older than six months. Build or reuse an eval of 20 or more rows with a binary check (code check or calibrated judge).
2. Run the drill from [03-outcome-first-and-expired-techniques.md](03-outcome-first-and-expired-techniques.md): old prompt on the old model, old prompt on the new model, one ablation per legacy line, a fresh-baseline rewrite, and an effort sweep (`low`, `medium`, `high`).
3. Gate the best candidate against the reference with paired outcomes.

**Done when.**
- You have an ablation table with pass count and mean output tokens per variant.
- The new version is in the registry with its `model` field set, and the changelog names every removed line along with its measured effect.
- The gate decision is recorded, including `inconclusive` if that's what it said.

---

## 7. Structured outputs on the real API (real API, 45 min)

**Goal.** Measure what constrained decoding adds over prompt-asked JSON.

**Steps.**
1. Write `code/triage_structured.py`, which calls `anthropic.Anthropic().messages.create(..., output_config={"format": {"type": "json_schema", "schema": TRIAGE_SCHEMA}})` directly (the course kit doesn't expose `output_config`), then runs `semantic_errors` on the result. Guard the `anthropic` import, and skip it in tests when no key is set.
2. Run both paths on `triage_eval.jsonl` with prompt v2.
3. Then delete the `<output_format>` section from a copy of the prompt, and run the structured path again.

**Done when.**
- You have a table of schema-valid rate, semantic-error rate and accuracy for each path.
- You can say whether removing the prose format description changed accuracy (OpenAI's guidance predicts not; check it for Claude).

---

## 8. A new-hire review of your AGENTS.md (real coding agent, 20 min)

**Goal.** Find the questions your repo's instruction file leaves open.

**Steps.**
1. In a fresh coding-agent session (no prior context), paste your repo's AGENTS.md or CLAUDE.md into the new-hire meta-prompt from [02-removing-ambiguity.md](02-removing-ambiguity.md).
2. Classify each question it returns: real gap, false alarm, or conflict.
3. Fix the real gaps and conflicts, and give every "never" either an enforcement mechanism or a scope.

**Done when.**
- Every question is classified.
- The file diff is in a PR whose description lists each question and its resolution.
- Every remaining "never" or "always" names its hook or carries a reason.
