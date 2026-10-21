# 06: Headless agents and fan-out: `claude -p`, `codex exec`, and a driver

## The idea

A headless agent is a coding agent invoked as a Unix command: prompt in, edits and a result out, exit code set. `claude -p "..."` and `codex exec "..."` turn the agent into something you can put in a `for` loop, a Makefile, a CI job or a pre-commit hook. **Fan-out** is the pattern of running one headless invocation per target (file, package, service, repo), in parallel, with a verifier per target.

This is where the course thesis turns most mechanical. Fan-out is only safe when **each target has its own automatic check**, because nobody watches 40 sessions. With a per-target oracle, fan-out is a batch job with a success rate you can measure. Without one, it's 40 unreviewed diffs.

## Why it matters

The numbers from teams who do this at scale all come from narrow, verifiable task classes:

- Spotify's background coding agent: agents save 60-90% of the time on migrations ([Spotify Engineering, "Honk" part 1](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1)). Their most serious failure mode is a PR that passes CI but is functionally incorrect, "as it erodes trust in our automation" ([part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). Their answer is verifiers that run in a Claude Code Stop hook (no PR if any fails), plus an LLM judge of the diff against the prompt ([part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)).
- Stripe's minions: a hard loop budget, "often one, at most two, CI runs—and only after we've fixed everything we can locally" ([Stripe, "Minions"](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents)).
- The Claude Code docs' fan-out recipe starts with a canary: "Refine your prompt based on what goes wrong with the first 2-3 files, then run on the full set" ([docs, Best practices](https://code.claude.com/docs/en/best-practices)).

Each of these is a reliability-engineering control: budgets, canaries, and an oracle that isn't the worker.

## How to do it

### The headless flags you need (Claude Code)

