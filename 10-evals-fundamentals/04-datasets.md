# 04: Datasets

## The idea
An eval dataset is a versioned set of **tasks**. Each task is an input plus everything a grader needs to decide whether a trial succeeded: an expected output, a reference solution, or a target environment state. Each task also carries metadata for analysis: the **slice** it belongs to, the **split** (dev or test), and its **origin** (which incident, trace or person it came from).

Where tasks come from matters more than how many there are. In priority order: real failures from production traces and bug reports, then a handful of handwritten cases, then synthetic cases to fill gaps you can name ([Lance Martin, "Automating eval design and hillclimbing with Claude"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Two more ingredients turn a list of examples into an eval: **negative controls**, which check that the system does *not* do something, and a **frozen test split** you do not tune against.

## Why it matters
Teams delay evals because they think they need hundreds of tasks. Anthropic's guidance is that "20-50 simple tasks drawn from real failures is a great start" ([Anthropic, "Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). The opposite mistake is worse: a large dataset that does not resemble production. OpenAI lists "synthetic data that doesn't match production" among its eval anti-patterns ([OpenAI, "Evaluation best practices"](https://developers.openai.com/api/docs/guides/evaluation-best-practices)).

One-sided datasets produce one-sided systems. Anthropic's example is web search: if every task rewards searching, you get an agent that searches for almost everything. The fix is to test both the cases where a behavior should happen and the cases where it should not ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). For a router, "should not" means not paging anyone for a test alert, and not calling SEV1 because an autoscaler "scaled down".

## How it works

### The row
```json
{"id": "r023",
 "input": {"source": "prometheus", "title": "Consumer lag on payments-events topic",
           "body": "Consumer group ledger-writer lag 300k on topic payments-events; ledger postings delayed about 10 min; no customer-visible impact.",
           "service": "ledger-writer", "env": "prod"},
 "expected": {"decision": "route", "team": "streaming", "severity": "SEV3"},
 "slice": "misleading_keyword", "tags": ["negation"], "split": "dev", "origin": "INC-2312 postmortem"}
```

- `slice` is what you will break metrics down by. Choose slices that match your failure modes and your risk: one per team, plus `abstain`, `negative_control`, `misleading_keyword`, `secret_in_body`.
- `tags` are secondary labels for cross-cutting properties (`implicit_impact`, `negation`, `ambiguous_owner`).
- `origin` is provenance. When a case's label is disputed, you need to find the incident it came from.

(The incident IDs and alerts in this module's dataset are realistic but fictional.)

### Sources, in order
1. **Real failures.** Every postmortem, every misroute an on-call engineer complained about, every bug-tracker item. Anthropic suggests converting the manual checks you already do and your bug-tracker items into tasks.
2. **Production traces**, sampled during error analysis. Copy the input verbatim (minus secrets), and have the dictator label the expected output.
3. **Handwritten cases** for constraints you know about up front: test pages, resolved alerts, alerts that carry a credential.
4. **Synthetic cases** to fill named coverage gaps. See below.

### Make tasks unambiguous
"A good task is one where two domain experts would reach the same verdict and everything the grader checks is stated in the task" ([Lance Martin](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). For the router, that means the severity rubric and team ownership are in the system prompt, so every label follows from information the model has. For the coding task, that means a reference solution exists and passes the hidden tests. `test_full_fix_passes_everything` checks this. Anthropic: 0% pass@100 "is most often a signal of a broken task, not an incapable agent".

### Synthetic data from dimension tuples
When you have no traffic yet, or a slice has few real examples, generate inputs. The procedure in the Husain and Shankar FAQ ([Husain and Shankar, "AI Evals FAQ"](https://hamel.dev/blog/posts/evals-faq/)):

1. **Name dimensions**: the axes along which real inputs vary.
2. **Write about 20 tuples by hand**, one value per dimension, to check the dimensions make sense.
3. **Scale up.** Either take the cross product and filter out impossible combinations (broad coverage), or have a model generate tuples directly (better when most combinations are invalid).
4. **Convert each tuple to a natural-language input in a separate prompt.** Splitting "what to cover" from "how to phrase it" avoids the repetitive phrasing you get from one big "generate 50 examples" call.

Two rules from Hamel's other writing: synthesize **inputs only, never the responses** ([Hamel Husain, "Using LLM-as-a-Judge"](https://hamel.dev/blog/posts/llm-judge/)), and verify that each generated scenario actually triggers the behavior it claims to ([Hamel Husain, "A Field Guide"](https://hamel.dev/blog/posts/field-guide/)). A "misleading keyword" alert without a misleading keyword is a mislabeled case.

The FAQ also advises fixing obvious prompt gaps directly rather than generating test data for them. If the prompt never says who owns the CDN, add that line; you do not need 20 synthetic CDN alerts to find out.

### Volume vs quality
Anthropic's docs say to "prioritize volume over quality" ([Anthropic docs, "Create strong empirical evaluations"](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)). Anthropic's agent-eval post says 20 to 50 tasks from real failures is a great start. These fit together once you look at cost per task. A single-turn classification case is cheap to run and to grade, so more cases with automated grading beats a few hand-graded ones. An agentic task with an environment, hidden tests and minutes of runtime is expensive, so each one must earn its place. *Course synthesis:* go for volume where tasks are cheap and code-graded, and for curation where they are expensive.

One more warning from Lance Martin: do not build the dataset only from cases your *current* model fails. That measures the model's "failure fingerprint", and the next model will have a different one. Pick cases a human judged hard.

### Splits
- **dev**: what you read, debug against, and tune prompts on.
- **test**: frozen. Run it to report, never to debug. The course syllabus calls this "freeze-and-read-test-once" ([syllabus](https://maven.com/parlance-labs/evals)).
- **Split by cluster, not by row**, when several cases come from one incident. Otherwise near-duplicates sit on both sides and the test split leaks. [Module 12](../12-hill-climbing/README.md) covers train/test discipline for hill-climbing and clustered standard errors.

The router dataset puts every third case in `test` (14 of 43). That is fine for a teaching set. In a real suite, stratify the split by slice so each slice has test coverage.

## Worked example: from a vibe dataset to a golden set

**Bad version.** Someone asks a model for data:

```text
Generate 30 diverse production alerts as JSON, each with the correct team and severity.
```

What comes back is 30 alerts that look alike: tidy titles, every component named, severity spread evenly, no empty bodies, no test pages, no secrets. The labels were written by a model, so a model-based router agrees with them for the same reasons it would agree with itself, and that agreement is not evidence of correctness. Nothing in the set resembles the 03:00 page that says only `CRITICAL`.

**Good version.** The router set in `code/data/router_cases.jsonl` has this composition:

| Property | Counts |
|---|---|
| Origin | 14 from postmortems, 19 from production traces, 10 handwritten |
| Decision | 37 route, 6 abstain |
| Severity | SEV1 6, SEV2 13, SEV3 14, SEV4 4 |
| Slices | streaming 7, database 5, network 5, abstain 5, identity 4, storage 4, misleading_keyword 4, negative_control 4, payments 3, secret_in_body 2 |
| Split | 29 dev, 14 test |

The negative controls are the cases where a trigger word is present and the triggered behavior is wrong:

| id | Input (abridged) | Trap | Expected |
|---|---|---|---|
| r033 | "Autoscaler scaled down consumer group ... lag 0" | "down" | streaming, SEV4 |
| r034 | "[TEST] PagerDuty integration test, ignore" | looks like a page | abstain |
| r035 | "RESOLVED: DNS resolution errors" | error words | network, SEV4 |
| r036 | "Scheduled maintenance: postgres minor upgrade tonight" | "read-only period" | database, SEV4 |

Then fill the gaps with tuples. `synth_data.py` defines five dimensions:

```python
DIMENSIONS = {
    "subsystem": ["kafka", "postgres", "dns", "oauth", "payments-api", "object-store"],
    "symptom": ["error_rate", "latency", "saturation", "outage", "cert_expiry"],
    "impact": ["none_yet", "internal", "customer_facing"],
    "signal_quality": ["clear", "misleading_keyword", "missing_service", "negated_impact"],
    "source": ["prometheus", "datadog", "cloudwatch", "pagerduty-manual"],
}
```

```text
$ python synth_data.py --n 24 --out data/synth_cases.jsonl
1440 tuples in the cross product, 944 after filtering
wrote 24 draft cases to data/synth_cases.jsonl (0 rejected). Review every label before use.
```

(Measured, with the offline fake writer.) The filter rules are named predicates such as "an outage always has impact". `stratified_sample` guarantees every subsystem and every signal quality appears at least once. Each tuple then becomes its own writer prompt, which carries the tuple and an explicit instruction not to reveal the team or severity:

```text
Write ONE realistic production alert as a JSON object with keys
"source", "title", "body", "service", "env". Do not say which team owns it or how severe it is.

Make it match this scenario exactly:
<scenario>{"impact": "internal", "signal_quality": "clear", "source": "cloudwatch", "subsystem": "object-store", "symptom": "outage"}</scenario>
...
```

The output row keeps the tuple and a rule-drafted label flagged for review:

```json
{"id": "s006", "input": {"source": "cloudwatch", "title": "outage on object store bucket media",
  "body": "object store bucket media all requests failing since 10:42 UTC. Internal batch jobs retrying.",
  "service": "media-store", "env": "prod"},
 "expected": {"decision": "route", "team": "storage", "severity": "SEV2"},
 "slice": "storage", "origin": "synthetic", "needs_review": true,
 "tuple": {"subsystem": "object-store", "symptom": "outage", "impact": "internal", "signal_quality": "clear", "source": "cloudwatch"}}
```

This row shows why `needs_review` exists. The draft rule says "an internal-only outage is SEV2". The dictator might rule that a total object-store outage is SEV1 regardless of who is calling, because customer impact is minutes away. That ruling changes `draft_label`, and the labeling guide records it. With the real API, the writer prompt runs at `temperature=1.0`, one call per tuple, and rejects anything that is not valid JSON with a `title` and `body`.

## Pitfalls
| Pitfall | How to detect it |
|---|---|
| Model-written labels | Check `origin` and `needs_review`. Any row with a synthetic label that no human reviewed is not golden. |
| No negative controls | Every case expects the behavior to fire. Count cases whose expected output is "do nothing" or "abstain". The router set has 9 of 43 across the `abstain` and `negative_control` slices. |
| Synthetic scenario doesn't trigger | Grep synthetic `misleading_keyword` inputs for an off-team keyword. Spot-check 10 rows per slice. |
| Tuning on test | Your test pass rate tracks dev perfectly, round after round. Record who ran test and when. |
| Duplicates across splits | Hash normalized inputs, and group by `origin`. The same incident should never appear in both splits. |
| Dataset tracks only the current model's failures | The set's pass rate jumps on a model upgrade and nothing else changed. Add cases a human judged hard. |
| Unversioned data | Results from two weeks ago can't be reproduced. Commit the JSONL, and log a hash of it next to the prompt hash. |

## In your day job
- Start your first suite this week from the last 20 to 50 things that went wrong, not from a brainstorm.
- Add a `slice`, `split` and `origin` field to every row from day one. Retrofitting them is painful.
- Ask your incident-management lead to own the labels. Give them a short labeling guide and the `needs_review` queue.
- Every postmortem for an LLM feature ends with a new eval row, the same way every bug fix ends with a regression test.
