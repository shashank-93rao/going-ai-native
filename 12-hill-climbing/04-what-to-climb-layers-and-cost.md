# 04: What to climb: layers, cost, and the model-upgrade drill

## The idea

An LLM system has several surfaces you can change, and they differ in what a change costs to make, costs to run, and costs to maintain:

| Layer | Examples | Change cost | Run cost | Maintenance and decay |
|---|---|---|---|---|
| **Prompt** | Definitions, rules, output format, tie-breaks | Minutes | Input tokens, mostly cacheable | Advice expires as models change |
| **Tools** | A lookup over the service catalog; better tool descriptions | Hours | Extra calls and latency | Owned code; the API contract has to stay stable |
| **Harness** | Verification pass, retry on parse failure, context assembly, routing | Days | Extra calls; complexity | Encodes a model weakness, so it decays on upgrade |
| **Model / effort** | Haiku, Sonnet, Opus; low to max effort | A config line | Large, multiplicative | Re-tune on every release |
| **Weights** | Fine-tuning, distillation | Weeks | Hosting and training | A new model means a new training run |

Two principles organize the climb. **Route each fix to the cheapest layer that can hold it.** Hamel Husain and Shreya Shankar teach the order prompt, then tool design, then harness, then model and weights, with weights "only when prompt search is flat" ([Maven, AI Evals for Engineers & PMs](https://maven.com/parlance-labs/evals), syllabus L8/L9). And **treat model and effort as dimensions of the search, not constants.** Then you are not climbing a single number. You are mapping an **accuracy-versus-cost frontier** and choosing a point on it.

## Why it matters

- Anthropic's support-bot climb ended on a *smaller* model at *low* effort, scoring 90.5% held-out against 78.6% originally, at about one fifth of the cost ([Lance Martin, "Automating eval design and hillclimbing with Claude"](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)). The win came from the cost axis as much as the accuracy axis.
- LangChain took its deep agent from 52.8% to 66.5% on Terminal-Bench 2.0 with the model held fixed, by harness changes alone. Running at xhigh effort everywhere scored *worse* than their "reasoning sandwich" (53.9% vs 63.6%) because of timeouts ([Vivek Trivedy, "Improving Deep Agents with harness engineering"](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)).
- Block's Bradley Axen, in an Anthropic customer story, describes benchmarking every model at every effort level per use case: "Fable on low might just be better than another model on xhigh" ([Anthropic customer story](https://claude.com/resources/articles/how-block-orchestrates-claude-fable-across-thousands-of-pull-requests)).
- Anthropic's Opus 5 prompting guide says to use effort as the primary cost lever, to re-run an effort sweep on your own evals when you change models, and to remove explicit verification instructions, which cause "over-verification" on that model ([Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)). Harness and prompt scaffolding written for an older model can become dead weight, or actively harmful.

## How it works

### Route the fix by failure type

| Failure pattern from error analysis | Cheapest layer that can hold the fix | Router example |
|---|---|---|
| Ambiguous or under-specified instruction | Prompt | "Route to the owner of the broken resource, not the symptom" (v2) |
| A rule the model could follow but wasn't told | Prompt | Earliest-timestamp tie-break (v4) |
| Missing knowledge the model cannot have | Tool | `lookup_owner(service)` over the catalog (v5) |
| Format and parse failures | Harness (structured output, validator, retry) | Parse `team:` strictly; retry once on a parse miss |
| Multi-step inference the model gets wrong at current effort | Effort, then model | Effort `high` for multi-signal alerts (v6b) |
| Consistently wrong on a class even at max effort | Model, or reconsider the task spec | (none here) |

OpenAI's receipt-inspection cookbook orders it differently: model selection first, then prompt, examples, tools, accessory models, and fine-tuning ([OpenAI cookbook](https://developers.openai.com/cookbook/examples/partners/eval_driven_system_design/receipt_inspection)).

> **Synthesis.** These don't conflict once you separate *running* a change from *owning* one. A model-and-effort sweep is cheap to run, so do one early to learn where the headroom is. *Fixes* still go to the cheapest layer to own. Never paper over a missing-knowledge failure with a bigger model: the tool fixes it for every model, and the bigger model fixes it only some of the time, at a recurring cost.

### Effort as a dimension

On current Claude models, effort is a request parameter: `output_config={"effort": "low" | "medium" | "high" | "xhigh" | "max"}`, with adaptive thinking. Defaults differ by model. As of the claude-api skill's model table cached 2026-10-06, Sonnet 5.5 defaults to `high` and Opus 5.5 to `medium`, so set it explicitly in every config you compare. (`ainative_kit`'s client does not forward effort. `code/README.md` shows a small subclass that does.) Sweep effort as one round with several candidates (concept 01). Expect a peak: more effort helps multi-step inference until the extra tokens start costing you truncations or latency-budget misses. In the simulated router, `max` lost 4 points to `max_tokens` truncations.

### The Pareto frontier

Hold the prompt, tools, harness, and dataset fixed, and vary model × effort. A config is **on the frontier** if no other config is at least as accurate *and* at least as cheap. Means alone over-trust the frontier, so `pareto.py` also tests every step along it with a *paired, clustered* difference against the next-cheaper frontier point. A step whose CI spans 0 is "not distinguishable": you would be paying for noise.

Then pick a point on it with a **cost model**, not by eye. OpenAI's cookbook converts eval errors into dollars because "not all evals matter". For an incident router, a misroute costs on-call minutes and time-to-mitigate, which dwarf token costs.

### The model-upgrade drill

From Hamel and Shreya's L9: keep frontier variants as configs, re-run the suite when a new model ships, redraw the frontier, then decide. Add the ablation step from Anthropic's April 2026 postmortem, which recommends line-by-line ablations for system-prompt changes ([Anthropic, "An update on recent Claude Code quality reports"](https://www.anthropic.com/engineering/april-23-postmortem)):

1. Re-run every frontier config with the new model (same prompts, same tools).
2. Redraw the frontier with old and new points together.
3. On the most promising new point, **ablate**: remove each prompt section, tool, and harness step one at a time, and measure the paired change.
4. Delete components whose removal costs nothing measurable. They encoded a weakness the new model no longer has.
5. Re-run the CI gate against the new baseline before you switch traffic.

## Worked example

### The frontier for the climbed router

```bash
python pareto.py --drill candidate-model-x
```

This is simulated output on dev (491 alerts, 3 repeats). The config is the climbed prompt, tools, and harness; only model and effort vary. Prices are list prices as cached on 2026-10-06, applied to simulated token counts:

| config | $/1k alerts | accuracy [95% CI] | frontier | gain over next-cheaper frontier point |
|---|---|---|---|---|
| haiku-5-5/low | 0.07 | 77.5 [73.0, 82.1] | yes | |
| haiku-5-5/medium | 0.18 | 80.9 [77.1, 84.7] | yes | +3.3 [1.2, 5.4]: real |
| haiku-5-5/high | 0.43 | 84.5 [81.4, 87.5] | yes | +3.6 [0.8, 6.4]: real |
| sonnet-5-5/low | 1.43 | 82.9 [78.7, 87.1] | | |
| opus-5-5/low | 2.86 | 85.6 [81.5, 89.7] | yes | +1.2 [-2.6, 4.9]: not distinguishable |
| sonnet-5-5/medium | 3.55 | 86.8 [83.4, 90.3] | yes | +1.2 [-0.6, 3.1]: not distinguishable |
| opus-5-5/medium | 7.10 | 87.5 [84.2, 90.8] | yes | +0.7 [-0.7, 2.1]: not distinguishable |
| sonnet-5-5/high | 8.58 | 89.2 [86.6, 91.9] | yes | +1.7 [-1.0, 4.4]: not distinguishable |
| opus-5-5/high | 17.17 | 91.2 [88.9, 93.5] | yes | +2.0 [0.5, 3.4]: real |

The simulator's model deltas are made up for teaching. Read the *method*, not the ranking.

**Bad decision:** "Sonnet/high is the climbed config, it's on the frontier, ship it." Or the opposite: "Haiku/high is 20x cheaper per alert and only 4.7 points worse, ship that."

**Good decision:** put a price on the error. Suppose a misrouted page costs about 20 minutes of a second engineer's time plus delayed mitigation, and call it $50. That is a hypothetical: use your own incident data. Then the expected cost per 1,000 alerts is:

| config | API $ | misroutes per 1k | misroute $ | total |
|---|---|---|---|---|
| haiku-5-5/high | 0.43 | 155 | 7,750 | **7,750** |
| sonnet-5-5/high | 8.58 | 108 | 5,400 | **5,409** |
| opus-5-5/high | 17.17 | 88 | 4,400 | **4,417** |

For a pager router, the token bill is a rounding error and accuracy is everything. Opus/high is the only step above Sonnet/high that the paired test calls real, and it pays for itself many times over. For a high-volume, low-stakes task (tagging log lines, say) the same table flips toward Haiku. The frontier tells you what you *can* buy, and the cost model tells you what to buy.

### The upgrade drill

Now a new model ships. In the simulator this is `candidate-model-x`, a placeholder with made-up behavior: better at multi-signal inference at low effort, and able to resolve alert chains without being told the rule. Re-run the frontier configs on it:

| frontier config | old acc | new acc | paired gain [95% CI] | old $/1k | new $/1k |
|---|---|---|---|---|---|
| haiku-5-5/low | 77.5 | 89.5 | +11.9 [8.4, 15.4] | 0.07 | 0.71 |
| sonnet-5-5/medium | 86.8 | 90.2 | +3.4 [1.0, 5.8] | 3.55 | 1.78 |
| sonnet-5-5/high | 89.2 | 89.7 | +0.5 [-0.7, 1.6] | 8.58 | 4.29 |
| opus-5-5/high | 91.2 | 90.8 | -0.3 [-1.5, 0.8] | 17.17 | 4.29 |

(Abridged. Several old configs map to the same new `candidate/<effort>` config. The 89.5 vs 88.2 spread you see for `candidate/low` in the full output is run-to-run noise on identical configs, a useful reminder.)

Then ablate on `candidate/low`:

| removed | paired change [95% CI] | verdict |
|---|---|---|
| section: queue_definitions | -9.1 [-12.5, -5.7] | still load-bearing |
| section: tiebreak | -0.5 [-1.8, 0.8] | no measurable value: delete |
| tool: lookup_owner | -6.0 [-9.3, -2.7] | still load-bearing |

The tie-break rule, a hard-won kept change from round 4, is dead weight on the new model. The tool and the queue definitions are not, as you would expect: the model can't know your service catalog, and "owner of the broken resource" is *your* policy, not world knowledge. That pattern generalizes. **Knowledge and policy survive upgrades; workarounds for reasoning weaknesses don't.**

The final check is candidate/low without the tie-break section against the current production config (sonnet/high), paired on test: **−0.8 [−2.1, 0.6]** at **$0.64 vs $8.58** per thousand alerts (simulated). The accuracy is statistically indistinguishable, at about one thirteenth of the API cost. Given the cost model above, you would still check whether candidate at `high` buys real accuracy before you take the cheap point. That is one more round of the same loop.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Fixing missing knowledge with a bigger model | The failure family is "unknown entity", yet the fix is a model swap; accuracy on it plateaus well below 100% |
| Comparing models at their *default* effort | Configs without an explicit `effort`; defaults differ by model |
| Reading the frontier off point estimates | No paired test per frontier step; adjacent points with overlapping CIs treated as different |
| Choosing a point without a cost model | Decision memo says "best trade-off" with no dollars per error |
| Swapping the model without re-running the climb's guards | No ablation; scaffolding count only ever grows |
| Effort `max` everywhere | Truncation or timeout counters rise; accuracy falls on the slice with long reasoning |
| Treating price as fixed | Prices hard-coded with no date; re-check the pricing page on every drill |

## In your day job
- Keep every frontier config as a committed file (`configs/haiku-high.json`, ...) so the upgrade drill is one command, not an archaeology project.
- Write the misroute (or error) cost into the eval README. It turns "which model?" debates into arithmetic.
- On every model release, run the drill and the ablation. Open a PR that *deletes* the components the ablation calls dead weight. That is the harness-decay thread from [Module 08](../08-harness-engineering/README.md).
- Route missing-knowledge failures to tools first. The tool fix is model-independent and survives every upgrade.
