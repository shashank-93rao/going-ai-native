# 07: Evaluating and hill-climbing RAG

## The idea

A RAG system has as many tunable parts as a database query planner, and all of them interact. You can't improve it by intuition. You improve it with a **labeled question set**, **per-stage metrics** that say where the failure is, **ablations** that change one component at a time, and **error bars** that say whether a change is real. [Module 03](../03-context-engineering/06-retrieval-agentic-search-vs-rag.md) introduced the tiers (retrieval, grounding, judged faithfulness, abstention). This file is the full workflow, built on `rag_eval.py`.

The metrics, mapped to Liu's Q/C/A relationships ([Liu, "There are only 6 RAG evals"](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/)):

| Metric | Relationship | Needs | Cost |
|---|---|---|---|
| recall@k, MRR, nDCG@k (doc ids) | C\|Q | Relevant doc labels | Free, deterministic |
| evidence@k (verbatim answer span shown) | C\|Q, finer | Evidence-span labels | Free, deterministic |
| recall@candidates vs recall@final | C\|Q per stage | Same | Free |
| Citation precision, grounding | A\|C | Chunk ids in answers | Free, deterministic |
| Faithfulness (claims supported) | A\|C | LLM judge or NLI | Calibrate first |
| Answer relevance | A\|Q | LLM judge | Calibrate first |
| Abstention (correct / abstain / wrong) | Q\|C answerability | Unanswerable labels | Free given answers |

## Why it matters

Each metric is blind to some failure the others catch. Here are three real cases from this module's eval:

- **q04** ("the box is out of space"): doc recall@5 = 0.5 and evidence@5 = 0. The right runbook's *Symptoms* section was retrieved and its *Mitigation* section wasn't. Doc-level recall alone would score this as half right.
- **q25** ("what retry budget does the envoy gateway use"): the answer was grounded and cited, from the wrong doc. It quoted the postmortem saying the budget "had not been rolled out to this route", not the ADR that defines it as 20%. Citation precision was 1.0. Answer relevance failed.
- **q06 with a lying generator**: "Set maxmemory-policy to `allkeys-lru`" passes the deterministic grounding check. Every word, including the backticked value, appears in the cited chunk, because the chunk says `allkeys-lru` is *wrong*. Lexical grounding can't see polarity. `test_lexical_grounding_is_fooled_by_a_negation_flip` pins this as a known gap.

## How it works

### 1. Build the labeled set

Each row in `data/questions.jsonl`:

```json
{"id": "q14", "team": "payments", "category": "acl",
 "question": "how long do we keep the old signing key in JWKS after promoting a new one",
 "answerable": true, "relevant_docs": ["adr-024-token-format"],
 "evidence": ["keep the old public key in JWKS until all tokens signed with it expire"],
 "note": "Same question as q13. Payments cannot see the restricted runbook, so the correct answer comes from the public ADR and is less specific."}
```

What makes a set useful:

- **Questions phrased the way users phrase them.** Take them from Slack, pages and tickets, not from the doc authors. Symptom phrasing ("pods keep getting kicked off") is where retrieval breaks.
- **Evidence spans, not just doc ids**, so chunking failures are visible ([02](02-chunking-and-embeddings.md)).
- **Unanswerable questions** (6 of 44 here). Without them, a system that never abstains scores perfectly.
- **Permission-dependent pairs.** The same question asked by two teams, with different correct outcomes (q13/q14, q32/q33). These are your ACL regression tests.
- **Category tags** (identifier, paraphrase, multi-hop, acl, unanswerable) so you can slice results.
- **Test the labels.** `test_corpus_data.py` checks that every evidence span exists verbatim in a relevant doc and that every relevant doc is readable by the asking team. A wrong label silently corrupts every metric downstream.

**Size.** With 38 answerable questions, one question is 2.6 points of evidence@5. A paired bootstrap CI on a typical delta here is about ±8 points wide. To resolve a 5-point difference you need a few hundred questions ([Module 12](../12-hill-climbing/README.md) has the power calculation). Start with 40, and grow from production traffic.

### 2. Retrieval metrics

`rag_eval.py` computes them per question, so you can pair and slice:

