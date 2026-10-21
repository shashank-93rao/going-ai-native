# 01: Explore, plan, implement, verify

## The idea

Every productive agentic coding session follows the same four phases. **Explore** means reading the code with no edits. **Plan** means writing down the change and having a human review it. **Implement** means making the change against the plan. **Verify** means running a check that can fail and showing the evidence. Claude Code's best-practices guide calls these explore, plan, implement, commit, and makes verification a separate first-class rule ([Claude Code docs, "Best practices"](https://code.claude.com/docs/en/best-practices)). The agent's internal loop has the same shape: "gather context, take action, verify results" ([Claude Code docs, "How Claude Code works"](https://code.claude.com/docs/en/how-claude-code-works)).

The phases matter because the agent is cheapest to correct at the first ones and most expensive at the last. A wrong mental model caught in explore costs one message. Caught in review, the same mistake costs a 600-line diff you have to unread.

Verification is the phase that decides how much autonomy you can grant. The docs put it bluntly: "Claude stops when the work looks done. Without a check it can run, 'looks done' is the only signal available, and you become the verification loop." That is the course thesis applied to a single session. **Autonomy should scale with verifiability.**

## Why it matters

Here are the failure modes you'll see if you skip phases. The docs list these as named anti-patterns:

- **Skip explore:** the agent pattern-matches on the file names and edits the wrong layer. Ask for "add retries" and you get retries in the HTTP client, when the service already retries in the queue consumer, so a single failure now produces 9 attempts.
- **Skip plan:** the diff solves a neighbouring problem. The docs' wording: "Letting Claude jump straight to coding can produce code that solves the wrong problem."
- **Skip verify:** the "trust-then-verify gap". The implementation looks plausible and doesn't handle edge cases. The docs' fix: "Always provide verification (tests, scripts, screenshots). If you can't verify it, don't ship it."

On the size of the verification effect: Boris Cherny, who created Claude Code, is *reported* to have said that giving Claude a way to verify its work improves quality "2-3x" ([VentureBeat, 2026-01-04, reporting his X thread](https://venturebeat.com/technology/the-creator-of-claude-code-just-revealed-his-workflow-and-developers-are)). That is a secondary report of a practitioner's estimate, not a measurement, so don't quote it as a number. The mechanism behind it is not in dispute: a check closes the loop without you.

## How to do it

### Phase 1: Explore (read-only)

In Claude Code, enter plan mode with `Shift+Tab` until the status bar shows `⏸ plan mode on`, or start with `claude --permission-mode plan`. In plan mode Claude reads files and answers questions but makes no edits (docs, read 2026-10-19). Codex doesn't need a separate mode for this: `codex exec` runs in a `read-only` sandbox by default ([Codex docs, non-interactive mode](https://developers.openai.com/codex/noninteractive)).

Point the agent at sources, not at your guesses:

```text
read internal/ingest/ and internal/ratelimit/. explain how a request flows from
the HTTP handler to the Kafka producer, where tenants are identified, and what
rate limiting exists today. cite file:line for each claim. don't propose changes yet.
```

When the exploration is big, delegate it: "use subagents to investigate X". Subagents read in their own context window and return a summary, so your main context stays clean (docs). The built-in `Explore` subagent is read-only.

### Phase 2: Plan

Ask for a plan that names files, interfaces, and the checks it will run. Press `Ctrl+G` to open the plan in your editor and change it directly before approving (docs). Review it the way you'd review an RFC. Is this the right layer? What's out of scope? What will tell us it worked?

The skip rule comes straight from the docs: "If you could describe the diff in one sentence, skip the plan." A typo fix, a log line, or a rename doesn't need a plan. A change that crosses files, or touches code you don't know, does.

### Phase 3: Implement

Approve the plan, or press `Shift+Tab` to leave plan mode, and let the agent implement against it. Two habits help:

- **Correct early.** `Esc` stops the agent mid-action and keeps the context. `Esc Esc` or `/rewind` restores code and conversation to a checkpoint. Checkpoints only track edits made through Claude's file tools, not changes made through Bash, so they don't replace git.
- **Reset instead of arguing.** "If you've corrected Claude more than twice on the same issue in one session, the context is cluttered with failed approaches. Run `/clear` and start fresh with a more specific prompt" (docs). Treat it like a crashed process. Restarting it with better input beats patching its state.

### Phase 4: Verify

The docs describe four strengths of verification gate. Pick the weakest one that's enough:

| Gate | Mechanism | Use when |
|---|---|---|
| In the prompt | "run `go test ./internal/ratelimit/...` and iterate until it passes" | Interactive work; you're watching |
| Across a session | `/goal all tests in ./internal/ratelimit pass and go vet is clean` (a separate evaluator re-checks after every turn) | Longer runs; you'll step away |
| Deterministic | A `Stop` hook that runs the check and blocks the turn from ending until it passes | Unattended runs; the check is a script |
| Second opinion | A verification subagent, or a workflow, that tries to refute the result in a fresh context | The check needs judgment, e.g. diff vs. spec |

([Module 14](../14-steering-and-guardrails/README.md) covers Stop hooks and `/goal` in depth, and [Module 07](../07-loops/README.md) covers the loops built on them.)

Whatever the gate, **ask for evidence, not assertions**: the command it ran, its exit code, and the last lines of output. Reviewing evidence is faster than re-running the check, and it works for sessions you weren't watching.

### The tension: "give it a way to verify" vs. over-verification

Anthropic's own guidance pulls in two directions here. The Claude Code docs make verification central. The Opus 5 prompting guide says that explicit instructions like "include a final verification step" cause *over-verification* on that model, and that removing them reduces wasted tokens with no loss in quality ([Anthropic, "Prompting Claude Opus 5"](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)).

> **Course stance (from the gap analysis):** put the check in the *environment*, not in the *prompt*. Give the agent a runnable test, a `make check` target, or a Stop hook. Don't add paragraphs telling it to double-check itself. Then re-measure on each model upgrade, because the right amount of prompting changes.

## Worked example: per-tenant rate limiting in a Go ingestion API

**The bad version.** One prompt, default mode:

```text
add per-tenant rate limiting to the ingestion API
```

What tends to happen *(illustrative output)*: the agent adds a `golang.org/x/time/rate` limiter in a new middleware, keyed by `r.RemoteAddr` because that's what it found first. It writes a unit test that constructs the limiter and asserts `Allow()` returns false after N calls, then reports "Done, all tests pass." Three problems survive:

1. Tenants sit behind a shared NAT and an L7 load balancer, so `RemoteAddr` is the LB's address. The limiter is effectively global.
2. There are 12 replicas, so the "limit" is 12x what you asked for.
3. The test exercises the library, not your handler. It would pass even if the middleware were never mounted.

None of these is a syntax problem, and all three are the kind of error a senior engineer catches in design review.

**The good version.** Same task, four phases.

Explore (plan mode):

```text
read cmd/ingest, internal/http, internal/auth. answer with file:line evidence:
1. where is the tenant id established for a request? (header, JWT claim, mTLS SAN?)
2. how many replicas run in prod and is there any shared state (redis, etc.) already used?
3. is there existing rate limiting anywhere (LB, envoy, middleware)?
don't propose anything yet.
```

The answer *(illustrative output)*: the tenant id comes from the `tid` claim, parsed in `internal/auth/jwt.go:88`. There are 12 replicas per `deploy/ingest.yaml:14`. Redis is already used for dedupe in `internal/dedupe/redis.go`. Envoy has a global limit, but nothing per tenant.

Plan:

```text
plan per-tenant limiting: limit applies across all replicas, keyed by the JWT tid,
429 with Retry-After on reject. list files to change, the redis key schema and TTL,
what happens when redis is down (fail open or closed? propose and justify), and the
exact tests including one that goes through the real router.
```

You press `Ctrl+G` and edit one line: *fail open when Redis is down, but emit `ratelimit_redis_errors_total` and log at most once per second*. That's a product decision, so it's yours to make, not the agent's.

Implement and verify, in one prompt:

```text
implement the plan. then run: go test ./internal/ratelimit/... ./internal/http/... -race
and the router-level test TestIngest_PerTenantLimit_AcrossReplicas (two handler
instances sharing one miniredis). show the command output. do not modify existing tests.
```

**Why the second version works.** The explore questions forced the agent to find the identity source, the replica count and the existing shared state before choosing a design. The plan exposed the fail-open/fail-closed decision to a human. The verification step names a test that would fail if the middleware weren't mounted, or if the limit were per replica. That is a check that can fail for the right reasons.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Planning trivial changes (overhead with no payoff) | You approved the plan without changing anything three times in a row on small diffs. Apply the one-sentence rule. |
| Rubber-stamping plans | Plans you approve never contain a decision you made. Each plan should leave at least one choice to you, or state why there isn't one. |
| "Verify" means the agent's own new test | Every check in the evidence was written in this session. Require at least one pre-existing or human-specified check. |
| Verification by assertion | The final message says "all tests pass" with no command or output. Make "show the command and output" part of your standard prompt. |
| Exploration that eats the context | The context meter is above half before implementation starts. Use subagents for reading, and see [02](02-research-plan-implement.md). |
| Over-prompting verification on newer models | Long runs spend many turns re-running the same tests. Remove "double-check" instructions and keep the environmental check (Opus 5 guide). |

## In your day job

- Make `Shift+Tab` into plan mode your default for anything that touches more than one package. Make `Ctrl+G` your default for any plan where you'd have a design opinion.
- Add one line to CLAUDE.md or AGENTS.md naming the fast check, e.g. `make check` (under 30 s), so every session has an oracle without being told.
- End every implementation prompt with the exact verification command and "show the output".
- After two failed corrections, `/clear` and rewrite the prompt with what you learned. Don't keep arguing in a polluted context.
