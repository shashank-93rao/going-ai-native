# 07: Loops
> After this module you can build an agent loop from scratch, put a real oracle and real governors around it, and run it unattended (Ralph, long-running harnesses, scheduled and event-driven agents) without it burning money, lying about being done, or running forever.

## Why this matters

Every agent is a loop: the model asks for a tool, your code runs it, the result goes back in, and the cycle repeats. Thorsten Ball's line is that a coding agent is "an LLM, a loop, and enough tokens" ([Ball, "How to Build an Agent"](https://ampcode.com/how-to-build-an-agent)). The inner loop is simple. The hard engineering is in the parts the model does not control: what counts as done, what counts as progress, and when to stop.

Nearly every expensive agent failure you will see is a loop failure. The agent declares victory on a half-built feature. It re-reads the same file forty times. It deletes the failing test. It keeps "fixing" a CI job overnight while the bill grows. Anthropic's code-review team saw one PR go through more than 50 automated review rounds overnight before they added round caps ([Anthropic, "How the Claude Code team does code review"](https://claude.dev/blog/solving-code-review-at-anthropic/)). Stripe caps its minions at two CI rounds because every round costs tokens, compute and time, with diminishing returns ([Stripe, "Minions"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)).

When loops are designed well, the results are large and well documented. Sixteen parallel Claudes in a bash `while true` loop built a 100k-line C compiler that builds Linux, for just under $20k ([Carlini, "Building a C compiler"](https://www.anthropic.com/engineering/building-c-compiler)). Bun was ported from Zig to Rust in about 11 days with coordinated agent loops, using its million-assertion test suite as the oracle ([Sumner, via Willison](https://simonwillison.net/2026/Jul/8/rewriting-bun-in-rust/)). In both cases, most of the effort went into the oracle and the harness, not the prompt.

The course thesis applies here most directly: **autonomy should scale with verifiability**. A loop is autonomy multiplied by iterations. It is only as safe as the check that decides whether to keep going.

## The distributed-systems anchor

A well-built agent loop is a **control loop**, and you already run dozens of them. A Kubernetes controller reads desired state (the spec), observes actual state, takes one action to reduce the difference, and repeats until they converge. An agent loop does the same: the spec is the desired state, the oracle measures the observed state, and the agent is the actuator. The governor around it is a **circuit breaker**, a **rate limiter** and a **deadline** combined. The oracle provides **backpressure**: it rejects bad work before that work propagates.

| Control-loop concept | Agent-loop equivalent |
|---|---|
| Desired state (spec / CRD) | `specs/*.md`, `fix_plan.md`, `feature_list.json`, a `/goal` condition |
| Observed state | Oracle output: test results, error counts, benchmark numbers |
| Reconcile action | One agent iteration (ideally one item) |
| Level-triggered, idempotent reconcile | Fresh-context iteration that re-reads all state from disk |
| Backoff, retry budget, circuit breaker | Iteration caps, consecutive-error breaker, $ budget |
| Liveness vs progress | "Agent is producing tokens" vs "oracle metric improved" |
| Exit status / conditions | Typed exit codes: success, fail, blocked, broken, budget, stalled |

**Where the analogy breaks.** A controller's actuator is deterministic and does what it is told. An agent is a stochastic actuator that can also *edit the sensor* (delete tests, write `passes: true`), *report success that did not happen*, and *repeat itself while looking busy*. That is why an agent loop needs things a reconciler does not: an oracle the actuator cannot write, a separate check on "done", and repetition and stall detectors. Reconcilers also converge on cheap actions. Each agent action costs real money, so the economics of each iteration matter (see [08-loop-economics](08-loop-economics.md)).

## Learning goals
- [ ] Write a ~250-line agent loop on the raw message API, and explain `stop_reason`, tool_use/tool_result pairing, and why the whole history is resent each turn
- [ ] Rank candidate oracles for a task, and prove an oracle can fail by running it against known-bad mutants
- [ ] Add governors (iteration, token, dollar and wall-clock caps, a consecutive-error breaker, repetition and no-progress detection) and map each to a typed exit code
- [ ] Build a generate → verify → fix loop and measure whether its fix rounds earn their cost
- [ ] Run a fresh-context Ralph loop over `fix_plan.md` and `specs/`, and explain when not to
- [ ] Design external state for a multi-session run (initializer, feature list, progress file, git) using the Anthropic and OpenAI templates
- [ ] Choose between `/goal`, `/loop`, a Stop hook, a routine and an event-driven agent, and make a scheduled agent idempotent
- [ ] Estimate the cost of a loop before you start it, and set its budget from that estimate

## Reading order
1. [01-the-agent-loop](01-the-agent-loop.md): model → tool → observe → repeat, built from scratch
2. [02-oracles-and-backpressure](02-oracles-and-backpressure.md): what decides "done", ranked, and how to prove it can fail
3. [03-governors](03-governors.md): budgets, breakers, stall and repetition detection, typed exits
4. [04-self-correcting-loops](04-self-correcting-loops.md): generate → verify → fix, and measuring whether reflection helps
5. [05-ralph-loops](05-ralph-loops.md): fresh-context same-prompt loops, the Stop-hook debate, case studies, when not to
6. [06-long-running-harnesses](06-long-running-harnesses.md): external state across many context windows
7. [07-scheduled-ambient-event-loops](07-scheduled-ambient-event-loops.md): `/loop`, `/goal`, Stop hooks, routines, idempotency, the agent inbox
8. [08-loop-economics](08-loop-economics.md): cost per iteration, diminishing returns, worked numbers
- [examples.md](examples.md), [exercises.md](exercises.md), [references.md](references.md), [code/](code/)

## Prerequisites
- [01-llms-for-systems-engineers](../01-llms-for-systems-engineers/README.md): tokens, context, caching, nondeterminism
- [04-agentic-coding-workflows](../04-agentic-coding-workflows/README.md): explore → plan → implement → verify, specs
- [05-tools-mcp-skills-hooks](../05-tools-mcp-skills-hooks/README.md): tool design and hooks (helpful, not required)
- Next steps: [08-harness-engineering](../08-harness-engineering/README.md) makes codebases loop-friendly, [12-hill-climbing](../12-hill-climbing/README.md) turns loops into measured improvement, [14-steering-and-guardrails](../14-steering-and-guardrails/README.md) covers gates and mid-run steering in depth

## Key takeaways
- The loop itself is about 100 lines. The oracle, the governor and the state on disk are the product.
- Write the oracle first and prove it can fail. If a mutant survives your oracle, the loop will eventually find that gap.
- "Done" must come from something the agent cannot write: CI, a hook, a test exit code, a human. A promise string or a ticked box is a claim, not evidence.
- Every loop needs a real number for each limit (iterations, tokens, dollars, wall clock, consecutive errors) and a typed exit code for each way it can end.
- Progress means the oracle metric improved and the change was kept. Activity is not progress. Detect repeats with a sliding window, not just consecutive matches.
- For long runs, use fresh context and durable state files by default: one item per iteration, state in specs, plans and git. Same-session Stop-hook loops are for short gates.
- Loop hard where the oracle is strong (ports, migrations, test-to-green, performance targets). Stay interactive where it is weak (design, code you need to understand deeply).
- Price the loop before you run it. Iteration cost grows with context, success rate per round falls, and a budget should pause the run rather than surprise you.