- **recall@k**: share of relevant docs in the top k.
- **MRR**: 1/rank of the first relevant doc.
- **nDCG@k**: rewards relevant docs near the top with a log discount, normalized by the ideal ordering.
- **evidence@k**: 1 if any top-k chunk contains a labeled answer span verbatim.

### 3. Generation metrics: deterministic first, then judges

The deterministic `grounding_check` runs on every production answer, not only in evals. It catches citations to unseen chunks, claims whose terms aren't in the cited chunk, backticked commands that don't appear verbatim, and uncited sentences.

For what it can't see (polarity, relevance, completeness), you need a model:

- **RAGAS-style metrics.** RAGAS computes faithfulness as supported claims divided by total claims, after an LLM splits the response into claims and checks each against the context ([RAGAS faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)). Its response relevancy generates 3 questions from the answer by default (`strictness`), embeds them, and averages their cosine similarity to the user's question ([RAGAS answer relevancy](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/)). These are convenient and cheap to start with.
- **Calibrated binary judges.** For anything that gates a release, the course stance from [Module 11](../11-llm-as-judge/README.md) applies. Use a binary rubric per failure mode ("does the answer recommend anything the cited chunk says not to do? yes/no"), and measure the judge's agreement with your own labels on 50 to 100 examples before you trust it. A continuous 0.73 faithfulness score from an uncalibrated model is a number, not a measurement. Its errors are correlated with the generator's when both are LLMs.

A judge for the q06 failure, as a rubric (illustrative; calibrate before use):

```text
You are checking one sentence of an on-call answer against the chunk it cites.
<chunk>{chunk_text}</chunk>
<sentence>{sentence}</sentence>
Does the sentence recommend, permit or state something the chunk says is wrong,
forbidden or unsafe? Answer with JSON: {"contradicts": true|false, "quote": "<the chunk text that decides it>"}
```

### 4. Abstention is a dial; find the setting with data

Every RAG system has some threshold for "not covered": a retrieval score floor, a judge, or the model's own judgment. Moving it trades coverage for hallucination. Score answerable and unanswerable questions separately, because one number hides the trade.

### 5. Ablations and hill-climbing

Change one component per run against a fixed baseline, on the same questions, and report a **paired** delta with a CI (`paired_bootstrap`). That's [Module 12](../12-hill-climbing/README.md)'s loop applied to RAG. Order the climb by pipeline stage, cheapest first: labels and evidence spans, then chunking, then hybrid and fusion, then reranker, then query-side, then generator prompt, then model.

### 6. Production monitoring

Offline evals tell you what was true on your labeled set. Production signals tell you when that stopped being representative:

| Signal | What it catches | Slice by |
|---|---|---|
| No-result rate (retrieval returned nothing) | Index outage, ACL filter starving, new topic | team, query category |
| `results_returned < k` | Filtered-ANN starvation ([03](03-indexes-and-vector-stores.md)) | team |
| Abstention rate | Corpus gaps, or a broken generator (abstains on everything) | team, topic |
| Grounding-check failure rate | Generator regressions, prompt changes | model, prompt version |
| Top-1 retrieval score distribution | Query drift, embedding mismatch | embedding model id |
| ANN recall vs exact on sampled queries | Index degradation, tombstone build-up | index generation |
| Index lag p99 and canary age | Freshness SLO ([06](06-ingestion-freshness-and-correctness.md)) | source |
| Citation click-through, thumbs-down with reason | Relevance failures no check sees | doc kind |

Feed thumbs-down and abstentions back into the labeled set weekly. That's how the eval tracks the questions people actually ask.

## Worked example: the full report

Real output from `rag_eval.py` (abridged; the full ablation is in [02](02-chunking-and-embeddings.md) and [04](04-hybrid-search-fusion-and-reranking.md)):

