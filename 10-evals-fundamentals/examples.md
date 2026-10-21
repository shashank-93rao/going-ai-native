# Examples

Five scenarios from a distributed-systems team's week. Each one follows: situation, the naive approach and what happens, the AI-native approach with artifacts, and what to check. Model outputs that were not run are labelled `(illustrative output)`.

---

## 1. Moving the alert router to a cheaper model

**Situation.** The incident router runs on `claude-sonnet-5-5`. Finance asks whether `claude-haiku-5-5` would do. The router handles about 4,000 alerts a day.

**Naive approach.** Someone swaps the model ID in staging, watches 30 alerts go by in Slack, sees nothing odd, and ships. Two weeks later the streaming on-call has been paged at night for three payments alerts, and nobody can say whether the model change caused it, because the traces don't record which model answered.

**AI-native approach.**
1. Confirm the trace data model records `model` and `prompt_hash` on every `llm_call` span ([02-instrument-first.md](02-instrument-first.md)). Without that, there is nothing to compare.
2. Run the suite on both models, same prompt hash, 5 trials each, on the **test** split only:
   ```bash
   python eval_harness.py --model claude-sonnet-5-5 --split test --trials 5 --k 1 3 --out sonnet.jsonl
   python eval_harness.py --model claude-haiku-5-5  --split test --trials 5 --k 1 3 --out haiku.jsonl
   ```
3. Compare the three-way split and the abstention-aware score, not accuracy alone, per slice:

   | slice | sonnet correct / wrong | haiku correct / wrong |
   |---|---|---|
   | OVERALL | 0.91 / 0.05 | 0.88 / 0.06 |
   | misleading_keyword | 0.80 / 0.20 | 0.55 / 0.40 |
   | secret_in_body | 1.00 / 0.00 | 1.00 / 0.00 |

   (illustrative output)
4. The aggregate drops 3 points, which might be noise on 14 cases. The `misleading_keyword` slice doubles its wrong rate, which is a real pattern. Read the haiku traces for that slice: the open codes say it routes on topic names.
5. Decide per slice: either add explicit ownership rules for topic names and re-run, or route alerts that match more than one team's keywords to the stronger model. [Module 12](../12-hill-climbing/README.md) covers the cost frontier and the model-upgrade drill.

**What to check.** Both runs show exactly one prompt hash. The test split was not used to tune the ownership rules. The slice with the regression has enough cases to trust the direction; if it has 4, add cases from production before deciding.

---

## 2. An eval for the PR-review bot that is supposed to catch missing idempotency keys

**Situation.** Your team runs an LLM reviewer on PRs to a payments service. Its job is to flag handlers that write to the ledger without an idempotency key. It has caught some real bugs and has also left long, wrong comments on clean PRs. Developers have started ignoring it.

**Naive approach.** The team writes a stricter prompt ("Only flag *real* idempotency issues") and judges it by feel on the next week of PRs. The bot gets quieter, and nobody knows whether it still catches the bug.

**AI-native approach.**
1. **Dataset from real failures.** Pull the PRs behind the last 18 months of duplicate-charge incidents (Anthropic describes running an eval built from past incident-causing PRs daily against its own reviewer). That gives about 12 positive cases. Add 30 clean PRs that touch the same handlers as **negative controls**: the bot must stay silent on them.
2. **Rows.**
   ```json
   {"id": "pr-4471", "input": {"diff_path": "fixtures/pr-4471.diff"},
    "expected": {"flag": true, "file": "ledger/handlers/refund.go", "reason_code": "missing_idempotency_key"},
    "slice": "positive", "origin": "INC-1932", "split": "test"}
   {"id": "pr-5102", "input": {"diff_path": "fixtures/pr-5102.diff"},
    "expected": {"flag": false}, "slice": "negative_control", "origin": "merged-clean", "split": "dev"}
   ```
3. **Graders.** The bot emits structured findings `{file, line, reason_code}`. Code graders check `flag`, `file` and `reason_code` with exact match. Whether the comment's explanation is correct is a judge's job ([Module 11](../11-llm-as-judge/README.md)); start without it.
4. **Metrics.** Recall on positives, false-flag rate on negative controls, and pass^3 on each, because developers see the bot's consistency across pushes to the same PR.
5. **Error analysis** on the false flags. The open codes cluster into "flags handlers that call `ledger.WriteIdempotent()` because it doesn't see the helper's definition". That is a context problem, not a prompt-wording problem ([Module 03](../03-context-engineering/README.md)).

**What to check.** The negative-control false-flag rate is reported next to recall, every time. Positives and negatives are split by incident, not by row. The fixtures are frozen diffs, not live branches that can change under you.

---

## 3. Cold start: a runbook assistant with no traffic yet

**Situation.** You are building an assistant that answers on-call questions ("how do I drain a Kafka broker?") from your runbooks. It launches in a month. There are no traces.

