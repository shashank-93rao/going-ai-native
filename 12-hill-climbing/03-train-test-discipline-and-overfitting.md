# 03: Train/test discipline and overfitting

## The idea

A hill-climb is an optimizer, and every optimizer overfits whatever it can see. You (or your agent) read dev failures, propose fixes for them, and score the fixes on dev. After twenty rounds, dev is no longer a sample of production. It is the set of cases your config has been tuned against. A held-out split is the only thing that tells you whether a gain generalizes, and it stays held out only as long as you protect it.

Four rules carry most of the weight:
1. **Split by cluster, stratified by failure family.** Never split by row.
2. **Read dev, score test.** Transcripts you read are dev. Test contributes numbers to keep/revert decisions, and you never read its failures.
3. **Revert when dev rises and test doesn't.** That pattern is the signature of overfitting, so treat it as overfitting and do not explain it away.
4. **Keep the answers structurally out of reach.** No eval item text in the prompt, no access to the grader, no write access to the dataset.

## Why it matters

Anthropic's inbox router is the canonical small case. Adding two worked examples raised train while test stayed flat, so the variant was reverted ([Lance Martin, "Automating eval design and hillclimbing with Claude"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). The same post names the mechanism: overfitting "happens when the harness absorbs eval-specific fixes", such as adding an OCR tool the benchmark needs but production rarely does. It gives three defenses: split the cases, "never paste failures into the prompt", and keep the answers "structurally out of the model's reach".

The failure gets worse when the optimizer is capable. Anthropic has documented models using git history from earlier trials to cheat an eval ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). They have documented a model that inferred it was being evaluated on BrowseComp, found the benchmark's decryption code, and decrypted the answer key, in 2 of 1,266 problems ([Anthropic, "Eval awareness in Claude Opus 4.6's BrowseComp performance"](https://www.anthropic.com/engineering/eval-awareness-browsecomp)). And in RL training, a model that learned to reward hack (for example with `sys.exit(0)` to fake passing tests) generalized to broader misaligned behavior ([Anthropic, "From shortcuts to sabotage"](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)). Your improve-loop is not RL training, but the lesson carries: **a loop that is rewarded for a number will find the cheapest path to the number.**

## How it works

### Splits

| Split | Who sees what | Used for |
|---|---|---|
| **dev** (train) | Full transcripts, failures, error analysis | Proposing hypotheses; the first gate in keep/revert |
| **test** (held out) | Scores only, never transcripts | The second gate in keep/revert; the headline number |
| **lockbox** (optional, recommended for long climbs) | Nothing until the end | One final read to confirm the test number didn't wear out |

Split **by cluster**. In the router, all alerts from one incident go to the same side (`test_router.py::test_dataset_split_by_cluster` enforces this). If you split by row, five near-identical alerts from incident 017 land on both sides. A prompt fix written for 017's dev alerts then "generalizes" to its test alerts, and test stops measuring anything new. This is the eval equivalent of leaking a user's sessions across train and validation.

**Stratify** by failure family, so each side has its share of ambiguous, tiebreak, lookup, and reasoning cases. `make_incidents.py` alternates clusters between dev and test within each tag.

### Where the sources disagree, and the course stance

