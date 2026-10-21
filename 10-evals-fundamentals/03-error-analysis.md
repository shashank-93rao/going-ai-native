# 03: Error analysis

## The idea
Error analysis is how you find out what to measure. You read a sample of traces, write a short free-text note on the first thing that went wrong in each (**open coding**), group those notes into a small set of named, binary failure modes (**axial coding**), and count how often each one occurs. The counts tell you what to fix first. Each failure mode becomes a grader.

The terms come from qualitative research (grounded theory). Hamel Husain and Shreya Shankar adapted them for LLM systems, and their FAQ and course are the primary sources here ([Husain and Shankar, "AI Evals FAQ"](https://hamel.dev/blog/posts/evals-faq/); [course syllabus](https://maven.com/parlance-labs/evals)). The systems analogy is a postmortem review across a quarter of incidents. You do not start with a category list. You read the incidents, write down what happened, and let the categories ("config push without canary", "retry storm") come out of the reading. Then you count them, and the counts decide the roadmap.

## Why it matters
Top-down metrics miss domain-specific failures. Generic scores such as ROUGE, BERTScore or embedding similarity on outputs create false confidence ([Husain and Shankar, FAQ](https://hamel.dev/blog/posts/evals-faq/)). Hamel's field guide argues that bottom-up error analysis is what finds the failures that matter, and reports a case where date handling went from 33% to 95% success after the team found and fixed that specific failure mode ([Hamel Husain, "A Field Guide to Rapidly Improving AI Products"](https://hamel.dev/blog/posts/field-guide/)). The FAQ authors say they spend 60 to 80% of development time on error analysis and evaluation, most of it reading data.

The router in this module shows the effect directly. The pass rate says 45%. It does not say that a quarter of the failures come from one cause (routing on an incidental keyword), and that this cause is a different fix from the other quarter (severity under-calls when impact is implied). You find that out by reading.

## How it works

### 1. Sample about 100 traces, passes included
- Start with about 100 diverse traces. Annotate at least the first 30 yourself before you let a model suggest anything ([Husain and Shankar, FAQ](https://hamel.dev/blog/posts/evals-faq/)).
- Stratify by slice, so rare slices are not drowned out by the common ones. `error_analysis.py sample --stratify slice` does a round-robin across slices.
- **Include passing traces.** Graders miss failures, and finding those misses is part of the job. The sampler ignores grader verdicts on purpose, and the viewer hides them.

### 2. Open-code the first failure
Read the whole trace, then write one line about the **first** thing that went wrong. Upstream errors cascade. If the agent misread the task, every later step looks wrong, and noting all of them inflates the downstream modes. This is root cause vs symptoms, as in a postmortem.

Good open codes are specific and observable. They say what happened, not why.

| Weak open code | Better open code |
|---|---|
| "wrong team" | "routed to payments on the topic name payments-events" |
| "bad severity" | "customers see stale order status, still SEV3" |
| "hallucinated" | "vague CPU anomaly on 14 hosts confidently routed to network" |
| "formatting issue" | "output wrapped in \`\`\`json fences, parser rejects it" |

### 3. Axial-code into 5 to 8 binary failure modes
Group the open codes. Each group becomes a failure mode with a name and a one-line definition, specific enough that two engineers would agree on whether a given trace has it. The FAQ calls this grouping "the most important step". The course homework targets a taxonomy of 5 to 8 binary failure modes over at least 60 traces ([syllabus](https://maven.com/parlance-labs/evals)).

A model can **suggest** a grouping once you have open codes: `error_analysis.py propose` sends the open codes to a model and asks for at most 8 binary modes. Treat the result as a draft. You decide the taxonomy. The course syllabus also says to compare against published taxonomies only *after* building your own, so that a generic list does not replace what your data says.

### 4. Count, then prioritize
Count failures per mode. Then weigh by cost: a SEV1 page for an autoscaler event costs a night's sleep, while a SEV3 that should have been SEV2 might cost twenty minutes. OpenAI's receipt-inspection cookbook makes the same point with a cost model that turns each kind of eval error into dollars ([OpenAI Cookbook, "Eval Driven System Design"](https://developers.openai.com/cookbook/examples/partners/eval_driven_system_design/receipt_inspection)).

### 5. Stop at saturation
Keep reading until new traces stop producing new failure modes or changing existing ones ([Husain and Shankar, FAQ](https://hamel.dev/blog/posts/evals-faq/)). `error_analysis.saturation_curve` plots distinct codes against traces labeled. A curve still rising at the end of your sample means you are not done.

### 6. One benevolent dictator owns "good"
Appoint one domain expert as the final authority on quality. The FAQ describes this person as "the definitive voice on quality standards". Others can give input, but one person decides, and multiple annotators are for larger or multi-domain organizations. For an alert router this is the incident-management lead or a senior on-call engineer, not the person who wrote the prompt. When labels conflict ("is MSK disk at 78% a streaming problem or a storage problem?"), the dictator decides, and the decision goes into the labeling guide.

### Agents: two phases and the transition failure matrix
For agents, the FAQ recommends two phases ([Husain and Shankar, FAQ](https://hamel.dev/blog/posts/evals-faq/)):
1. **End-to-end:** a precise success rule per task, treating the agent as a black box, and recording the first upstream failure.
2. **Step-level:** tool choice, argument extraction, error handling, context retention, efficiency, checking tool name, arguments, result and resulting state separately.

The **transition failure matrix** turns first-failure labels into a picture. Rows are the last state that went right, and columns are the state where the first failure happened. The FAQ's text-to-SQL example found "GenSQL → ExecSQL transitions cause 12 failures while DecideTool → PlanCal causes only 2", which tells you where to look first. `error_analysis.transition_matrix` builds it from the `last_good_state` and `first_failure_state` columns. [Module 13](../13-testing-agentic-systems/README.md) uses it for trajectory evals.

## Worked example: 43 router traces and 10 agent traces

**Bad version.** An engineer looks at the 45% pass rate, opens the `failing_graders` counter (`severity: 65, team: 21, ...`), concludes "severity is the problem", and adds a paragraph to the prompt about severity. That counter counts *grader* failures, not *causes*. The severity grader fires for under-calls, over-calls on alarm words, and ignored "RESOLVED" status, which are three different bugs with three different fixes. A single paragraph aimed at "severity" is unlikely to fix all three, and nothing will tell you which it fixed.

**Good version.** Run the harness with tracing, sample, and label:

```bash
python eval_harness.py --trials 5 --traces traces.jsonl
python error_analysis.py sample --traces traces.jsonl --n 100 --stratify slice --out labels.csv
python error_analysis.py label --traces traces.jsonl --csv labels.csv --labeler oncall-lead
```

Here the author labeled one trial of each of the 43 cases, reading each trace. A few rows of the sheet:

```csv
trace_id,case_id,trial,slice,state_path,pass_fail,open_code,axial_code,last_good_state,first_failure_state,labeler
4d543bf6a943,r003,0,streaming,route,fail,503s block producers for the public events API; called SEV3,severity_under_call,,,oncall-lead
...,r023,0,misleading_keyword,route,fail,routed to payments on the topic name payments-events; also ignored 'no customer-visible impact',team_keyword_overmatch,,,oncall-lead
...,r033,0,negative_control,route,fail,'scaled down' read as down: SEV1 page for an autoscaler event,severity_over_call,,,oncall-lead
...,r037,0,secret_in_body,route,fail,rationale repeats the bearer token from the alert body,secret_echoed,,,oncall-lead
```

The report:

```text
$ python error_analysis.py report --csv labels.csv
labeled 43/43 traces, 24 failures

failure modes (axial code: count, share of failures):
  severity_under_call                 6  25%
  team_keyword_overmatch              6  25%
  output_not_bare_json                3  12%
  lifecycle_status_ignored            2  8%
  severity_over_call                  2  8%
  guessed_instead_of_abstaining       2  8%
  secret_echoed                       2  8%
  abstained_when_routable             1  4%

saturation: distinct codes after each 10 labels: [3, 4, 5, 7, 8]
```

(Measured: `error_analysis.py report` on the author's labels of the fake router's traces.)

Read it like an engineer:

- **Two modes are half the failures.** `team_keyword_overmatch` and `severity_under_call` get the first fixes. They are separate fixes: ownership rules and examples for the first, an explicit impact rubric for the second.
- **`output_not_bare_json` is cheap to fix and should not be fixed in the prompt.** Use structured outputs or a validator-and-retry ([Module 14](../14-steering-and-guardrails/README.md)), and keep the `schema` grader as the regression check.
- **`secret_echoed` is rare and launch-blocking.** Frequency is not the only axis. It needs a code grader on every output in production as well as in the eval.
- **The curve is still rising at 43.** Eight modes, with the last two appearing after trace 30. That says keep reading. This sample is too small to claim saturation.

Each mode is now a candidate grader. Most are code checks (`schema`, `no_secret_echo`, the `severity` and `team` match on targeted slices). A mode like "rationale doesn't explain the decision" would need a judge ([Module 11](../11-llm-as-judge/README.md)).

The author also noticed something no grader checks: on every *passing* route, the rationale is a truncated copy of the alert body, not an explanation. The benevolent dictator ruled that on-call engineers read the alert itself, so rationale quality is out of scope for pass/fail for now, and the ruling went into the labeling guide. That is the dictator's job. Without one person deciding, this question would come back in every review.

**The agent.** Ten trials of the coding task, three failures. Labeling each by last good state and first failing state:

| trial | trajectory | last good | first failure | axial code |
|---|---|---|---|---|
| 1 | edited `test_ratelimit.py` to weaken the assertion | inspect | edit | `edited_tests` |
| 3 | fixed `>` to `>=` only | inspect | edit | `partial_fix` |
| 6 | same | inspect | edit | `partial_fix` |

```text
transition failure matrix (rows: last good state, cols: first failure):
                    edit
  inspect              3
```

(Measured from the fake trajectories.) All three failures start at `edit`, after a correct `inspect`. The fix is not in verification: the `verify` step passed every time, because the visible test does not cover the second bug. The two cheapest interventions are a better task statement (name the behavior, "refill must never exceed capacity") and a better visible test. The `report` step also claimed success all three times, which `claim_matches_outcome` flags. With a real agent and more states (`inspect`, `plan`, `edit`, `verify`, `report`), the matrix spreads out and the hot cell is less obvious, which is when it earns its keep.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Letting a model do the open coding from the start | You cannot explain why a mode exists, or the taxonomy reads like a generic list ("hallucination", "tone"). Do at least 30 yourself first. |
| Coding every error in a trace | Downstream modes have inflated counts. Check that each failed row has exactly one axial code: the first failure. |
| Reading only failures | Your taxonomy has no "graders missed it" modes, and you cannot estimate prevalence. Sample passes too. |
| Non-binary failure modes ("severity quality") | Two labelers disagree on the same trace. Split the mode until each is a yes/no question. |
| Committee labeling with no tie-breaker | Repeated debates about the same ambiguous cases. Name the dictator and keep a labeling guide. |
| Stopping at a fixed count | The saturation curve is still rising. Keep going until about 20 consecutive traces add nothing new. |
| Treating grader failure counts as a taxonomy | One grader maps to several causes. Group by cause, not by which assertion fired. |

## In your day job
- Block out two hours this week to read 50 production traces of your LLM feature with a spreadsheet open. Write one line per trace on the first failure.
- Name the benevolent dictator for each LLM feature in its design doc, and keep a labeling guide next to the eval dataset.
- Review the failure-mode counts every sprint, the same way you review incident categories. Fix the top mode, then re-read.
- For agents, add a `state` attribute to every span now, so that you can build the transition matrix when you need it.
