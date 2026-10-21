# 06: Agent architectures
> After this module you can pick the least autonomous architecture that solves a task, implement each of the five workflow patterns with code gates, decide when multi-agent helps (and keep it to one writer), and make an agent run crash-safe and safe under concurrent user input.

## Why this matters

Most agent failures in production are architecture failures rather than prompt failures. A team wraps a fixed four-step process in an autonomous loop, then can't explain why it sometimes does three steps or seven. Another team splits a feature across "specialist" agents that each write code, and gets a merge that compiles in every file and works in none. A third ships an agent that opens a ticket, crashes, gets retried by the job runner, and opens the same ticket again, because the retry re-asked the model and the model picked a slightly different call.

None of these are exotic. They are the same mistakes you have seen in distributed systems: the wrong consistency model, several writers on shared state, and non-idempotent retries. The AI-specific twist is that one of the components is a nondeterministic decision-maker. If you re-run it you don't get the same decision back, so "just retry" is not safe unless you have recorded what it decided.

The course thesis applies directly: **autonomy should scale with verifiability.** A workflow with code gates between steps is checkable at every edge. An autonomous agent is checkable only at its tools and its final output. A swarm of writing agents is barely checkable at all. Every architecture choice in this module comes back to one question: *where are the checks, and what can they see?*

## The distributed-systems anchor

| Agent concept | What you already know | Where the analogy breaks |
|---|---|---|
| Workflow vs agent | Static DAG (Airflow) vs a dynamic planner | The "planner" is a stochastic model. Its plan is a sample, not a computation. |
| Single-writer multi-agent | Single-writer principle, single leader per partition | Agents conflict on *decisions*, not only on bytes. OCC catches byte conflicts and misses semantic ones. |
| Clean-context reviewer | An independent auditor, or a separate read replica for validation | The reviewer is the same model family, so its errors are correlated. Independence is partial. |
| Event-sourced run log | Event sourcing, a WAL, Temporal workflow history | You must log the model's *outputs* and replay them. Re-executing the "pure" step gives a different result. |
| Idempotency keys for tools | Stripe-style `Idempotency-Key`, exactly-once via dedup | The key has to come from the logged decision. A re-sampled decision gets a new key. |
| Double texting | Concurrency control on a per-thread aggregate: try-lock, queue, preempt, abort | Rollback reverts only your state. The model may already have acted on the world. |

## Learning goals
- [ ] Classify a task as single call, workflow, or agent using the number of steps and how predictable they are, and justify the choice in one paragraph.
- [ ] Implement prompt chaining, routing, parallelization (sectioning and voting), orchestrator-workers and evaluator-optimizer, each with a *code* check at the boundary.
- [ ] State the course stance on multi-agent systems, cite the evidence on both sides, and apply the single-writer rule to a design review.
- [ ] Build a clean-context reviewer whose context is provably limited to spec plus diff, with evidence-checked findings.
- [ ] Make an agent run resumable after a crash at any point, with exactly one side effect per logged tool call.
- [ ] Choose a double-texting policy for a product surface and name the failure mode of each alternative.
- [ ] Recognise harness decay: remove or cap scaffolding (verification steps, subagent spawning) that a newer model no longer needs.

## Reading order
1. [01-augmented-llm-and-workflows-vs-agents.md](01-augmented-llm-and-workflows-vs-agents.md): the building block, and the decision between workflow and agent
2. [02-five-workflow-patterns.md](02-five-workflow-patterns.md): chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer, each with its gate
3. [03-multi-agent-and-the-single-writer-rule.md](03-multi-agent-and-the-single-writer-rule.md): Anthropic +90% vs Cognition, the course stance, and harness decay (over-spawning)
4. [04-clean-context-reviewers.md](04-clean-context-reviewers.md): helpers that add intelligence, not actions
5. [05-durable-runs-event-sourcing-idempotency.md](05-durable-runs-event-sourcing-idempotency.md): checkpoints, resume, idempotent tools
6. [06-double-texting-and-concurrency.md](06-double-texting-and-concurrency.md): reject, enqueue, interrupt and rollback, mapped to OCC
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/README.md)

## Prerequisites
- [01-llms-for-systems-engineers](../01-llms-for-systems-engineers/README.md): tokens, sampling, nondeterminism
- [03-context-engineering](../03-context-engineering/README.md): why clean context matters, and context rot
- [05-tools-mcp-skills-hooks](../05-tools-mcp-skills-hooks/README.md): tool design (the agent-computer interface)
- Helpful: [07-loops](../07-loops/README.md) covers the agent loop from scratch. This module treats it as a component.

## Key takeaways
- Start with one call. Move to a workflow when the steps are known, and to an agent only when the number of steps can't be predicted. Each step up trades checkability for flexibility.
- Every arrow between LLM steps should pass through a **code gate**. If you can't write the gate, you can't tell where the pipeline broke.
- Multi-agent works when it spends more tokens on *independent reads* (research, search, review). It fails when parallel agents *write* shared state. **One writer, many readers.**
- OCC prevents lost updates, but it does not catch two agents making conflicting decisions in different files. Single-writer catches both.
- A reviewer is worth having only if its context is clean (spec plus diff), its findings must cite evidence, and severity filtering is done in code.
- A durable agent logs the model's decisions before acting on them, replays them on resume, and keys every side effect on the logged tool-call id.
- Double texting is concurrency control on a thread. Enqueue is the safe default for work that has side effects. Interrupt needs synthetic tool results. Rollback needs compensation for anything the run already did to the world.
- Harness assumptions decay. Current models over-spawn subagents and over-verify. Cap delegation in config, and re-ablate scaffolding on every model upgrade.
