# Capstone grading rubric

Four levels per milestone. Grade yourself, then have someone else (or a clean-context reviewer agent with only this file and your evidence pack) grade you. Disagreements are the interesting part.

| Level | Meaning |
|---|---|
| **0: Missing** | Deliverable absent, or present but cannot be run or reproduced |
| **1: Works** | Deliverable exists and runs; claims are qualitative |
| **2: Measured** | Claims backed by numbers from the eval with sample sizes; reproducible from a command in the README |
| **3: Rigorous** | Numbers have error bars or calibration stats; failure cases are explained; a skeptic could not easily poke a hole in it |

**Passing the capstone:** level 2 or above on every milestone of one variant, and level 3 on at least three of them. **Distinction:** level 3 on every milestone, or both variants passed.

**Automatic fail conditions** (any variant):
- The system can edit its own grader, labels or test split, and nothing prevents or detects it.
- A reported improvement is computed on the same split that was used to choose it.
- (A) The final agent takes a dangerous action or follows an injected instruction on any case in the regression suite, and the readiness review does not report it.

---

## Variant A: ops agent

### A-M1: Spec and harness
| Level | Criteria |
|---|---|
| 1 | SPEC.md and AGENTS.md exist; tools listed |
| 2 | Every tool is classified read / mutate / escalate with an authority rule; INVARIANTS.md lists at least 6 invariants, each mapped to a grader check or marked "not yet checkable" |
| 3 | Each invariant has a test that fails when it is violated ("prove the oracle can fail"); the spec states the autonomy level per action class and the evidence needed to raise it |

### A-M2: Agent loop with tools and governors
| Level | Criteria |
|---|---|
| 1 | Agent completes episodes against the simulator with a real model |
| 2 | Governors for steps, tokens, repeats and wall-clock (or simulated time); stop reasons recorded per run; tool errors are actionable; offline tests for each governor |
| 3 | Governor thresholds justified from observed distributions (for example p95 steps on passing runs); stall detection beyond identical repeats; a cost-per-episode number |

### A-M3: Tracing and error analysis
| Level | Criteria |
|---|---|
| 1 | Traces collected; some failures described |
| 2 | ≥50 traces read; open codes then axial categories with counts; a transition failure matrix |
| 3 | Taxonomy prioritized by frequency × severity; at least one category traced to a harness or grader bug rather than the model; categories each become an eval case or a check |

### A-M4: Eval suite
| Level | Criteria |
|---|---|
| 1 | Code graders run on the suite |
| 2 | Suite split train/test; capability vs regression cases separated; pass rate with CI; pass^k for k ≥ 3; correct/abstain/wrong reported; judge for summary quality with a binary rubric |
| 3 | Judge calibrated on ≥100 human labels with TPR and TNR on a held-out split; corrected pass-rate estimate; grader bugs found and fixed, with before/after |

### A-M5: Hill-climb with error bars
| Level | Criteria |
|---|---|
| 1 | Some changes tried, final score better than first |
| 2 | Noise check before round 1; experiment log with one change per row, train and test scores, keep/revert decision; at least 4 rounds |
| 3 | Paired comparisons with CIs; revert rule applied at least once and explained; at least one non-prompt dimension (model, effort, tool design); cost per passing episode tracked; final claim stated with CI on the untouched test split |

### A-M6: Guardrails
| Level | Criteria |
|---|---|
| 1 | Some blocking of dangerous actions |
| 2 | Lethal-trifecta audit table; deterministic pre-tool-use gate for dangerous actions; injection suite of ≥10 variants; injection-success and dangerous-action rates reported |
| 3 | Both rates at 0 on the suite; false-block rate on legitimate fixes measured and reported; at least one structural defense (plan-then-execute, dual LLM, context minimization), not only a filter; each red-team finding became a regression test |

### A-M7: Scheduled / ambient loop with inbox
| Level | Criteria |
|---|---|
| 1 | Agent runs on a schedule against a stream of incidents |
| 2 | Inbox with notify / question / review items; idempotent mutations (re-running a tick causes no duplicate action); per-run and per-day budgets; bookmark rather than time window |
| 3 | Crash-and-resume test proving no lost or duplicated work; staleness re-check before acting; inbox items assert or drop status, never hedge |

### A-M8: Production readiness review
| Level | Criteria |
|---|---|
| 1 | A document describing the system |
| 2 | SLIs and SLO targets with current measured values; staged rollout plan with entry/exit criteria per stage; rollback triggers |
| 3 | Autonomy decision per action class tied to measured evidence; known failure modes and residual risk stated honestly; model-upgrade drill described; a reviewer could approve or reject from the doc alone |

---

## Variant B: LLM data pipeline

### B-M1: Pipeline v0
| Level | Criteria |
|---|---|
| 1 | Pipeline runs over all docs with a real model and writes predictions |
| 2 | Map and reduce stages separated; parse failures recorded, not raised; token counts per doc; run is reproducible from one command |
| 3 | Labeling guide written before looking at outputs, with a definition for every field; traces per doc |

### B-M2: Labels and metrics
| Level | Criteria |
|---|---|
| 1 | Scorer reports overall accuracy |
| 2 | Field-level precision and recall; counting rules documented; ≥40 labeled docs (20 provided plus your own) with at least 10 not from the generator |
| 3 | Double-labeled subset with inter-annotator agreement; bootstrap CIs on micro F1; property tests on the scorer |

### B-M3: Error analysis
| Level | Criteria |
|---|---|
| 1 | Some errors listed |
| 2 | Every error on the dev split categorized (spec gap, extraction miss, hallucinated value, normalization, label error); counts per field and per hard feature |
| 3 | Label errors fixed and logged; at least one "model error" reclassified as a spec gap with the spec fixed; prioritized plan for M4 |

### B-M4: Hill-climb
| Level | Criteria |
|---|---|
| 1 | A better pipeline exists |
| 2 | Experiment log; at least three of: prompt decomposition, chunking, gleaning/self-check, model choice, effort; train/test split respected |
| 3 | Accuracy/cost frontier plotted with CIs; paired bootstrap for each kept change; the chosen point justified against a stated budget |

### B-M5: Judge for free-text fields
| Level | Criteria |
|---|---|
| 1 | A judge prompt scores summaries |
| 2 | Binary rubric per criterion; judge model differs from the pipeline model; TPR/TNR on held-out human labels |
| 3 | ≥100 labels; bias checks (length, position in pairwise); judge drift check after a pipeline change |

### B-M6: CI gate and drift monitoring
| Level | Criteria |
|---|---|
| 1 | Eval runs in CI |
| 2 | Gate fails on a statistically meaningful regression per field, not on noise; cost gate; drift monitor on unlabeled production docs |
| 3 | Gate tested with a seeded regression that it catches and a no-op change that it passes; drift alarm tested with a shifted document batch; runbook for what to do when it fires |
