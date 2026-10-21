# 06: Hooks: blocking gates, not steering wheels

## The idea

A **hook** is your code that the agent harness runs at a fixed point in the loop: before a tool call, after a tool call, when the agent tries to stop, when a session starts. In Claude Code, hooks are configured in `settings.json` and run deterministically, every time. CLAUDE.md instructions are advisory; a hook is guaranteed to run ([Claude Code hooks guide](https://code.claude.com/docs/en/hooks-guide)).

The three events that matter most:

| Event | Fires | Can it block? | Typical job |
|---|---|---|---|
| `PreToolUse` | After the model chooses a tool call, before it runs | Yes: `deny`, `ask`, or `allow`, or rewrite the input (`updatedInput`) | Policy: block `kubectl delete` in prod, protect `.env` |
| `PostToolUse` | After the tool ran | No (it already ran). It can add context next to the result, or replace what Claude sees with `updatedToolOutput` | Run the formatter or linter after an edit and report errors |
| `Stop` | When the agent tries to end its turn | Yes: `decision: "block"` with a `reason` keeps it working | Completion gate: refuse to stop while tests fail |

The course stance, from the research synthesis: **blocking verification gates work; hooks that try to steer behavior mostly don't.** A hook that says "no, and here's why" at a decision point is a check the agent can't skip. A hook that injects "remember to write good code" after every edit is another prompt, with the same reliability as any prompt.

## Why it matters

The disagreement in the field is real, and it resolves along this line:
- Armin Ronacher listed hooks among the things that didn't work for him in mid-2025: they couldn't change what executes, and denies didn't work in YOLO mode ([Ronacher, "Agentic Coding Things That Didn't Work"](https://lucumr.pocoo.org/2025/7/30/things-that-didnt-work/)). (Claude Code has since added `updatedInput` for PreToolUse, so the first complaint is partly dated.)
- Spotify's background agent runs all verifiers in a Claude Code **Stop hook**. If any fails, no PR is opened ([Spotify Engineering, part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3)). That's a gate, and it's the backbone of their system.
- Anthropic's own docs show the same split: a `PreToolUse` hook that blocks edits to `.env` and `.git/`, and a Stop hook that verifies tests pass ([hooks guide](https://code.claude.com/docs/en/hooks-guide)).

The difference: a gate turns a property you can check (this command deletes in prod; the test suite fails) into a hard stop in the loop. Steering tries to turn a property you can't check into one by repeating it. [Module 14](../14-steering-and-guardrails/README.md) builds the Stop-hook gate in depth; this file covers the mechanics and the PreToolUse case.

## How it works (Claude Code, verified against the docs in October 2026)

### Configuration

Event, then matcher group, then handlers:

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash",
       "hooks": [{"type": "command",
                  "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/block_kubectl_delete.py\"",
                  "timeout": 10}]}
    ]
  }
}
```

`matcher` is a tool name (`Bash`), a `|` list (`Edit|Write`), or a regex (`mcp__deploy-status__.*`). Handler `type` can be `command`, `http`, `mcp_tool`, `prompt` (a single LLM call) or `agent` (a subagent with tools). Command hooks default to a 600-second timeout on most events.

### Input

One JSON object on stdin. For `PreToolUse` on Bash:

```json
{"session_id": "abc123", "transcript_path": "/home/user/.claude/projects/.../transcript.jsonl",
 "cwd": "/home/user/my-project", "permission_mode": "default", "hook_event_name": "PreToolUse",
 "tool_name": "Bash", "tool_input": {"command": "npm test", "description": "Run test suite"},
 "tool_use_id": "toolu_01ABC123..."}
```

`PostToolUse` adds `tool_response`. `Stop` includes `stop_hook_active` (true when Claude is already continuing because of a stop hook) and `last_assistant_message`.

### Output: exit codes and JSON

| Exit code | Meaning |
|---|---|
| `0` | Success. If stdout is a JSON object, Claude Code applies its fields. |
| `2` | Blocking error. PreToolUse: the call is blocked. Stop: Claude keeps working. stderr is the reason shown to Claude. |
| anything else | **Non-blocking** error. The action proceeds and the transcript shows a hook error. |

That last row is the most important line in this file for a safety hook: **a Python crash exits 1, and exit 1 lets the tool call through.** Catch everything and exit 2, or configure the hook to block on failure.

The structured PreToolUse decision (exit 0):

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Destructive command blocked by hook"}}
```

