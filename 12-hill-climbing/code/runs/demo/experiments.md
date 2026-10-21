# Experiment log: incident-router hill-climb

- evaluator fingerprint: `11d8d01305ec2280` (grader + dataset, checked every round)
- dev: 491 alerts in 161 incidents; test: 478 alerts in 159 incidents
- repeats per variant: 4; base seed 1; fresh seeds per evaluation
- deltas are paired against the CURRENT BEST, with incident-clustered 95% CIs, in points
- cost column is $ per 1k alerts at the list prices in incident_router.py (simulated token counts)

## Noise check (baseline, before round 1)

| metric | value |
|---|---|
| runs x items | 6 x 491 |
| run accuracies | 68.8, 69.2, 69.5, 70.1, 70.7, 69.2 |
| SD of run accuracy | 0.7 pts |
| items that flipped across runs | 19.1% |
| SE of one run: naive / clustered | 2.1 / 2.6 pts |
| null paired diff (same config, two halves) | 0.8 pts |
| paired SE at 4 repeats | 0.6 pts |
| minimum detectable effect (80% power) | 1.7 pts |
| smallest effect you'd act on | 5.0 pts |

**Verdict:** OK: the eval can resolve the smallest effect you'd act on.

## Rounds

| # | variant | change | dev % | Δdev [95% CI] | test % | Δtest [95% CI] | $/1k | decision | reason |
|---|---|---|---|---|---|---|---|---|---|
| 0 | v0-baseline | `baseline` | 69.6 | - | 67.9 | - | 2.66 | **baseline** | starting point |
| 1 | v1-step-by-step | `{"add_section": "step_by_step"}` | 69.9 | 0.3 [-1.3, 1.8] | 67.4 | -0.5 [-2.0, 0.9] | 4.18 | **revert** | dev change within noise (CI spans 0); simpler config wins ties |
| 2 | v2-queue-defs | `{"add_section": "queue_definitions"}` | 77.5 | 7.9 [4.5, 11.4] | 74.6 | 6.7 [3.9, 9.5] | 3.03 | **keep** | dev up (significant), test up (significant) |
| 3 | v3-fewshot-failures | `{"paste_dev_failures": 60}` | 86.4 | 8.8 [4.5, 13.1] | 72.5 | -2.0 [-3.4, -0.6] | 6.25 | **revert** | dev up but test significantly DOWN: overfit to dev; WARNING 60 eval items pasted into prompt |
| 4 | v4-tiebreak | `{"add_section": "tiebreak"}` | 79.8 | 2.2 [0.3, 4.2] | 78.8 | 4.2 [1.4, 7.0] | 3.16 | **keep** | dev up (significant), test up (significant) |
| 5 | v5-owner-tool | `{"add_tool": "lookup_owner"}` | 85.2 | 5.4 [2.1, 8.7] | 85.1 | 6.3 [2.8, 9.7] | 3.55 | **keep** | dev up (significant), test up (significant) |
| 6 | v6a-effort-low | `{"set": {"effort": "low"}}` | 82.9 | -2.2 [-4.0, -0.5] | 82.2 | -2.9 [-4.5, -1.4] | 1.43 | **revert** | dev regression (CI below 0) |
| 6 | v6b-effort-high | `{"set": {"effort": "high"}}` | 89.1 | 3.9 [1.3, 6.5] | 89.1 | 4.0 [1.2, 6.7] | 8.58 | **keep** | dev up (significant), test up (significant) |
| 6 | v6c-effort-xhigh | `{"set": {"effort": "xhigh"}}` | 88.6 | 3.4 [0.9, 5.9] | 90.0 | 4.9 [2.0, 7.8] | 14.17 | **revert** | passed rules but lost the sweep to v6b-effort-high |
| 6 | v6d-effort-max | `{"set": {"effort": "max"}}` | 81.1 | -4.1 [-7.1, -1.0] | 79.3 | -5.8 [-9.2, -2.5] | 22.90 | **revert** | dev regression (CI below 0) |

## Hypotheses and error analysis

- **v1-step-by-step**: Generic reasoning boilerplate helps everywhere. (No error-analysis evidence; included because someone always proposes it.)
- **v2-queue-defs**: Error analysis: most ambiguous-owner alerts go to the team whose service shows the symptom (payments-api pool exhaustion -> payments). Define queues by owned resource.
- **v3-fewshot-failures**: Paste 60 current dev failures with their correct labels as few-shot examples. (The anti-pattern: block_leaks is off for this demo.)
- **v4-tiebreak**: Error analysis: multi-component alert chains are routed to the first component LISTED, not the earliest failing. Add an explicit timestamp tie-break rule.
- **v5-owner-tool**: Error analysis: codename services (svc-orion, svc-vega) are guessed. No prompt can fix missing knowledge; give the model a lookup_owner tool over the service catalog.
- **v6a-effort-low**: Effort sweep: low. Cheaper; does accuracy hold?
- **v6b-effort-high**: Effort sweep: high. Remaining failures are multi-signal alerts that need inference.
- **v6c-effort-xhigh**: Effort sweep: xhigh. If high helps, does xhigh help more?
- **v6d-effort-max**: Effort sweep: max. The top of the range.

Dev accuracy by failure family for the final best config:

- ambiguous: 87%
- easy: 90%
- lookup: 91%
- reasoning: 88%
- tiebreak: 88%

## Result

- best config: `v6b-effort-high`
- test accuracy: baseline 67.9 [62.7, 73.1] -> best 89.1 [86.6, 91.6]
- paired test gain: 21.2 [16.5, 25.8] points (incident-clustered)
- verdict: ship it
