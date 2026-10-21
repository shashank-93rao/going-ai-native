# 05: Parallel sessions, worktrees, background and cloud agents

## The idea

Once one session is reliable, the next lever is running several at once. There are three increasingly detached ways to do it:

| Mode | Where it runs | You are | Isolation |
|---|---|---|---|
| **Parallel interactive sessions** | Your machine, one terminal each | Switching between them | A git worktree per session |
| **Background sessions** | Your machine, no terminal attached | Dispatching and checking an inbox | A worktree per session (automatic) |
| **Cloud sessions** | Remote VM, fresh clone | Reviewing branches and PRs | A separate machine |

The rule that makes any of this safe comes straight from distributed systems: **single writer per piece of state.** Parallel agents are fine when each one owns its files, branch, ports and database. They fail when they share mutable state, the way two processes writing one file without a lock fail. Cognition's 2026 update reached the same conclusion for agent architectures: multi-agent works when "writes stay single-threaded and the additional agents contribute intelligence rather than actions" ([Cognition, "Multi-Agents: What's Actually Working"](https://cognition.com/blog/multi-agents-working)). [Module 06](../06-agent-architectures/README.md) develops that principle. This file is the hands-on version.

## Why it matters

The ceiling on parallel agents is your review bandwidth, not compute. Simon Willison: "I can only focus on reviewing and landing one significant change at a time" ([Willison, "Embracing the parallel coding agent lifestyle"](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)). He argues parallelism still pays when the parallel work is cheap to review. His list:

1. Research and proof-of-concept builds, which you throw away.
2. Codebase explanations written to notes, for reuse as later context.
3. Small maintenance chores (deprecation warnings, lint).
4. Carefully pre-specified work. "Code you specified yourself is far easier to review."

He also suggests "sending out a scout": give an agent a hard task you don't intend to merge, just to learn where the sticky bits are.

