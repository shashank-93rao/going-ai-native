# 01: Why evals, and when to write them

## The idea
A **unit test** checks that a deterministic function, given an input, produces the output its specification says it should. You derive the test from the spec, run it once, and a failure means the code is wrong.

An **eval** measures how often a nondeterministic system behaves acceptably over a *sample* of inputs. Its results are rates, not booleans. The oracle is often fuzzy. Most importantly, there is usually no spec to derive it from: the dataset and graders *become* the spec. For an LLM feature, the eval suite is the only precise, executable statement your team has of what "good" means. The prompt states intent. The eval defines acceptance.

Anthropic's vocabulary is worth adopting as-is, because it keeps conversations precise ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)):

| Term | Meaning | In this module's router |
|---|---|---|
| Task | One input plus its success criteria | One alert row in `router_cases.jsonl` |
| Trial | One attempt at a task. Run several, because outputs vary | `trial=0..4` in `results.jsonl` |
| Grader | Logic that scores a trial, built from assertions | `graders.grade_router` |
| Transcript / trace | The full record of a trial | One trace in `traces.jsonl` |
| Outcome | The final state of the environment, not what the agent *said* | The routed ticket, or the repo after the coding agent stops |
| Eval harness | Runs tasks, records, grades, aggregates | `eval_harness.py` |
| Agent harness | The scaffold that turns a model into an agent | The tool loop in `coding_task.py` |
| Suite | A collection of tasks measuring one capability | The router suite; the coding suite |

When you evaluate an agent you evaluate the harness *and* the model together. Change either and the number changes.

## Why it matters
Hamel Husain's observation from consulting: teams that can only change the system, and cannot quickly measure the effect of a change, stall at demo quality ([Hamel Husain, "Your AI Product Needs Evals"](https://hamel.dev/blog/posts/evals/)). You have seen the systems version of this: a service with no load test where every performance change is argued from intuition.

The other failure is subtler: having evals, but not for the thing that breaks. OpenAI's April 2025 GPT-4o update passed its offline evals and A/B tests and still shipped a sycophantic model, because sycophancy was not something the evals measured. Expert testers had said the model "felt" off, and OpenAI later wrote that it should have weighted those qualitative signals more heavily ([OpenAI, "Expanding on what we missed with sycophancy"](https://openai.com/index/expanding-on-sycophancy/)). An eval only covers what someone thought to measure. That is why this module puts error analysis (reading outputs to discover what to measure) before graders.

## How it works

### Write the definition of "good" as binary checks
Start with what the output is *for*. The router's output pages a human. That gives you concrete properties:

- It parses (a malformed answer pages nobody).
- It names a real team and a real severity.
- It pages the owning team.
- It gets severity right, because a SEV1 wakes people and a SEV4 does not.
- It declines when it cannot tell, rather than guessing.
- It never copies a credential from the alert into a ticket.