`permissionDecision` is `allow`, `deny`, `ask` (prompt the human) or `defer`. The reason is shown to Claude, so write it as an instruction. Deny and ask rules in permissions are still evaluated whatever the hook returns.

A Stop gate returns `{"decision": "block", "reason": "..."}`. Claude Code overrides the next block after a stop hook has continued the turn eight times in a row, and the docs tell you to check `stop_hook_active` to avoid blocking forever on a condition that can't resolve.

## Worked example: block `kubectl delete` in production

Situation: your on-call agent runs in Claude Code with `kubectl` on PATH and a kubeconfig that includes prod contexts. You want it to investigate freely and never delete anything in prod.

### Before: an instruction

```markdown
# CLAUDE.md
- Never run `kubectl delete` against production.
```

What happens (illustrative): during a stuck-rollout investigation, the agent decides a crash-looping pod should be recycled and runs `kubectl delete pod ledger-writer-7d9f-1`. The current context is `gke_acme_europe-west1_prod`. The instruction was in context. It was outweighed by a plausible local reason, the same way a human under pressure skips a runbook step. There is no check anywhere in the loop.

### After: a gate

`code/hooks/block_kubectl_delete.py` reads the event from stdin, splits the command into simple commands (handling `&&`, `;`, pipes, `bash -c '...'`, and wrappers like `sudo`, `env A=B`, `xargs`), finds `kubectl` invocations, parses the verb and `--context`, and falls back to `kubectl config current-context`. Core of the decision:

```python
for seg in segments(command):
    args = kubectl_invocation(seg)
    if args is None:
        continue
    verb, ctx, dry_run = parse_kubectl(args)
    if verb != "delete" or dry_run in ("client", "server"):
        continue
    ctx = ctx or current_context()
    if ctx is None:
        return "ask", "kubectl delete with an unknown kube context ... A human must approve it."
    if PROD_PATTERN.search(ctx):
        return "deny", (f"Blocked by policy: `kubectl delete` in production context {ctx!r}. Do not retry with "
                        "different syntax. Instead: (1) run the same command with --dry-run=server and show the "
                        "output, then (2) give the user the exact command to run themselves.")
```

Real runs of the hook (current context set to `gke_acme_europe-west1_prod`):

```text
kubectl delete pod x                                      => deny
cd /tmp && kubectl --context prod-us delete deploy y      => deny
bash -c 'kubectl delete ns foo'                           => deny
kubectl delete pod x --dry-run=server                     => (no output: allowed)
kubectl --context=staging delete pod x                    => (no output: allowed)
echo 'kubectl delete                                      => ask   (unparseable quoting)
```

Note the design of the deny reason. It doesn't just say no. It tells the agent the two useful things it *can* do, and it pre-empts the failure mode where the agent tries `k delete` or a Python client to route around the block. The session then looks like this (illustrative):

```text
-> Bash(kubectl delete pod ledger-writer-7d9f-1)
   PreToolUse hook denied: Blocked by policy: `kubectl delete` in production context 'gke_acme_europe-west1_prod'. ...
-> Bash(kubectl delete pod ledger-writer-7d9f-1 --dry-run=server)
   pod "ledger-writer-7d9f-1" deleted (server dry run)
(illustrative) I can't delete pods in prod. The pod is crash-looping on the poison message at partition 3, offset
88123401, so recycling it won't help: it will crash again on the same record. If you still want to recycle it, run:
kubectl --context gke_acme_europe-west1_prod -n payments delete pod ledger-writer-7d9f-1
```