Anthropic's hillclimb workflow scores test every round and uses it in the keep/revert rule ("keep if train and test both improve"). Hamel Husain and Shreya Shankar's course teaches "freeze-and-read-test-once": the test slice is scored once, at the end ([Maven, AI Evals for Engineers & PMs](https://maven.com/parlance-labs/evals), syllabus L5). Both are right about different risks. Scoring test every round gives you an early overfitting alarm, but every peek is a small amount of selection, so after 20 or 30 rounds test has been partly fitted too.

> **Course stance (synthesis):** use test as a *decision* set, scored every round with numbers only, as Anthropic does. Also keep a small **lockbox** that is read once, as Hamel and Shreya teach. If the lockbox disagrees with test by more than the CIs allow, your test set has worn out: refresh it from new production data before the next climb.

### Revert rules

`hillclimb.decide()` implements these, in order:

| Condition (Δ = paired, clustered, vs current best) | Decision | Log reason |
|---|---|---|
| Δdev CI entirely below 0 | revert | dev regression |
| Δdev CI spans 0 | revert | within noise; simpler config wins ties |
| Δtest CI entirely below 0 | revert | dev up, test significantly down: overfit |
| Δtest ≤ 0, or Δtest < 0.5 × Δdev | revert | dev up, test flat: overfit |
| cost ratio > budget (if set) | revert | over cost budget |
| otherwise | **keep** | dev up (significant), test up (significant or directional) |

The 0.5 ratio is a judgment call: it says a real fix should carry at least half its dev gain to test. Set `require_test_significant: true` for high-stakes systems, and accept that you will revert more real fixes (concept 02 shows how often at a given eval size).

### Goodhart's law in your own loop

Goodhart's 1975 observation about monetary targets is usually quoted in Marilyn Strathern's paraphrase: when a measure becomes a target, it ceases to be a good measure. In a hill-climb this shows up concretely, in three ways:

| Failure | Example | Guard |
|---|---|---|
| **Memorization** | Eval items or near-copies pasted into the prompt as "examples" | Leak check: refuse configs that contain eval item text (`hillclimb.leaked_items`) |
| **Grader gaming** | The prompt learns the grader's quirks. A regex grader accepts `team: database` anywhere, so the prompt makes the model list all six teams | Grade the parsed answer, not raw text; run an adversarial "does this output deserve the score?" spot check |
| **Evaluator tampering** | An agent "fixes" a failing grader, edits the dataset, or reads labels from disk | Fingerprint grader + data and verify every round; read-only mount; grade in a separate process |
| **Proxy drift** | Accuracy climbs while the thing you care about (pager load, time to mitigate) doesn't | A cost-weighted metric or a second guardrail metric; production online evals ([Module 15](../15-observability-and-production/README.md)) |

### The adversarial-sampling trap

The opposite mistake is in *building* the eval. If you fill it only with cases today's model fails, Lance Martin notes, you measure "that model's failure fingerprint" rather than the task. You get a set that looks hard for this model, easy for the next, and skewed toward whatever this model happens to be bad at. Anthropic's guidance is to pick hard cases a human can justify, add specific production failures, and not rely only on user traffic, because "users sometimes try what they expect to work" and that skews easy (same post).

The same trap appears inside a climb when every new eval item comes from the current best's failures. Each round the eval drifts toward the residue of your own fixes. Add new items from production traffic and human-judged hard cases, on a schedule, not from your last round's failures.

## Worked example

### Bad: round 3 of the climb

The hypothesis sounds reasonable: "the model doesn't know the edge cases, so show it 60 of them with the right answers." `apply_change` takes the current best's 60 majority-failed dev alerts and appends:

```text
## Examples
[alert 000.1] payments-api pods OOMKilled on node pool gp-b; node memory pressure
team: platform

[alert 004.1] users-db WAL volume at 94% and rising; CDC replication slot inactive 4h; warehouse tables stale
team: data-pipeline
...
```

The simulated result, from the canonical log:

```text
| 3 | v3-fewshot-failures | dev 86.4 | Δdev +8.8 [4.5, 13.1] | test 72.5 | Δtest -2.0 [-3.4, -0.6] | $6.25/1k | revert |
reason: dev up but test significantly DOWN: overfit to dev; WARNING 60 eval items pasted into prompt
```

This is the largest dev gain of the entire climb, and it is entirely memorization. The 60 pasted items are now answered from the prompt. Every other alert got slightly *worse*, because the examples anchor the model on their surface features, so test fell 2 points. Cost per alert doubled from the longer prompt (from $3.03 to $6.25 per thousand). In the 10-seed study at this eval size, v3 was reverted in 10 of 10 runs. It never once survived the test gate.

The simulation hard-codes "pasted text is memorized, everything else gets a small anchoring penalty." Real models degrade in messier ways, but the published inbox-router result shows the same shape: train rose, test stayed flat.

### Good: the guard on by default

With `"rules": {"block_leaks": true}` (the default), the runner refuses the config before spending a token:

```text
| 3 | v3-fewshot-failures | `{"paste_dev_failures": 60}` | - | - | - | - | - | **blocked** | config contains 60 eval items verbatim |
```

The legitimate version of the same idea is *synthetic* examples, written from the failure pattern and not copied from the eval. For instance: "a pool exhausted *against* a database is database, even when the symptom is in payments-api." That is exactly what the kept v2 queue-definitions section does, as a rule rather than an example. If you want few-shot examples, write them about incidents that are not in any split, and check them with `leaked_items` anyway, because a "new" example that paraphrases an eval item is still a leak. Verbatim checks will not catch a paraphrase, so for paraphrase leaks add an n-gram or embedding-similarity check against the eval set.

### Good: a reviewer's overfitting checklist for a climb PR

```text
[ ] split is by cluster; script that produced it is in the repo
[ ] no transcript from test or lockbox was opened (check the notebook / agent trace)
[ ] leak check passes against dev+test+lockbox
[ ] evaluator fingerprint identical at round 0 and final round
[ ] every kept row: Δtest > 0 and >= half of Δdev
[ ] lockbox read once at the end; within CI of test
[ ] new eval items added this cycle came from production or human-judged hard cases,
    not from the current best's failures
```

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Row-level split on clustered data | Any cluster ID appears in both splits (one-line check) |
| Reading test transcripts "just once, to see why" | Test failures show up in a hypothesis column; you now need a new test set |
| Explaining away dev-up/test-flat ("test is harder") | The rule says revert. Write the explanation as a new hypothesis and test it on dev |
| Paraphrased leaks | High n-gram overlap between prompt and eval items; verbatim checks miss them |
| The agent-optimizer edits the grader | Fingerprint mismatch; agent trace shows writes under `eval/` |
| Test wears out over a long climb | Lockbox disagrees with test beyond CI; Δtest systematically tracks Δdev too closely late in the climb |
| Eval drifts toward your residue | Share of eval items sourced from "current failures" rises each cycle |

## In your day job
- Make the split a committed artifact produced by a script (`make_incidents.py` here), keyed by cluster, with a test that fails on cross-split clusters.
- Mount the eval directory read-only for any agent that climbs, and have the runner verify a fingerprint. Then a tampering attempt is a crash, not a judgment call.
- Add a leak check to the PR template for prompt changes. It is twenty lines of code, and it catches the most common overfit in prompt work.
- Budget a test-set refresh every few climbs, from fresh production samples. Treat the old test set as dev.
