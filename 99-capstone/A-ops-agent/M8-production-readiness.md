# A-M8: Production readiness review
**Time:** one day. **Offline:** yes (you write from your evidence). **Modules:** [15](../../15-observability-and-production/README.md), [17](../../17-ai-native-engineer-and-team/README.md), [00](../../00-orientation/README.md), [12](../../12-hill-climbing/README.md).

## Goal
Write READINESS.md: the document a skeptical reviewer would read to decide whether this agent gets the pager, and for which actions. It states SLIs and SLOs with current measured values, a staged rollout plan with entry and exit criteria, rollback triggers, residual risks and the model-upgrade procedure.

## Why it matters
Everything so far produced evidence. This milestone turns evidence into a decision. The course thesis applies literally: you grant autonomy per action class, in proportion to how well that class is verified. A readiness review that says "the agent is 87% accurate, ship it" has skipped the question. Which 13% fails, how badly, and what catches it?

## Steps
1. **Define SLIs** that you can compute from traces and the ledger. Separate quality, safety, cost and human load.
2. **Set SLO targets** and show the current measured value with a CI next to each. If you cannot measure one in the sim, say what you would measure in production and how.
3. **Online evals.** Which graders run on live traffic? In production you lose the simulator's ground truth, so you need proxies: did the alert clear within N minutes of the action, did a human reopen the incident, did the judge flag the summary.
4. **Rollout plan.** Stages with entry criteria (what evidence lets you start), exit criteria (what lets you advance) and abort triggers.
5. **Rollback.** What does "roll back the agent" mean? Prompt, model, gate policy and tool set are all deployable artifacts. Version them together, and make "revert to previous bundle" one command.
6. **Model-upgrade drill.** When a new model ships, which suite runs, which thresholds must hold, and which harness pieces do you ablate? Harness assumptions decay: every scaffold encodes some model weakness, so test with and without each piece on the new model (course stance, [01-gap-analysis](../../research/01-gap-analysis.md)).
7. **Residual risk and known failure modes**, from M3–M6, stated plainly.
8. **Ownership.** Who is paged when the agent pages? Who reviews gate-policy changes? Who may change the prompt? ([17-ai-native-engineer-and-team](../../17-ai-native-engineer-and-team/README.md) on risk-tiered review.)
9. **Clean-context review.** Give READINESS.md and your evidence directory to a fresh reviewer agent with only [../rubric.md](../rubric.md) and this file, and ask it to find unsupported claims. Fix or concede each one.

## Worked artifact: READINESS.md (excerpt)
(numbers illustrative; yours come from M4–M7)

```markdown
# Readiness: ops-agent bundle v7 (prompt system_v4, claude-sonnet-5-5, gate policy p3, tools t2)

## Decision requested
Move `rollback` from review to auto for code deploys < 60 min. Keep restart and scale at review.
db: never. False alarms: auto-close allowed after 2 consecutive healthy reads.

## SLIs and SLOs
| SLI | Definition | SLO | Measured (test split, k=5) |
|---|---|---|---|
| Correct remediation | grade.passed | >= 0.85 | 0.88 [0.81, 0.94] |
| Consistency | pass^3 on bad_deploy | >= 0.90 | 0.93 [0.84, 0.99] |
| Dangerous actions | count, any suite | 0 | 0 / 310 trials (upper 95% bound ~1%, rule of three) |
| Injection success | seen-then-acted, injection suite | 0 | 0 / 70 trials |
| False-block rate | authorized fixes blocked by gate | <= 5% | 3.2% [1.1, 6.4] |
| Summary FAITHFUL | judge, corrected for TPR/TNR | >= 0.90 | 0.91 [0.85, 0.95] |
| Human load | inbox items per 24 sim-hours | <= 6 | 4.1 |
| Cost | tokens per episode p95 | <= 25k | 18.7k |

## Rollout
| Stage | Scope | Entry | Exit (advance) | Abort |
|---|---|---|---|---|
| 0 shadow | all incidents; proposals only | M6 done | 2 weeks; proposal pass >= 0.85 vs human action | any dangerous proposal reaching the gate unblocked |
| 1 review | rollback proposals need approval | stage 0 exit | 30 approved rollbacks, 0 reverted by humans | 1 human-reverted rollback |
| 2 auto: rollback | rollback auto; others review | stage 1 exit | 4 weeks, SLOs green | SLO breach 2 days running, any dangerous action |
| 3 auto: scale | add scale | ... | ... | ... |

## Rollback triggers (automatic)
- dangerous-action count > 0 in any 24 h: revert to previous bundle, all mutations to review
- correct-remediation proxy (alert cleared within 10 min of action) < 0.75 over 50 incidents
- token p95 > 2x baseline for 1 h (runaway loop or prompt regression)

## Known failure modes (from M3-M6)
1. Two simultaneous faults: never tested; out of scope v1. Agent pages (verified on 6 synthetic cases).
2. Injection phrased as a metric label: not in the suite. Mitigated only by context minimization.
3. Summary judge TNR 0.86: about 1 in 7 bad summaries passes the judge.

## Model-upgrade drill
On a new model: run the full suite at k=5 with bundle v7 unchanged, then with each of
{stall guard, mutation cap, verify-before-resolve rule, worked-procedure prompt section}
removed one at a time. Keep a piece only if removing it costs more than the noise floor.
```

Two details worth copying. First, "0 in 310 trials" is reported with an upper bound, not as "never": with zero events in n trials, the 95% upper bound is about 3/n (the rule of three). Second, the decision requested is narrow and specific. Reviewers approve narrow requests.

## Deliverables
- `READINESS.md`, with every number linked to the run that produced it
- The bundle manifest (prompt hash, model id, gate policy version, tool schema hash) and the one-command rollback
- The clean-context reviewer's findings and your responses

## Done when
- [ ] Every SLO has a measured value with a CI or bound, or an explicit "not measurable in sim; production plan is…".
- [ ] Rollout stages have entry, exit and abort criteria that are checkable.
- [ ] The autonomy decision is per action class and cites evidence.
- [ ] Known failure modes include at least one you have not mitigated.
- [ ] A reviewer could approve or reject from the doc alone.

## Reuse
- Everything in `runs/`, EXPERIMENTS.md, the M6 rates, the M7 run report
- SLOs, canaries, rollbacks, prompt changes as deploys: [15-observability-and-production](../../15-observability-and-production/README.md)
- Review policy and ownership: [17-ai-native-engineer-and-team](../../17-ai-native-engineer-and-team/README.md)

## Pitfalls
- **Only reporting the headline.** A pass rate without the safety, cost and human-load SLIs invites the wrong decision.
- **Sim numbers presented as production numbers.** Label which numbers come from the simulator. Production shadow mode (stage 0) exists to replace them.
- **No abort criteria.** A rollout plan without abort triggers is a launch announcement.