Other design choices, each one a decision you should be able to defend:
- **Fail closed.** Unparseable stdin exits 2. Any uncaught exception exits 2. An unknown context returns `ask`.
- **`--dry-run=server` is allowed**, because it's the evidence a human needs to approve.
- **`preprod-1` is not prod** under the default pattern (a `prod` segment bounded by separators). Make the pattern match your naming, via `PROD_CONTEXT_PATTERN`.
- **Tested offline.** `code/test_hook.py` runs the script as a subprocess with JSON on stdin, exactly as Claude Code does, across 20+ commands.

What it does **not** do, and must not be mistaken for: a security boundary. The agent can write a Python script that calls the Kubernetes API, or `cat` a kubeconfig into a different tool. Hooks also run outside Claude Code's Bash sandbox. The boundary is RBAC: the agent's prod credentials shouldn't have `delete` at all ([Module 16](../16-security-and-containment/README.md)). The hook's job is to catch the honest mistake, quickly, with a useful message.

### Two more gates worth having

A `PostToolUse` formatter on edits (feedback, not steering: it reports a fact):

```json
{"PostToolUse": [{"matcher": "Edit|Write",
                  "hooks": [{"type": "command", "command": "\"${CLAUDE_PROJECT_DIR}\"/scripts/lint_changed.sh"}]}]}
```

A `Stop` gate that refuses to end the turn while tests fail, with the loop guard:

```python
#!/usr/bin/env python3
import json, subprocess, sys
event = json.load(sys.stdin)
if event.get("stop_hook_active"):
    sys.exit(0)  # already continued once for this; let the 8-block cap and the human take it from here
r = subprocess.run(["make", "test-fast"], capture_output=True, text=True, timeout=300)
if r.returncode != 0:
    print(json.dumps({"decision": "block",
                      "reason": "make test-fast fails; fix it before finishing:\n" + r.stdout[-1500:]}))
sys.exit(0)
```

## Pitfalls

| Pitfall | How to detect it |
|---|---|
| Hook crashes and fails open (exit 1) | Feed it malformed JSON and an unexpected `tool_input` shape in a test; assert exit 2. |
| Matching strings instead of parsing | `grep "kubectl delete"` blocks `echo kubectl delete` and misses `kubectl --context prod delete`. Tokenize, find the binary, parse the verb. |
| Wrong matcher for MCP tools | Hook never fires. Matchers use the full tool name (`mcp__server__tool`); plugin-bundled servers use `mcp__plugin_<plugin>_<server>__<tool>`. |
| Steering hooks | A PostToolUse hook that injects "remember the style guide" on every edit. Measure with and without; if the eval doesn't move, delete it. |
| Stop gate that can never pass | If the agent keeps calling tools between blocks, it loops with no end: the 8-continuation cap resets on every tool call, so it only stops a gate that blocks with nothing in between. Check `stop_hook_active`, give the gate its own block budget (see [Module 14](../14-steering-and-guardrails/03-hooks-as-gates.md)), and gate on something the agent can actually fix. |
| Slow hooks on hot paths | A 2-second hook on every Bash call adds minutes to a session. Time it; keep `PreToolUse` hooks fast and offline. |
| Hooks from untrusted repos | A cloned repo's `.claude/settings.json` hook is code that runs on your machine. Anthropic reports fixing a case where hooks in a cloned repo's settings ran before the trust prompt ([Anthropic, "How we contain Claude"](https://www.anthropic.com/engineering/how-we-contain-claude); more in [Module 16](../16-security-and-containment/README.md)). Review hook config like CI config. |
| Treating the hook as the control | Prod credentials still allow delete. Audit what the credential can do, not what the hook blocks. |

## In your day job
- List the three commands that would ruin your week if an agent ran them (prod deletes, `terraform apply`, force-push to main). Write a `PreToolUse` hook for each, with subprocess tests like `test_hook.py`.
- Replace any "never do X" line in CLAUDE.md that you can check mechanically with a hook, and delete the line.
- Put your fast test suite behind a `Stop` gate for agent sessions in your repo, with the `stop_hook_active` guard.
- Review `.claude/settings.json` hook changes in PRs with the same care as CI pipeline changes.
