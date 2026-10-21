# Exercises

Run everything from `12-hill-climbing/code/` with `PYTHONPATH=../../shared` (or from the course root via pytest). Exercises 1–6 are offline (`AINATIVE_FAKE=1`); 7–8 use a real API key or a real coding agent.

---

## 1. Verify the statistics by hand (30 min, offline)

**Goal.** Trust `stats.py` because you have checked it, not because it has tests.

**Steps.**
1. By hand or in a scratch REPL, compute the clustered SE of `[1, 1, 0, 0]` with clusters `[a, a, b, b]`, with and without the G/(G−1) correction.
2. Compute McNemar's exact p for b01 = 7, b10 = 1.
3. Reproduce Eugene Yan's ±2.4% (n = 200, p = 0.03) and ±1.7% (n = 400) with `ci_halfwidth`.
4. Use `required_n_two_proportions` and `required_n_paired` (with `sd_diff_from_correlation`, ρ = 0.3, 0.5, 0.7) to size an eval that detects 80% → 85%.

**Done when.** Your hand values for steps 1–2 match `clustered_se` and `mcnemar` to 4 decimals. You have a table of required n for three values of ρ, and can state in one sentence why pairing changes it.

**Stretch.** Add a hypothesis property test: `paired_bootstrap` CI width shrinks roughly as 1/√n when you duplicate the dataset k times with distinct cluster IDs.

---

## 2. Run the canonical climb and read the log like a reviewer (30 min, offline)

**Goal.** Get fluent in the experiment log.

**Steps.**
1. `python hillclimb.py data/variants.json --out runs/mine`
2. Diff `runs/mine/experiments.md` against `runs/demo/experiments.md`. They should be identical apart from paths.
3. For each row, write one line: what the decision rule saw, and whether you agree.
4. Change `"seed": 1` to 5 and to 8 and re-run. Note which rows change decision.

**Done when.** You can explain why v3 is reverted despite the largest dev gain, why v6c is reverted despite passing the rules, and which seed(s) revert v4 and why. (Hint: concept 02, "the noise check is a lower bound".)

---

## 3. Feel the power problem (45 min, offline)

**Goal.** Reproduce the eval-size table in concept 02 yourself.

**Steps.**
1. `python make_incidents.py --clusters 160 --out data/small.jsonl`
2. Copy `data/variants.json` to `data/variants_small.json` and add `"dataset": "data/small.jsonl"`.
3. Write a 15-line script that runs `Climb` for seeds 1–10 on both datasets and counts how often each round is kept.
4. Repeat at `--clusters 640`.

**Done when.** You have a 3-row table (160 / 320 / 640 incidents) of keep counts for v2, v4, v5, and v6b, and final test accuracy ranges. It qualitatively matches concept 02's table. You can state the smallest eval size at which all real fixes survive at least 9 times out of 10.

**Stretch.** Instead of more incidents, try `repeats: 12` at 160 incidents. Explain why it helps much less.

---

## 4. Break the guards, then fix them (45 min, offline)

**Goal.** See the overfitting and tampering defenses work, and find their gaps.

**Steps.**
1. Set `"block_leaks": true` and run. Confirm v3 is `blocked`.
2. Add a round with `"change": {"set": {"extra_prompt": "<a paraphrase of 5 dev alerts with their teams>"}}`. Does `leaked_items` catch it?
3. Implement `ngram_overlap(cfg, items, n=5) -> list[str]` in a new file `leak_check.py` and wire it into `try_variant` behind a rule flag.
4. While a climb is running (insert a `time.sleep` in a round, or use a debugger), append a row to `data/incidents.jsonl`. Confirm the fingerprint guard aborts.

**Done when.** Your paraphrase from step 2 is caught by the n-gram check and missed by the verbatim check. A test in `test_hillclimb.py` covers both. Step 4 raises `RuntimeError: evaluator or dataset changed`.

---

## 5. Price the frontier (40 min, offline)

**Goal.** Turn a Pareto table into a decision.

**Steps.**
1. `python pareto.py`, and save the table.
2. Add a `--error-cost` argument to `pareto.py` that adds `(1 - acc) * 1000 * error_cost` to each point and prints the total-cost ranking.
3. Run it with error costs of $0.01 (log-line tagging), $1, and $50 (paging the wrong team).

**Done when.** You have three rankings, and you can name the error cost at which the recommended config changes from a Haiku tier to a Sonnet or Opus tier. Every recommended step is backed by a paired gain whose CI excludes 0.

---

## 6. Wire up the CI gate (45 min, offline)

**Goal.** A working three-tier gate in a scratch repo.

**Steps.**
1. Copy `code/` into a scratch repo with `shared/ainative_kit`, and copy `ci/.github/workflows/eval-gate.yml` to `.github/workflows/`.
2. Adjust `CODE_DIR` and paths. Push, and open a PR that removes `tiebreak` from `data/climbed_config.json`.
3. Confirm tier 1 passes and tier 2 fails, with a readable step summary.
4. Open a second PR that only edits a comment. Confirm tiers 1–2 pass and tier 3 is skipped.

**Done when.** Both PRs show the expected check results, and the failing PR's summary table names the regression check with its CI. (No GitHub? Run the two `ci_gate.py` commands locally and check exit codes: 1 for the first PR, 0 for the second.)

**Stretch.** Add a tier-2 replay path. Record a cassette with `RecordingClient` against the real API once, then replay it in CI. Show that a prompt edit raises `KeyError` (a cassette miss), and explain why that should route the PR to tier 3.

---

## 7. Climb against the real API (2–3 hours, real API, about $5–15 depending on model and repeats)

**Goal.** See what changes when the model is real.

**Steps.**
1. Implement the effort-forwarding client from `code/README.md`, and use it in a `real_factory` passed to `Climb`.
2. Reduce cost: dev and test each limited to 120 alerts across at least 60 incidents, `repeats: 2`, model `claude-haiku-5-5`.
3. Run the noise check, then the canonical rounds.
4. Compare your log with the simulated one: which decisions agree? Where does the real model differ (for example, does "think step by step" really do nothing, and does pasting failures really lose on test)?

**Done when.** You have a real `experiments.md` with CIs, a written comparison against the simulated log (at least 5 bullets), and you have marked every claim in the simulated log that did *not* hold on the real model.

---

## 8. Hand the climb to an agent (2 hours, real coding agent)

**Goal.** Run a bounded, guarded, automated climb and review it.

**Steps.**
1. Write a `program.md` modelled on concept 05's: an editable-surface allow-list, a budget, stop rules, and the never-list.
2. Make `router_eval.py`, `make_incidents.py`, `data/incidents.jsonl`, `stats.py`, and `hillclimb.py` read-only (`chmod a-w`), and add a lockbox split you hold back from the agent entirely.
3. Run a coding agent (Claude Code headless, or similar) for at most 8 rounds.
4. Review: the config diff line by line, every reverted row, 20 random test transcripts once, then the lockbox.

**Done when.** You have the agent's `experiments.md` and a one-page review that states the lockbox number with CI. It lists every prompt line in the final config with the log row that justifies it, and it notes any attempt to touch read-only files (check the agent trace).
