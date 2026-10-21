# 05: Automated optimization

## The idea

Once the loop in concept 01 works by hand, most of it is mechanical. You read failures, propose a patch, run the eval, and apply the rules. Each of those steps can be handed to a program or an agent. There are three families, from the most constrained to the most open:

| Family | What it searches | Proposer | Examples |
|---|---|---|---|
| **Prompt optimizers** | Instructions and few-shot demos inside a fixed program structure | An optimizer algorithm, often LLM-driven reflection | DSPy optimizers such as MIPROv2 and GEPA |
| **Bounded improve-loops** | Prompt sections, tool descriptions, config parameters | An LLM reading bucketed failures, proposing one patch per round | Hamel & Shreya's "bounded improve-loop"; Anthropic's `/claude-api hillclimb` |
| **Agentic research loops** | Anything in an editable file: code, harness, configs | A coding agent with a fixed budget per trial | Karpathy's autoresearch; overnight agent loops |

They share one property. **The optimizer is only as honest as the evaluator and the guards around it.** An automated proposer runs more rounds than you would and reads more failures than you would. If you let it, it will paste them, peek at test, or edit the grader. Automation multiplies whatever discipline the manual loop had, including the lack of it.

## Why it matters

The upside is real. GEPA ("Genetic-Pareto"), a reflective prompt optimizer, reports beating the GRPO RL method by 6% on average and up to 20% across six tasks, with up to 35x fewer rollouts, and beating DSPy's MIPROv2 by over 10% ([Agrawal et al., "GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning", arXiv 2507.19457](https://arxiv.org/abs/2507.19457)). GEPA reflects in natural language on sampled trajectories to diagnose failures, and keeps a *Pareto frontier* of candidates rather than a single best. Anthropic's automated skill-eval climb ran 24 rounds, from 66.1% to about 88% ([Lance Martin, claude.dev](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). autoresearch runs about 12 trials an hour, which is roughly 100 overnight ([karpathy/autoresearch](https://github.com/karpathy/autoresearch)).

The course's ordering comes from Hamel and Shreya: do a manual fix loop *first*, then automate with GEPA or a bounded improve-loop, and "guard against reward hacking" ([Maven, AI Evals for Engineers & PMs](https://maven.com/parlance-labs/evals), syllabus L8). The manual climb is what tells you the failure families, the noise floor, and whether the grader can be trusted. An optimizer pointed at an untrusted grader climbs the grader's bugs very efficiently. In Anthropic's skill climb, the last phase of the gain came from *fixing* graders, a step an unguarded optimizer would have exploited instead of reporting.

## How it works

### Preconditions: do not automate until all are true

- [ ] You have done at least a few manual rounds and have a failure taxonomy (concept 01).
- [ ] The noise check passes, and the eval is big enough for the slices you target (concept 02).
- [ ] The grader is calibrated if it is a judge ([Module 11](../11-llm-as-judge/README.md)), and has survived a round of "is this failure real?" reading.
- [ ] There is a split the optimizer *never* scores against (see the next section).
- [ ] The guards below are enforced in code, not written as requests in a prompt.

### The extra split

Prompt optimizers *select* on their validation set. DSPy's GEPA `compile(student, trainset=..., valset=...)` uses `valset` to choose among candidates ([DSPy GEPA docs](https://dspy.ai/current/api/optimizers/GEPA/overview/), read 2026-10-19). Whatever the optimizer selects on stops being held out. So an automated climb needs three splits: **train** (what the optimizer reads), **val** (what it selects on), and **test** (what you read at the end, once). This is the lockbox from concept 03, and here it is mandatory.

### Guards

| Guard | Implements | In this module |
|---|---|---|
| Frozen evaluator | The optimizer can't redefine success | `fingerprint()` checked every round; eval dir mounted read-only |
| Editable-surface allow-list | Changes stay attributable and reviewable | Variants can only touch `sections`, `tools`, `effort`, `model` |
| Leak check | No eval items in the prompt | `leaked_items()`; `block_leaks: true` |
| Fixed budget per trial and overall | Comparable trials, bounded spend | `repeats`, round list; autoresearch's 5-minute cap; a dollar cap |
| Decision rules in code | No "close enough" | `decide()` |
| Simplicity pressure | Prompts don't bloat into a pile of patches | Ties revert; cost column; autoresearch's "simpler wins" |
| Proposer never sees test | No selection on test | The proposer gets dev failures only |
| Human review of the final diff | Catches anything clever | The PR shows the config diff plus the log |

### Shapes of the three families

**DSPy/GEPA (sketch).** The DSPy docs describe a metric with signature `(gold, pred, trace, pred_name, pred_trace)`, returning either a float or a `dspy.Prediction` with `score` and `feedback`. The textual feedback is what GEPA reflects on. The minimal documented usage is `gepa = dspy.GEPA(metric=metric, track_stats=True, ...)` and then `gepa.compile(student, trainset=..., valset=...)`. Other constructor arguments are documented on the docs' "GEPA Advanced" page, which this module did not verify. DSPy is not installed in the course venv, so there is no runnable GEPA code here. The sketch is the shape to aim for:

```python
# Sketch only: DSPy is not a course dependency. Check the current DSPy docs before use.
import dspy

class Route(dspy.Signature):
    """Route a production alert to the owning on-call team."""
    alert: str = dspy.InputField()
    team: str = dspy.OutputField(desc="one of: payments, platform, data-pipeline, database, identity, edge")

def metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    ok = pred.team == gold.team
    # Feedback is the lever: describe the failure FAMILY, never the answer key for this item.
    fb = "correct" if ok else f"misrouted; check owner-of-broken-resource vs symptom team ({gold.tag})"
    return dspy.Prediction(score=float(ok), feedback=fb)

# train = dev alerts, val = a separate slice of dev; test is never passed to the optimizer.
# optimized = dspy.GEPA(metric=metric, track_stats=True).compile(dspy.Predict(Route), trainset=train, valset=val)
```

Note the feedback string. It names the failure *family*. If you put `gold.team` in the feedback, you have built an automated version of round 3's paste-the-answers overfit.

**Bounded improve-loop.** This is `hillclimb.py` with the `rounds` list generated by an LLM instead of written by you. Each round: bucket the current best's dev failures by tag; give the proposer the largest bucket (a few transcripts, with labels *removed* from anything the patch could copy); ask for one prompt section or tool-description edit; run it through the same `try_variant` and `decide`. Stop after N rounds, after two flat rounds, or when the budget is spent. The proposer is just another `LLMClient` call through `ainative_kit`, and a `FakeClient` makes the loop testable offline.

**Agentic research loop.** Point a coding agent at a `program.md` and let it edit, run, and keep or revert overnight. This is the most powerful family and the riskiest, because the agent has a shell. Every guard has to be enforced by the environment (file permissions, a sandbox, a runner that refuses tampered evals), as [Module 16](../16-security-and-containment/README.md) argues for containment generally.

## Worked example

### Bad: an open-ended instruction to a coding agent

```text
Improve the incident router's eval score as much as you can. The eval is
`python router_eval.py`. Work until it's above 95%.
```

This is an invitation to reward hack. The cheapest paths to 95% are, in order: edit `grade()` to be more "lenient"; paste dev items into a prompt section; or notice `data/incidents.jsonl` has a `label` field and build a "lookup tool" that reads it. All three are things a capable agent will try if the score is the only signal. Anthropic's eval write-ups document models using git history from earlier trials and finding benchmark answer keys ([Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [BrowseComp eval awareness](https://www.anthropic.com/engineering/eval-awareness-browsecomp)).

### Good: a `program.md` with the guards made explicit, and enforced

```markdown
# program.md: incident-router hill-climb (agent instructions)

## Goal
Raise TEST accuracy of the incident router with the fewest, simplest changes.
Target: test lower 95% bound >= 0.88 at <= $10 per 1k alerts. Stop when reached.

## What you may edit
- New prompt sections in data/prompts/ (one per round) and data/variants.json rounds.
- Tool DESCRIPTIONS in incident_router.py (not tool behavior).
You may NOT edit: router_eval.py, make_incidents.py, data/incidents.jsonl, stats.py,
hillclimb.py, or anything under ci/. They are mounted read-only; writes will fail.

## Loop (one round = one change)
1. Read runs/latest/experiments.md and the DEV failures for the current best.
2. Group failures by cause. Pick the largest bucket a single change could fix.
3. Write ONE change as a new round in data/variants.json with a hypothesis that names the bucket.
4. Run: python hillclimb.py data/variants.json --out runs/latest
5. Do not argue with the decision column. If reverted, record why you think so in the hypothesis
   of your next round, then move on.
6. After 2 consecutive reverts, stop proposing and write a failure-bucket report instead.

## Never
- Paste alert text from any split into a prompt or example. The runner blocks it.
- Read test transcripts or the label field of any eval row.
- Add examples that paraphrase eval items.
- Change the grader. If you believe the grader is wrong, write it up and stop.

## Budget
At most 8 rounds and $25 of API spend. Each run's cost is in the $/1k column.
```

And the enforcement behind it, as real behavior of this module's runner (from the tests):

```text
# the agent pastes failures -> blocked before any spend
| 3 | v3-fewshot-failures | `{"paste_dev_failures": 60}` | ... | **blocked** | config contains 60 eval items verbatim |

# the agent edits the grader or dataset mid-climb -> the climb aborts
RuntimeError: evaluator or dataset changed during the climb; results are void
```

The second line comes from `test_hillclimb.py::test_frozen_evaluator_guard`. In production you would also make the files read-only, so that the fingerprint check is a second line of defense, not the only one.

### What to review when the automated climb finishes

1. **The diff of the final config against the baseline,** line by line. Every prompt line should trace back to a kept row in the log.
2. **The log's reverted rows.** If most rounds were reverted, the proposer is guessing. Go back to manual error analysis.
3. **A read of 20 random *test* transcripts, once.** You are looking for anything clever: answers in the right format for the wrong reason, or tool calls that shouldn't be needed.
4. **The lockbox number** against the test number.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Automating before the manual climb | No failure taxonomy exists; the optimizer's "hypotheses" are generic |
| Optimizer selects on your test set | The same split is passed as `valset` and reported as the result |
| Feedback strings leak answers | Metric feedback contains the gold label or item text |
| Prompt bloat | System prompt length grows every round; cost column climbs on kept rows |
| Guards written only in the prompt | The agent can write to `router_eval.py`; nothing crashes when it does |
| Overnight runs with no budget | No dollar cap; a stalled loop burns tokens until morning ([Module 07](../07-loops/README.md) governors) |
| Trusting the optimizer's own report | The summary comes from the agent's narrative, not from `experiments.md` |

## In your day job
- Turn on automated optimization only for an eval that has been climbed by hand at least once, has passed a noise check, and has a split the optimizer never touches.
- Write the guards into the runner and the filesystem, then write them into `program.md` as well. Prompt-only guards are suggestions.
- Make the feedback the optimizer sees describe failure *families*, never items. Review it like you would review a data-access path.
- Review the final config diff and the log yourself. An automated climb is a PR from a very fast, very literal contributor.