**Naive approach.** Ask a model for "50 realistic on-call questions with answers", then measure the assistant against those answers. The questions are tidy and repetitive, and the answers came from a model, so agreement with them proves little.

**AI-native approach.**
1. **Constraint evals first** ([01-why-evals-and-when-to-write-them.md](01-why-evals-and-when-to-write-them.md)): every answer cites a runbook path that exists; no answer contains a credential; questions about systems with no runbook get "I don't have a runbook for that".
2. **Dimensions** for the questions, as in `synth_data.py`:
   ```python
   DIMENSIONS = {
       "system": ["kafka", "postgres", "envoy", "vault", "k8s-node"],
       "intent": ["diagnose", "mitigate", "rollback", "escalate"],
       "urgency": ["mid-incident", "post-incident", "learning"],
       "phrasing": ["terse-slack", "full-sentence", "pasted-error-log"],
       "coverage": ["runbook-exists", "runbook-missing", "runbook-outdated"],
   }
   ```
3. Write 20 tuples by hand, filter the cross product, stratify so every `coverage` value appears, and generate **questions only**, one prompt per tuple.
4. The on-call lead writes the expected answer: which runbook section, or "no runbook". This is the benevolent dictator's work, and the `needs_review` flag tracks it.
5. Dogfood with the on-call rotation for two weeks with tracing on, then run error analysis on the real traces. Expect the taxonomy to replace much of what you guessed.

**What to check.** Every `runbook-missing` tuple generated a question that really has no runbook (verify that the scenario triggers). The synthetic phrasing is not all identical; skim 20. Real traces join the dataset as soon as they exist, and synthetic rows are gradually retired.

---

## 4. A coding agent that "fixes" flaky integration tests

**Situation.** A background agent picks up flaky-test tickets for a Java service, finds the race, and opens a PR. The team says it "works most of the time".

**Naive approach.** Grade the agent by whether CI goes green on its PR. Green CI is the agent's own target, and agents have learned to make tests pass by adding `@Retry(3)`, widening timeouts, or deleting assertions.

**AI-native approach.**
1. **Tasks from history.** Take 25 past flaky-test fixes from git. Revert each fix to create the task, and keep the real fix as the reference solution.
2. **Outcome grader.** Run the test 200 times under stress (`-Dtest.iterations=200`, CPU contention) and require 200/200. That is the hidden test. The visible test is the single flaky test.
3. **State graders.** Fail the trial if the diff touches the test file's assertions, adds a retry annotation, or raises a timeout by more than 2x. This is a diff check, which is a code grader.
4. **Transcript grader** (diagnostic): the PR description's claim ("root cause: unsynchronized access to `pendingAcks`") matches the files changed.
5. **Metrics.** Run each task 5 times. Report pass@1 and pass^5 per task. Tasks with pass@5 = 1 and pass^5 = 0 are where the agent *can* fix the race but doesn't reliably, which is where better task statements or a stronger verifier help most.
6. **Isolation.** Each trial gets a fresh clone at the task commit, with no access to the branch that contains the real fix.

**What to check.** The task set includes a few tickets where the flakiness was infrastructure, not code. The correct outcome there is "no code change, here's why", which is the agent's abstain path. The diff check really fails on a `@Retry` PR; prove it with one ([05-graders.md](05-graders.md)).

---

## 5. A vendor says its new model is 5 points better on a coding benchmark

**Situation.** A model release post shows a 5-point gain on a public agentic coding benchmark. Your team wants to switch the coding agent from Example 4.

**Naive approach.** Switch. Five points sounds large.

**AI-native approach** ([07-eval-integrity-and-benchmarks.md](07-eval-integrity-and-benchmarks.md)):
1. Read the claim with the checklist. Which scaffold? Which reasoning effort? Pass@1 or best-of-k? How many trials, and what interval? How old is the benchmark, and has its maintainer retired or revised it? Anthropic measured 6-point swings from infrastructure configuration alone on Terminal-Bench 2.0.
2. Run both models on **your** flaky-test suite, same harness, same resource limits, same day, 5 trials per task.
3. Compare per task with a paired analysis ([Module 12](../12-hill-climbing/README.md)), not the two aggregate means.

   | | current | new |
   |---|---|---|
   | pass@1 | 0.64 | 0.66 |
   | pass^5 | 0.31 | 0.42 |
   | false "fixed" claims | 9% | 4% |

   (illustrative output)
4. In this illustration the pass@1 gain is within noise, but pass^5 and honesty both improved. For a background agent whose PRs humans review, that is the case for switching, and it has nothing to do with the public benchmark's 5 points.

**What to check.** Both runs used the same prompt hash and harness version. The comparison is paired by task. Someone read the transcripts of the new model's highest-token trials for signs of gaming.
