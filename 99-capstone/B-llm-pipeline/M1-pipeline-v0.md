# B-M1: Pipeline v0: map/reduce over documents
**Time:** one day. **Offline:** scaffold yes; the real run needs a key. **Modules:** [02](../../02-prompting-as-specification/README.md), [06](../../06-agent-architectures/README.md), [08](../../08-harness-engineering/README.md), [15](../../15-observability-and-production/README.md).

## Goal
Get an end-to-end real-model run of the pipeline over all documents with traces, token counts and recorded responses. Write the labeling guide *before* you look at any output.

## Why the labeling guide comes first
In an extraction pipeline, the label definitions are the spec. "Duration" could mean impact start to resolution, declaration to resolution, or first alert to mitigation. If you have not decided, the model will decide for you, differently per document, and your M3 error analysis will be an argument with yourself. Writing the guide before looking at outputs also protects against a subtle bias: once you have seen what the model produces, you will be tempted to define fields so that its outputs count as correct. Shankar et al. call the reverse effect criteria drift: grading outputs changes your criteria ([Who Validates the Validators?](https://arxiv.org/abs/2404.12272)). You will revise the guide in M3, but you want a v1 that predates the outputs, so the revisions are visible.

## Steps
1. **Read five documents** and the generator. Note every place where a field is ambiguous.
2. **Write `LABELING.md`**: for each field, a definition, the allowed values, how to handle absence, and two edge cases. This is the system of record ([08-harness-engineering](../../08-harness-engineering/README.md)).
3. **Copy `pipeline_v0.py`** and put the definitions into the extraction prompt. Version the prompt.
4. **Wrap the client** in `RecordingClient` so every real response is saved to a cassette. Reruns of unchanged prompts use `ReplayClient` and cost nothing.
5. **Run it for real** over all 20 documents, with traces:
   ```bash
   python pipeline_v0.py --out runs/v0/preds.jsonl --traces runs/v0/traces.jsonl
   python score.py runs/v0/preds.jsonl
   ```
6. **Record cost**: input and output tokens per document (they are in each prediction row and in the `map_extract` span), and the total. Convert to currency with the current price sheet and note its date.
7. **Separate the stages** in code so each can be swapped in M4: `map_extract`, `validate` (new: schema and enum checks, see below), `reduce_stats`, `reduce_themes`.

## Worked example: the prompt as a spec
Bad (the v0 prompt, roughly):

```text
Extract incident facts from the postmortem below. Return only a JSON object with keys:
... duration_minutes (int) ...
```

Why it fails: "duration" is undefined. On a document whose header says "Duration: 2h 52m" and whose timeline runs 09:36 to 12:28, both readings agree (172 minutes). On a `detection_in_prose` document, the header is absent, the timeline's first entry is the alert, and the true start is in a later paragraph. A model that computes "first timeline entry to resolution" is consistently wrong there, and nothing in the prompt says it is wrong.

Better (excerpt):

```text
Field definitions. These are exact; follow them even when the document uses other terms.

duration_minutes: minutes from IMPACT START to RESOLUTION.
  - IMPACT START is when customer or system impact began, which may be stated
    outside the timeline (e.g. "later log analysis showed impact began at 09:02").
    It is NOT the first alert or the declaration time.
  - RESOLUTION is the timeline entry where error rates returned to baseline.
  - If a "Duration:" header exists, it is authoritative.
  - If neither can be determined, null. Never estimate.

severity: the FINAL severity. If the incident was upgraded or downgraded, use the last
  level stated. Ignore severities mentioned in runbook excerpts or appendices.

services_affected: services listed as affected in the Impact section, or described as
  having elevated errors. A service that was "suspected" or "investigated" but found
  normal is NOT affected.
```

Then a validator, in code, after the map step:

```python
SEVERITIES = {"SEV1", "SEV2", "SEV3"}
CATEGORIES = {"deploy", "config", "capacity", "dependency", "data", "network"}

def validate(row: dict) -> list[str]:
    """Return a list of problems; the row is kept either way, and problems are logged."""
    probs = []
    if row.get("severity") not in SEVERITIES | {None}:
        probs.append(f"severity {row.get('severity')!r} not in enum")
    if row.get("root_cause_category") not in CATEGORIES | {None}:
        probs.append("root_cause_category not in enum")
    d, t = row.get("detection_minutes"), row.get("duration_minutes")
    if isinstance(d, int) and isinstance(t, int) and d > t:
        probs.append(f"detection {d} > duration {t}: impossible by definition")
    return probs
```

The `d > t` check is an invariant that follows from the definitions (you cannot detect an incident after it ended), and it is free to check on unlabeled production data. Those are the checks M6's drift monitor will lean on.

## Deliverables
- `LABELING.md` v1, committed before the first real run (the commit order is the evidence)
- The versioned prompt, `validate`, and a cassette of the v0 run
- `runs/v0/`: predictions, traces, the score report, and tokens/cost per doc

## Done when
- [ ] One command runs the whole pipeline and writes predictions, aggregates and traces.
- [ ] Parse failures and validation problems are recorded per row, not raised.
- [ ] Rerunning with `ReplayClient` reproduces the predictions exactly with zero API calls.
- [ ] Tokens and cost per document are reported.
- [ ] LABELING.md v1 has a definition, allowed values, absence rule and edge cases for every field.

## Reuse
- `../code/pipeline_v0.py` (`map_extract`, `reduce_stats`, `reduce_themes`, `parse_json_object`), `../code/score.py`
- `ainative_kit.RecordingClient`, `ReplayClient`, `Tracer`
- Prompts as versioned specs: [02-prompting-as-specification](../../02-prompting-as-specification/README.md)

## Pitfalls
- **Fixing the prompt before scoring v0.** You lose the baseline. Score first, always.
- **Asking for JSON and trusting it.** Parse defensively and validate. Count parse failures as a metric; they are a recall loss.
- **Prefill to force JSON.** It errors on current Claude models (course style rule). Use a clear output instruction, a validator and a retry, or structured outputs ([14-steering-and-guardrails](../../14-steering-and-guardrails/README.md)).