Mitchell Hashimoto's routine is a good model of background agents done well. He spends the last 30 minutes of the day launching research, exploration and triage agents that *only write reports*. He outsources "slam dunks" to a background agent **with notifications off**, so it doesn't fragment his attention ([Hashimoto, "My AI Adoption Journey"](https://mitchellh.com/writing/my-ai-adoption-journey)).

## How to do it

### Parallel sessions with worktrees (Claude Code)

All flags below were checked against the Claude Code docs on 2026-10-19 ([Worktrees](https://code.claude.com/docs/en/worktrees)):

```bash
claude --worktree fix-rebalance     # or -w; creates .claude/worktrees/fix-rebalance/ on branch worktree-fix-rebalance
claude --worktree idempotency-keys  # second terminal, second isolated checkout
claude --worktree "#1234"           # branch from a PR's head commit
```

Facts that matter in practice:

- New worktrees branch from the repo's **default branch** (`worktree.baseRef: "fresh"`) unless you set `"head"` in settings to carry your local commits.
- A worktree is a fresh checkout, so gitignored files like `.env` are missing. List them in `.worktreeinclude` (gitignore syntax) to copy them in. Dependencies still need installing per worktree.
- Add `.claude/worktrees/` to `.gitignore`.
- On exit from an interactive session, a clean worktree with no name is removed automatically, and one with changes prompts you. **`-p` runs don't clean up**, so remove them with `git worktree remove`.
- Claude Code enforces isolation: it blocks edits to paths in the main checkout and git commands redirected into it. It does *not* track what a shell command writes, so `cp` into the main checkout isn't blocked. Hooks keep `${CLAUDE_PROJECT_DIR}` pointing at the main checkout, and the hook input's `cwd` gives the worktree.

Plain git works too, and works with any agent (Codex, Aider, anything):

```bash
git worktree add ../payments-idem -b idem-keys
cd ../payments-idem && codex        # or: claude
git worktree list
git worktree remove ../payments-idem
```

**What a worktree does not isolate.** It gives separate files and a separate branch, sharing one `.git`. It does not give you separate ports, databases, Docker container names, Kafka topics or caches. Two worktrees both running `make test-integration` against `localhost:5432` with a fixed DB name will corrupt each other's state, and the result looks exactly like a flaky test. Give each worktree its own environment: derive ports and names from the worktree name. OpenAI's harness-engineering post describes booting one app instance plus an ephemeral log and metrics stack per worktree, so each agent can verify its own work ([OpenAI, "Harness engineering"](https://openai.com/index/harness-engineering/)). [Module 08](../08-harness-engineering/README.md) shows how to build that.

```bash
# .envrc or a make target: derive per-worktree resources
WT=$(basename "$PWD")
export PGDATABASE="app_${WT//-/_}"
export HTTP_PORT=$((20000 + $(printf '%s' "$WT" | cksum | cut -d' ' -f1) % 10000))
export KAFKA_TOPIC_PREFIX="${WT}."
```

### Subagents in worktrees, and `/batch`

Inside one session, a custom subagent with `isolation: worktree` in its frontmatter gets a temporary worktree of its own (docs). `/batch <instruction>` has Claude split a change across 5 to 30 subagents, each in its own worktree ([docs, Best practices](https://code.claude.com/docs/en/best-practices)). Use these when the split is mechanical. Use separate sessions when each stream needs your judgment.

### Background sessions

Agent view is a **research preview**: "The interface and keyboard shortcuts may change" ([docs, Agent view](https://code.claude.com/docs/en/agent-view), read 2026-10-19).

```bash
claude --bg --name flaky-ledger-it "investigate why LedgerConsumerIT fails ~1 in 30 runs; write findings to docs/research/ledger-it.md; do not change code"
claude agents                       # one screen: working / needs input / done
claude logs flaky-ledger-it
claude attach flaky-ledger-it
```

The docs show `--permission-mode plan` as an agent-view default (`claude agents --permission-mode plan`). If your version rejects it on a single `--bg` command, set it there instead, and keep "do not change code" in the prompt either way. Background sessions run under a local supervisor process and survive closing your shell. Before editing, a background session moves into its own worktree under `.claude/worktrees/`. `--bg` can't be combined with `-p`.

### Cloud sessions

```bash
claude --permission-mode plan                       # plan locally, commit and push the plan
claude --cloud "Execute the migration plan in docs/migration-plan.md"
claude --cloud "Fix the flaky test in LedgerConsumerIT"   # each --cloud is an independent session
claude --teleport                                   # pull a finished cloud session + its branch into this terminal
```

The cloud VM clones your GitHub remote at the current branch, **not your local checkout, so push first**. Network access is limited by default and configurable per environment ([docs, Claude Code in the cloud](https://code.claude.com/docs/en/claude-code-on-the-web)). Codex has a matching surface: `codex cloud exec --env <env> --attempts N "<task>"` submits a task, and `--attempts` (1 to 4) runs several attempts you choose between ([Codex CLI command reference](https://learn.chatgpt.com/codex/developer-commands?surface=cli), where `developers.openai.com/codex` pages redirected as of 2026-10-19).

### Choosing among them

| Situation | Choose |
|---|---|
| Two features you'll both review today | Two `--worktree` sessions |
| Investigations that only produce a report | `--bg` background sessions (Mitchell's end-of-day agents) |
| Long execution of an already-approved plan; your laptop may sleep | `--cloud` |
| Same mechanical change over many files | `/batch`, or headless fan-out ([06](06-headless-fan-out.md)) |
| Polling a deploy or babysitting a PR while you work | `/loop` in a session ([Module 07](../07-loops/README.md)) |

## Worked example: an on-call morning, three streams

**The bad version.** One terminal, one session. You ask it to look at the flaky `LedgerConsumerIT`, then mid-way ask it to bump the `pgx` version for a CVE, then ask about yesterday's lag alert. This is the docs' "kitchen sink session". The context holds three unrelated investigations. The CVE bump lands on the same branch as half-finished test changes. Then you run the integration suite to check the bump, and it fails because the test changes are half-applied, so you can't tell which change broke what.

**The good version.**

```bash
# 1. Report-only investigation, detached (no code changes allowed)
claude --bg --name lag-alert --permission-mode plan \
  "Read the consumer-lag alert from yesterday (runbooks/lag.md, dashboards/lag.json).
   Write docs/research/lag-2026-10-18.md: timeline, suspected cause, evidence. No code changes."

# 2. A slam dunk: isolated worktree, crisp verification, you'll review the diff
claude -w pgx-cve
> bump github.com/jackc/pgx/v5 to the patched version in go.mod, run go mod tidy,
> then `make check` and `make test-integration`. show output. nothing else changes.

# 3. The hard one, interactive, its own worktree and its own DB/ports via .envrc
claude -w ledger-it-flake
> (research-plan-implement, as in 02)
```

You check `claude agents` between steps of stream 3, review the `pgx-cve` diff when it reports done, and read the lag report at lunch.

**Why the second version works.** Each stream has one writer and its own branch. The report-only agent is in plan mode, so it can't write code. The integration tests in streams 2 and 3 don't share a database because the worktree name derives the resources. Your attention goes to stream 3, the one that needs judgment, and the cheap-to-review work runs alongside it.

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Shared ports, DBs or topics across worktrees | Tests that pass alone and fail when another worktree runs. `lsof -i :5432` shows two clients. Derive resources from the worktree name. |
| Cloud session ran against stale code | Its branch doesn't contain your last local commit. Push before `--cloud`. |
| More agents than you can review | PRs sitting unreviewed for more than a day while new sessions start. Cap parallel *write* sessions at your review capacity (often 2 to 3). Read-only agents are cheap. |
| Leaked worktrees from `-p` runs | `git worktree list` keeps growing. Remove them in your fan-out driver's cleanup, or periodically. |
| Two parallel writers on one file | Merge conflicts on the same hunk. Partition work by file or package before dispatching. |
| Notifications fragmenting attention | You context-switch on every "done". Batch your checks (Mitchell: notifications off). |

## In your day job

- Default to `claude -w <task>` (or `git worktree add`) for every change you expect to take more than a few minutes. One task, one worktree, one branch.
- Put per-worktree port, DB and topic derivation in your repo's dev setup, so parallel integration tests never collide.
- End the day by dispatching 2 or 3 report-only background agents on tomorrow's unknowns.
- Use cloud sessions for executing approved plans, and keep planning local, where you can steer.
