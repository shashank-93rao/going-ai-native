# 08: Harness engineering: agent-ready codebases
> After this module you can turn a service into one where a coding agent can build features, find problems and fix them on its own, and you can measure how often that actually happens.

## The question this module answers
*"Does harness engineering take care of building enough context around codebases that agents can independently code features, identify problems and come up with fixes?"*

**Short answer: context is one third of it, and "enough" is something you measure, not something you assert.**

- **Context (pillar 1, Understand)** lets the agent work out *what to change* and *what must not break*. That covers an architecture map, invariants, ADRs, a glossary, and nested AGENTS.md files.
- **Verification (pillar 2, Verify)** lets the agent tell, without you, whether the change is correct. Fast checks, lints that explain the fix, hermetic fakes and checkable "done" do that work.
- **Diagnosis (pillar 3, Diagnose)** lets the agent find problems nobody has pinned down yet. That needs queryable logs, metrics and traces, plus repro scripts and runbooks.
- **Measurement (the autonomy rate)** tells you whether the three pillars are enough *for your codebase and your model*. It is a seeded suite of features, bugs and incidents, graded by hidden tests.

A codebase with perfect docs and no verifiers gets you confident wrong answers. A codebase with great tests and no observability gets you features but no incident fixes. Agents act *independently* only where all three pillars exist **and** the autonomy rate says they work. Everywhere else, keep a human in the loop. That is the course thesis applied to a repo: **autonomy should scale with verifiability.**

What harness engineering does **not** cover:
- product judgment and ambiguous specs;
- novel architecture decisions;
- incidents whose evidence lives outside anything the agent can query;
- correctness properties nobody has written down as a check.

Those stay human until you make them checkable. [01-what-a-harness-is.md](01-what-a-harness-is.md) works through the full answer.

