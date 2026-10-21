# B-M4: Hill-climb: decomposition, chunking, model/effort, cost frontier
**Time:** one weekend. **Offline:** analysis yes; runs need a key (cache aggressively). **Modules:** [12](../../12-hill-climbing/README.md), [03](../../03-context-engineering/README.md), [01](../../01-llms-for-systems-engineers/README.md), [14](../../14-steering-and-guardrails/README.md).

## Goal
Search the space of pipeline rewrites by hand, the way DocETL's optimizer searches it automatically, and finish with an accuracy/cost frontier and a chosen operating point justified against a budget.

## The search space
DocETL's README describes its optimizer as tuning pipelines by swapping models, rewriting prompts, breaking operations into subtasks, and replacing parts with code where possible ([DocETL repo](https://github.com/ucbepic/docetl); [optimizer paper](https://arxiv.org/abs/2512.02289)). Concretely, for this pipeline:

| Rewrite | What changes | Targets (from M3) | Cost effect |
|---|---|---|---|
| **Field decomposition** | One map call per field group (severity+timeline; services; impact) instead of one call for all | fields that interfere | ~2–3x calls; smaller prompts |
| **Section chunking** | Split the doc by `##` headings; route each field to the sections that define it (services from Impact, severity from Timeline) | distraction (appendix, decoys) | fewer input tokens per call |
| **Code for the computable** | Extract timestamps with the model, compute minutes in Python | arithmetic, normalization | cheaper and exact |
| **Gleaning / self-check** | A second pass: "here is the doc and your extraction; list fields that are unsupported or wrong; fix them" | hallucination | +1 call per doc |
| **Model cascade** | Cheap model first; escalate to a larger one when the validator flags the row or fields are null | cost | depends on escalation rate |
| **Model and effort** | Same pipeline on Haiku / Sonnet / Opus; reasoning effort low/high | everything | the frontier's x-axis |

## Steps
1. **Noise check.** Run v1 (post-M3) on dev three times. Real-model extraction at temperature 0 still varies. Measure the per-field spread; it sets the smallest change you act on.
2. **One rewrite per round**, starting with the M3 plan's top target. Run on dev, compare paired with `paired_bootstrap(a, b, labels)`. Then run on test once.
3. **Apply the same keep/revert rules as variant A:** train (dev) up and test flat means revert; any field's precision dropping beyond noise means revert, even if micro F1 rose.
4. **Track cost per document** for every variant: input and output tokens, calls per doc, and currency at a dated price sheet.
5. **Plot the frontier.** x = cost per 1,000 documents, y = macro F1 (with CI bars). Mark the dominated points. A point is dominated if another is both cheaper and better beyond noise.
6. **Choose a point against a budget.** For example: "≤ $X per 1,000 docs, macro F1 ≥ 0.9, no field below 0.8 precision". Write the budget down *before* you plot.
7. **Stretch: automate.** Write a small search loop that proposes the next rewrite from the error table and runs it. Keep a human approving each keep. The automated version is the same loop with the same rules; it does not get to edit `score.py`.

## Worked example: section chunking for `services_affected`
Before (one prompt, whole doc): the model sees "We initially suspected search…" and the runbook appendix listing other services. On the offline baseline, precision is 0.42.

After: route the field to the sections that define it, and tell the model why.

```python
import re

def sections(doc: str) -> dict[str, str]:
    """Split a markdown postmortem into {heading: body}. Text before the first ## goes under 'preamble'."""
    parts = re.split(r"^## +(.+)$", doc, flags=re.M)
    out = {"preamble": parts[0]}
    for head, body in zip(parts[1::2], parts[2::2]):
        out[head.strip().lower()] = body
    return out

SERVICES_PROMPT = """From the Impact section below, list the services that were affected
(had elevated errors or latency, or were named as affected). Return only JSON: {{"services_affected": [...]}}.
Do not include services that are only mentioned as suspected, investigated or unaffected.

<impact>
{impact}
</impact>"""

def extract_services(client, doc, model=None):
    s = sections(doc)
    impact = s.get("impact") or s.get("summary", "")
    resp = client.complete([{"role": "user", "content": SERVICES_PROMPT.format(impact=impact)}],
                           model=model, max_tokens=256, temperature=0)
    return (parse_json_object(resp.text) or {}).get("services_affected")
```

The decoy sentence lives in Summary, and the appendix is its own section, so neither reaches this call. The fallback to Summary when Impact is absent is a choice you must test: your own (non-generator) documents may not have an Impact heading at all.

What to log (illustrative output):

```markdown
| # | Change | Dev macro F1 (Δ, paired 95% CI) | services P / R | Test macro F1 | $/1k docs | Decision |
|---|---|---|---|---|---|---|
| 1 | v1 after M3 fixes | 0.81 | 0.71 / 0.97 | 0.79 | 2.10 | - |
| 2 | services from Impact section only | 0.86 (+0.05 [+0.02, +0.08]) | 0.95 / 0.93 | 0.85 | 1.60 | keep |
| 3 | timestamps by model, minutes by code | 0.90 (+0.04 [+0.01, +0.07]) | - | 0.89 | 1.70 | keep |
| 4 | gleaning pass on all fields | 0.91 (+0.01 [-0.01, +0.03]) | - | 0.89 | 3.30 | revert: within noise, 2x cost |
| 5 | cheaper model, same pipeline | 0.88 (-0.02 [-0.05, +0.00]) | - | 0.87 | 0.45 | frontier point; keep as option |
```

Row 5 is the interesting one: within noise of row 3 at about a quarter of the cost. Whether to pick it depends on the budget you wrote down in step 6, which is why you write it first.

## Deliverables
- EXPERIMENTS.md with noise check, ≥4 rounds (at least three distinct rewrite types from the table), reverts included
- The frontier plot with CIs and a stated budget
- The chosen pipeline, versioned, with its cassette

## Done when
- [ ] Each kept change has a paired bootstrap CI on dev that excludes zero, and test did not drop.
- [ ] Per-field precision is checked every round, not just micro F1.
- [ ] At least one model or effort comparison is on the frontier.
- [ ] The chosen point satisfies a budget written before the plot.

## Reuse
- `../code/score.py` (`paired_bootstrap`, `bootstrap_ci`), `../code/pipeline_v0.py`
- `ainative_kit.RecordingClient`/`ReplayClient` to avoid paying twice for unchanged stages
- Noise checks, revert rules, cost frontier, model-upgrade drill: [12-hill-climbing](../../12-hill-climbing/README.md)
- Chunking and context minimization: [03-context-engineering](../../03-context-engineering/README.md)

## Pitfalls
- **Copying failing documents into the prompt as examples.** It raises dev and does not transfer; it is the overfitting pattern Anthropic's hill-climbing write-up warns about ([post](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). Examples, if any, come from a separate pool.
- **Chunking that drops the fact.** Routing a field to one section fails when the fact is elsewhere (impact start in a prose paragraph). Measure recall per hard feature after every chunking change.
- **Comparing variants on different cassettes.** If one variant replays and another hits the live API on a different day, you are measuring drift too.