From the docs as read on 2026-10-19 ([Run Claude Code programmatically](https://code.claude.com/docs/en/headless)). Re-check them on your version.

| Flag | What it does | Why it matters for fan-out |
|---|---|---|
| `-p` / `--print` | Non-interactive. Exit 0 on success, non-zero on failure | The driver branches on exit status |
| `--output-format json` | One JSON object with `result`, `session_id`, `total_cost_usd` (a client-side estimate) and more | Cost accounting and `is_error` per target |
| `--json-schema '<schema>'` | Structured output in `structured_output` | Machine-readable per-target reports |
| `--allowedTools "Read,Edit,Bash(go test *)"` | Pre-approve specific tools (permission-rule syntax; the space before `*` matters) | Least privilege per batch |
| `--permission-mode dontAsk` | Deny anything that would prompt, unless allowed | Unattended runs can't hang on a prompt |
| `--bare` | Skip auto-discovery of hooks, skills, plugins, MCP servers, CLAUDE.md | The same result on every machine. Needs `ANTHROPIC_API_KEY`. The docs say it "will become the default for `-p` in a future release" |
| `--max-budget-usd N` | Stop when the run reaches the cap | A per-target budget |
| `--worktree name` | Run in an isolated worktree (`-p` skips the trust check and doesn't clean up) | Parallel writers that need isolation |

One security note from the same page: without `--bare`, a `-p` session runs the hooks in a project's `.claude/settings.json` and connects its `.mcp.json` servers "even in a folder you've never trusted". Fan-out over third-party repos should use `--bare`. See [Module 16](../16-security-and-containment/README.md).

### The equivalents for Codex

From the Codex non-interactive docs (read 2026-10-19; the URL redirects to `learn.chatgpt.com`) ([Codex, non-interactive mode](https://developers.openai.com/codex/noninteractive)):

| Flag | Notes |
|---|---|
| `codex exec "<task>"` | Progress goes to stderr, the final message to stdout |
| `--sandbox read-only \| workspace-write \| danger-full-access` | **`read-only` is the default in exec mode**, so a migration needs `workspace-write` |
| `--json` | JSONL events (`thread.started`, `turn.completed`, `turn.failed`, `item.*`, `error`) |
| `-o, --output-last-message <path>` | Writes the final message to a file |
| `--output-schema <file>` | Final response must match a JSON Schema |
| `--ephemeral` | Don't save session rollout files |
| `--skip-git-repo-check` | Codex requires a git repo by default |
| `codex exec resume --last "<follow-up>"` | Continue the previous run |

The docs also say that `--full-auto` "is no longer supported", replaced by `--sandbox workspace-write`. Old blog posts with `--full-auto` are stale.

### From a `for` loop to a driver

The docs' loop is the right starting point:

```bash
for file in $(cat files.txt); do
  claude -p "Migrate $file from Python 2 to Python 3. Return OK or FAIL." \
    --allowedTools "Edit,Bash(git commit *)" \
    --permission-mode dontAsk
done
```

It's serial, has no per-file verifier, trusts the agent's "OK", and lets each agent `git commit`. That's fine serially, and a race on `.git/index.lock` the moment you parallelize. [`code/fanout.py`](code/fanout.py) is the same idea with the reliability controls a senior engineer would add:

| Control | Flag | Distributed-systems analogue |
|---|---|---|
| Bounded worker pool | `--concurrency 6` | Bulkhead / connection pool. Protects rate limits and the box |
| Oracle per target | `--verify 'python check_callsite.py {target}'` | Health check. The verdict comes from outside the worker |
| Generate-verify-fix | `--retries 1` + `{feedback}` / `$FANOUT_FEEDBACK` | Retry with the error in context, capped (Stripe's "at most two") |
| Canary | `--canary 3` | Canary deploy. A failed canary aborts the batch |
| Circuit breaker | `--max-failures 5` | Stop admitting work when the error rate says the prompt is wrong |
| Single writer | `--on-success 'git add {target} && git commit -qm "..."'` (runs under one lock) | Serialize writes to shared state |
| Idempotent re-runs | `--results r.jsonl --resume` | Skip completed work. The results file is a ledger |
| Claimed vs. verified | `claimed_ok_but_not_ok` in the summary | Measures the trust-then-verify gap directly |
| Kill on timeout | `--agent-timeout 900` (kills the process group) | Deadlines that actually release resources |

## Worked example: the same migration, naive vs. driven

The task: migrate 40 call sites from `emit_event(topic, entity)` (fire-and-forget, no partition key) to `publisher.publish(topic, entity, key=entity["id"])`, so per-entity ordering holds on the new topic. Full artifacts are in [examples.md](examples.md) scenario 3. This shows the contrast.

**The bad version.**

```bash
rg -l 'emit_event\(' services/ > files.txt
cat files.txt | xargs -P 8 -I{} claude -p "migrate {} from emit_event to publisher.publish with a key. Return OK or FAIL." \
  --allowedTools "Edit,Bash(git commit *)" --permission-mode dontAsk
```

What goes wrong:

- Eight agents race on `git commit` and `.git/index.lock`. Some commits fail, and some agents retry by running `git add -A`, which sweeps up another agent's half-written file.
- `{}` is interpolated unquoted into the prompt, so a path with a space breaks the command.
- Success is whatever each agent printed. An agent that gave up but printed "OK" is counted as done.
- No canary: if the prompt has a systematic flaw (say, it keys by `entity["tenant_id"]`), you find out after 40 runs and 40 charges.

**The good version** (with the offline fake agent, so you can run it; the real-agent template is in [code/README.md](code/README.md)):

```bash
cd 04-agentic-coding-workflows/code
../../.venv/bin/python migrate_demo.py
```

Actual output from the demo (fake agent, deterministic):

```text
agent_failed   attempts=1 claimed_ok=False svc_05_shipment.py  <- agent exited non-zero / is_error
verify_failed  attempts=2 claimed_ok=True svc_12_customer.py  <- services/svc_12_customer.py: syntax error at line 8: '(' was never closed
ok             attempts=2 claimed_ok=True svc_20_customer.py  <- recovered after verifier feedback
verify_failed  attempts=2 claimed_ok=True svc_33_payment.py  <- services/svc_33_payment.py: line 8: legacy emit_event() call remains
{
  "targets": 40,
  "by_status": {"ok": 37, "agent_failed": 1, "verify_failed": 2},
  "claimed_ok_but_not_ok": 2,
  "needed_retry": 1,
  ...
}
```

Read it as an SRE would. Two agents *claimed* success and were wrong: one wrote broken code, and one changed nothing. Only the verifier caught them. One target recovered on its second attempt because the verifier's error went back into the prompt. One failed outright and needs a human. Each of the 37 "ok" targets passed a check that could have failed.

**Why the second version works.** Success is defined by the oracle. Concurrency is bounded. Commits (if enabled) go through one lock. A systematic prompt bug would have tripped the canary on the first three files. And the results file lets you fix the prompt and `--resume` without redoing the 37 that passed.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Trusting "Return OK or FAIL" | `claimed_ok_but_not_ok > 0` in the summary. The verifier is the source of truth. |
| A verifier that can't fail | Run it on an unmigrated file first, and confirm exit 1. ("Prove the oracle can fail", [Module 07](../07-loops/README.md).) |
| Agents committing in parallel | `index.lock` errors, or commits containing other targets' files. Move commits to `--on-success`. |
| No canary | Many identical failures in results.jsonl. Always `--canary 2`-`3` on a new prompt. |
| Unbounded retries | Cost grows with no rise in success rate. Keep `--retries` at 1 or 2, then hand off to a human. |
| Non-reproducible runs | Different results on teammates' machines because of their hooks, skills or MCP. Use `--bare` with explicit flags. |
| Codex edits silently rejected | `codex exec` in its default `read-only` sandbox. Pass `--sandbox workspace-write`. |

## In your day job

- Before any fan-out, write and test the per-target verifier. If you can't write one, the task isn't ready for fan-out ([07](07-reviewing-ai-code-and-when-not-to-delegate.md)).
- Start every new batch with `--canary 3 --max-failures 5`. Read the canary diffs yourself before letting the rest run.
- Keep the results JSONL with the PR. It records what was verified, what needed a retry, and what needed a human.
- Use `--bare` plus explicit `--allowedTools` for scripted runs, so the batch behaves the same in CI as on your laptop.