## Why this matters
OpenAI reports that a small team shipped roughly a million lines of agent-written code in about five months. They describe their main job as building the environment: the map, the lints, and the per-worktree observability ([OpenAI, "Harness engineering"](https://openai.com/index/harness-engineering/)). LangChain moved its coding agent from 52.8% to 66.5% on Terminal-Bench 2.0 by changing only the harness, with the model held fixed ([LangChain, "Improving Deep Agents with harness engineering"](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)). A 13.7-point gain from the harness alone is larger than most model-to-model gaps on that leaderboard.

Without a harness, an agent on your service does what a smart contractor would do on day one with no onboarding and no staging environment. It reads the code that is visible, pattern-matches, and declares success when the tests it can see pass. In a distributed system, that is exactly how you get these failures:
- a consumer that dedupes on partition offset;
- a relay that "keeps moving" past a failed publish;
- an idempotency hash that includes a timestamp.

All three pass unit tests, and all three are in this module's task suite.

The stakes are asymmetric. A feature that fails CI costs you a retry. A fix that passes CI but violates an invariant costs you an incident. Spotify calls a PR that passes CI but is functionally incorrect "the most serious error, as it erodes trust in our automation" ([Spotify Engineering, Honk part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). The harness exists to make that third outcome rare and detectable.

## The distributed-systems anchor
**Harness engineering is platform engineering, and the agent is your tenant.** You already know this from building paved roads:
- a service template with the right defaults;
- CI that fails with an actionable message;
- per-PR preview environments;
- dashboards that exist before the incident;
- an operability review before launch.

The paved-road question was always "can a new team ship safely without asking us?" Harness engineering asks the same question about an agent.

The table maps it out:

| Platform engineering | Harness engineering |
|---|---|
| Service template, golden path docs | AGENTS.md as a map, ARCHITECTURE.md, ADRs |
| Operability review / production readiness | INVARIANTS.md and the lints that enforce it |
| Preview environment per PR | Ephemeral environment per worktree |
| On-call runbook | Runbook as a skill the agent loads |
| Dashboards and log search | `diagnose.py`, LogQL/PromQL over CLI or MCP |
| DORA metrics | Autonomy rate on a seeded task suite |

**Where the analogy breaks:**
- **The agent reads everything literally and remembers nothing between sessions.** A human absorbs tribal knowledge over months. An agent has only what is in the repo, the tools and the context window. As OpenAI puts it, whatever it cannot access while running effectively does not exist.
- **The agent will optimize against your checks.** A new hire does not delete a failing test to get CI green. An agent sometimes will. Your verifiers therefore have to sit outside its reach, and you need hidden tests to grade it.
- **The tenant changes every few months.** A new model has different weaknesses, so some of your scaffolding becomes dead weight or actively harmful. Platform teams rarely see their users' capabilities jump overnight.

## Learning goals
- [ ] Define a harness as model + prompt + tools + context + verifiers + environment, and say which parts you control in a codebase.
- [ ] Write an AGENTS.md that is a map (under about 100 lines), plus an INVARIANTS.md that states ordering, idempotency, consistency and retry semantics as checkable rules.
- [ ] Build a custom lint whose error message tells the agent how to fix the violation, and a docs-freshness check that keeps the map true.
- [ ] Give an agent hermetic fakes, fast local checks and a single "done" command.
- [ ] Give an agent queryable structured logs and repro scripts, and encode the bug-fix protocol (reproduce, failing test, fix, verify) as a skill.
- [ ] Build a seeded task suite with hidden tests, and report an autonomy rate with a confidence interval.
- [ ] Ablate harness components on a model upgrade, and run an entropy-management loop.

## Reading order
1. [01-what-a-harness-is.md](01-what-a-harness-is.md): the six parts, harness vs model gains, and the full answer to "is context enough?"
2. [02-pillar-understand.md](02-pillar-understand.md): the architecture map, INVARIANTS.md, ADRs, glossary, nested AGENTS.md, code search, and docs kept fresh by checks
3. [03-pillar-verify.md](03-pillar-verify.md): fast checks, lints with remediation, hermetic fakes, per-worktree environments, contract tests, checkable "done"
4. [04-pillar-diagnose.md](04-pillar-diagnose.md): agent-queryable observability, repro scripts, runbooks as skills, the bug-fix protocol, and how to stop the agent "fixing" the test
5. [05-measuring-autonomy-rate.md](05-measuring-autonomy-rate.md): the seeded suite, hidden tests, confidence intervals, hill-climbing only the harness, and ablation
6. [06-entropy-and-harness-decay.md](06-entropy-and-harness-decay.md): golden principles, cleanup agents, quality scores, pruning, and the model-upgrade drill
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
- [03-context-engineering](../03-context-engineering/README.md): how context files get loaded, and why pruning matters.
- [04-agentic-coding-workflows](../04-agentic-coding-workflows/README.md): explore, plan, implement, verify; TDD with agents; worktrees.
- [07-loops](../07-loops/README.md): oracles, "prove it can fail", and governors. The harness is what the loop's oracle runs on.
- Helpful: [10-evals-fundamentals](../10-evals-fundamentals/README.md) for pass@k and pass^k, and [12-hill-climbing](../12-hill-climbing/README.md) for error bars.

## Key takeaways
- **A harness is everything except the weights.** In your repo, that means the context, the tools, the verifiers and the environment. Changing the harness can move results as much as changing the model.
- **Three pillars, all required.** Understand (what to change), Verify (is it right), Diagnose (what is wrong). Context alone produces confident, wrong changes.
- **Write invariants as checks, not prose.** Every guarantee in INVARIANTS.md should name the lint, test or repro script that enforces it. A guarantee with no enforcer is a wish.
- **Error messages are prompts.** Make a lint's output say *why* and *how to fix*, because that text lands in the agent's context at exactly the right moment.
- **Grade with what the agent cannot touch.** Use hidden tests, restore the original tests, and run the lint from a pristine checkout. Otherwise you are measuring the agent's ability to edit the grader.
- **"Enough context" is an autonomy rate, not a feeling.** Seed 20 to 50 tasks from real features, bugs and incidents. Report the rate with a confidence interval, and hill-climb only the harness.
- **Re-ablate on every model upgrade.** Every component encodes an assumption about what the model cannot do. Some assumptions expire, and some components start to hurt (Opus 5 over-verifies when told to verify).
- **Entropy is continuous.** Agents copy whatever patterns exist. Encode golden principles as lints and run cleanup agents on a schedule, rather than holding a "slop Friday".