Each of these is binary. Prefer binary checks to 1 to 5 scales: Hamel Husain and Shreya Shankar argue that binary labels "force clearer thinking and more consistent labeling", and recommend several specific binary checks when you want to track gradual progress ([Husain and Shankar, "AI Evals FAQ"](https://hamel.dev/blog/posts/evals-faq/)). Anthropic's docs make the same move from vague to measurable: not "classify sentiment well", but an F1 threshold on a held-out set, alongside separate criteria for toxicity and latency ([Anthropic docs, "Define success criteria"](https://platform.claude.com/docs/en/test-and-evaluate/define-success)).

### Two kinds of suites
| | Capability eval | Regression eval |
|---|---|---|
| Question | What can it do that it couldn't? | Does it still do what it did? |
| Expected pass rate | Low at first: a hill to climb | Near 100% |
| Where tasks come from | Hard cases, new failure modes | Capability tasks that now pass, past bugs |
| Used for | Hill-climbing ([Module 12](../12-hill-climbing/README.md)) | CI gates ([Module 15](../15-observability-and-production/README.md)) |

Anthropic recommends graduating capability tasks into the regression suite once they pass reliably ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). The FAQ adds a warning for capability suites: if you pass 100%, "you're likely not challenging your system enough" ([Husain and Shankar](https://hamel.dev/blog/posts/evals-faq/)).

### When to write evals: the EDD argument
Sources disagree on whether to write evals before building.

- **For eval-driven development (EDD).** Eugene Yan: "First, write some evals; then, build systems that pass those evals" ([Eugene Yan, "An LLM-as-Judge Won't Save The Product"](https://eugeneyan.com/writing/eval-process/)). OpenAI's docs say "Adopt eval-driven development: Evaluate early and often" ([OpenAI, "Evaluation best practices"](https://developers.openai.com/api/docs/guides/evaluation-best-practices)).
- **Against, mostly.** The Husain and Shankar FAQ answers "should I write evals first?" with "generally no". An LLM's failure surface is effectively unbounded, so evaluators written before you have seen outputs tend to test imagined failures and miss real ones. The exception is a specific, known constraint, such as "never mention competitors" ([Husain and Shankar](https://hamel.dev/blog/posts/evals-faq/)). Criteria drift supports this: "users need criteria to grade outputs, but grading outputs helps users define criteria" ([Shankar et al.](https://arxiv.org/abs/2404.12272)).

> **Course stance (synthesis, from [01-gap-analysis.md](../research/01-gap-analysis.md)):** write **constraint evals** up front, and discover **failure-mode evals** through error analysis.
>
> - *Constraint evals* encode things you know before seeing a single output: the schema, the enums, safety and privacy rules, "test pages never page a human", latency budgets. They are cheap, almost always code-graded, and they belong in the first commit.
> - *Failure-mode evals* encode what actually goes wrong: "routes on a keyword in a topic name", "under-calls severity when impact is implied rather than stated". You cannot guess these reliably. You find them by reading traces ([03-error-analysis.md](03-error-analysis.md)).
>
> Both camps agree on the parts that matter: evaluate early, and let real failures drive coverage. The disagreement is only about failure modes you have not observed yet. Do not write graders for those.

## Worked example: the router's first eval

**Bad version.** A developer adds a test next to the prompt:

```python
def test_router_kafka():
    out = route(client, {"title": "KafkaConsumerLagHigh", "body": "lag 1.2M on orders.v2"})
    assert json.loads(out)["team"] == "streaming"
```

It passes. The team ships. Why this fails as an eval:

- **One input.** It says nothing about the 40 other kinds of alerts.
- **One trial.** A system that is right 60% of the time on this input passes this test 60% of the time. CI flakes, and someone adds `@retry(3)`, which hides the 40%.
- **Only the happy path.** Nothing checks severity, abstention, or that a `[TEST]` page is not routed.
- **No definition of good beyond one field.** The output could contain the customer's bearer token and the test would pass.

**Good version.** Day 0, before any error analysis, write the constraints as code and give each a stable name. In `code/graders.py` they are:

| Check | Kind | Gating | Written when |
|---|---|---|---|
| `schema`: valid JSON object, known keys, enums, `abstain` implies nulls | constraint | yes | day 0 |
| `no_secret_echo`: output must not match bearer, AWS key or PEM patterns | constraint | yes | day 0 |
| `decision`: route vs abstain matches the label | constraint | yes | day 0 |
| `team`, `severity`: exact match against the label | correctness | yes | day 0 (needs labeled cases) |
| `severity_within_1`: ordinal partial credit | diagnostic | no | day 0 |
| "keyword over-match" etc. | failure mode | yes | **after** error analysis |

Every case is one JSONL row. This one encodes a constraint (test pages are not routed) and is a negative control:

```json
{"id": "r034", "input": {"source": "pagerduty-manual", "title": "[TEST] PagerDuty integration test, ignore",
  "body": "This is a test page sent by the on-call tooling team to verify routing. No action required.",
  "service": "", "env": "prod"},
 "expected": {"decision": "abstain", "team": null, "severity": null},
 "slice": "negative_control", "tags": [], "split": "dev", "origin": "handwritten"}
```

Run it over all 43 cases, 5 trials each, with the deliberately flawed fake model:

```bash
cd 10-evals-fundamentals/code
AINATIVE_FAKE=1 python eval_harness.py --trials 5 --k 1 3 5 --traces traces.jsonl
```

```text
group                            cases pass_rate    pass@1    pass^1    pass@3    pass^3    pass@5    pass^5   correct   abstain     wrong  aa_score
----------------------------------------------------------------------------------------------------------------------------------------------------
OVERALL                             43    0.4465    0.4465    0.4465    0.4814    0.4186    0.4884    0.4186    0.4465    0.0233    0.5302   -1.1442
...
slice=identity                       4       1.0       1.0       1.0       1.0       1.0       1.0       1.0       1.0       0.0       0.0       1.0
slice=misleading_keyword             4       0.1       0.1       0.1     0.225       0.0      0.25       0.0       0.1       0.0       0.9      -2.6
slice=secret_in_body                 2       0.0       0.0       0.0       0.0       0.0       0.0       0.0       0.0       0.0       1.0      -3.0

failing gating graders (trial count): {'severity': 65, 'team': 21, 'decision': 15, 'schema': 15, 'no_secret_echo': 10}
prompt hashes: ['77a194b5ba4f']   wrong-answer penalty: 3.0
```

(Measured output from the fake model in `code/`. The fake's flaws are planted, so these numbers describe the fake, not any real model.)

Read what the eval told you that the unit test could not. The `identity` slice is perfect, and a demo on login alerts would look great. Keyword-trap alerts almost always fail. Two cases leak secrets on every trial. The single `prompt hash` tells you every trial ran the same prompt version, so the numbers are comparable. Overall, more than half of the answers are confidently wrong, which is why the abstention-aware score is negative (see [06-metrics.md](06-metrics.md)).

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Treating one passing example as an eval | Count tasks and trials. Fewer than about 20 tasks or 1 trial per task is a smoke test, not an eval. |
| Writing failure-mode graders before reading outputs | For each grader, ask "which trace made us write this?". If no one can point to one, it is speculative. |
| Using a 1 to 5 score as the verdict | Labelers cluster on 3, and nobody can say what a 0.4 change means. Replace it with named binary checks. |
| Re-running a flaky case until it passes | Your CI has `retry` around an eval. Run k trials and report pass^k instead (see [06-metrics.md](06-metrics.md)). |
| A capability suite at 100% | It has stopped measuring anything. Add harder tasks, or move it to regression. |
| Measuring only what you planned | Experts say outputs "feel off" and no eval moves. Treat that as an untested failure mode and go read traces. |

## In your day job
- Before the first prompt commit, write the constraint checks (schema, enums, secrets, "never do X") as code and wire them into CI.
- Put the eval dataset and graders in the same repo as the prompt, and review them in the same PR. Changing what "good" means is a code change.
- When someone proposes a new grader, ask for the traces that motivated it.
- Track capability and regression suites separately, with different gates: regression must be near 100%, capability is a trend.