```text
$ PYTHONPATH=shared .venv/bin/python 18-rag-systems/code/rag_eval.py
44 questions (38 answerable, 6 unanswerable for the asking team)

config                                     recall@5    MRR  nDCG@5  evid@5  words   evid@5 delta vs row 1 [95% CI]
bm25 heading, no header (Module 03 style)     0.965  0.974   0.949   0.789    108   +0.000 [+0.000, +0.000]
hybrid RRF heading + header                   0.965  0.987   0.964   0.816    101   +0.026 [-0.053, +0.105]
hybrid fixed 40w + header                     0.978  0.974   0.963   0.947    172   +0.158 [+0.026, +0.289]
hybrid sentence -> whole doc                  0.978  0.974   0.965   1.000    396   +0.211 [+0.079, +0.342]
...
End to end (hybrid heading, fake extractive generator), by abstention threshold:
  min_overlap=2  answerable_correct=0.95  answerable_wrong=0.05  answerable_abstain=0.00  unanswerable_abstain=0.67  unanswerable_answered=0.33
      wrong: ['q13', 'q25', 'q33', 'q40']
  min_overlap=3  answerable_correct=0.84  answerable_wrong=0.05  answerable_abstain=0.11  unanswerable_abstain=1.00  unanswerable_answered=0.00
      wrong: ['q13', 'q25']
  min_overlap=4  answerable_correct=0.50  answerable_wrong=0.03  answerable_abstain=0.47  unanswerable_abstain=1.00  unanswerable_answered=0.00
      wrong: ['q13']
```

The generator here is `fake_generator_responder`, a deterministic extractive stand-in. It picks the sentence sharing the most terms with the question, and abstains below `min_overlap` shared terms. It never invents text, so every non-abstained answer passes grounding (40 of 40 at `min_overlap=2`). The table measures retrieval and the abstention dial, not a real model's reasoning.

**Bad version: one accuracy number.** "End-to-end accuracy 95%" at `min_overlap=2`. That's true for answerable questions, and it hides that a third of unanswerable questions got a confident, cited, wrong answer (q33 and q40 both cite ADR-024's JWKS sentence, for questions about log leaks and HSM keys).

**Good version: read the trade-off and pick deliberately.**

- `min_overlap=3` abstains on every unanswerable question and costs 11 points of coverage on answerable ones (q05, q23, q26, q27 now abstain).
- `min_overlap=4` halves coverage for no further safety gain.
- For an on-call assistant, a wrong command is worse than "not covered", so 3 is the choice. Write that rationale next to the number, the same way you'd document an alert threshold.
- **q25 and q13 stay wrong at every threshold.** They aren't abstention problems. q25 is answer relevance (a grounded sentence from the wrong doc), and q13 is the generator preferring a vaguer public sentence over the restricted runbook it was shown. A threshold can't fix either. They need a relevance judge, or a better generator. The per-question `wrong:` list is what tells you that.

**Then climb.** Evidence@5 says chunking is the biggest retrieval lever on this corpus (+15.8 and +21.1 points, CIs excluding zero). Hybrid vs BM25 is inside the noise at n=38. So the next round is "sentence-to-whole-doc for runbooks, heading chunks for ADRs", re-measured with the same paired bootstrap, not a reranker purchase.

## Pitfalls

- **Labels without evidence spans.** Detect it: chunker changes never move the metric. Add spans.
- **No unanswerable questions.** Detect it: abstention rate in production is near zero, and nobody knows whether that's good. Add 10 to 15% unanswerable and permission-dependent rows.
- **One blended score.** Detect it: you can't say whether a change traded safety for coverage. Report answerable and unanswerable outcomes separately.
- **Trusting RAGAS numbers as gates.** Detect it: a release blocked or shipped on a 0.02 faithfulness change with no judge calibration. Calibrate binary judges against your labels ([Module 11](../11-llm-as-judge/README.md)).
- **Deterministic grounding treated as complete.** Detect it: no test for negation flips. Keep the characterization test, and add a contradiction judge.
- **Unpaired comparisons on small sets.** Detect it: "+3 points" with no CI on 40 questions. Use paired bootstrap; expect ±8.
- **Eval set frozen at launch.** Detect it: production abstentions on topics absent from the set. Add from thumbs-down and abstentions weekly.

## In your day job

- Turn your assistant's last month of questions into 40 labeled rows with evidence spans, 5 unanswerable rows and 3 permission-dependent pairs. Test the labels in CI.
- Report per-stage metrics (evidence@k, recall@candidates, grounding failures, abstention split) on one dashboard, sliced by team.
- Sweep your abstention threshold on the labeled set and write the chosen value and its rationale into the service's runbook.
- Gate retrieval changes in CI on the paired-bootstrap lower bound of evidence@k against main ([Module 12](../12-hill-climbing/README.md)).
