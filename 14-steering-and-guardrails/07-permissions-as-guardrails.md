# 07: Permission modes and allow/deny lists as guardrails

## The idea

Permissions are the coarsest steering mechanism and the most reliable. They don't try to change what the agent *wants* to do. They change what the harness *lets it do*, and when the harness asks a human first.

Claude Code has two layers ([permission modes](https://code.claude.com/docs/en/permission-modes) and [permissions](https://code.claude.com/docs/en/permissions), verified 2026-10-19):

1. **A mode** sets the baseline: what runs without asking.
2. **Rules** (`allow`, `ask`, `deny`) layer on top for specific tools and commands. PreToolUse hooks and the sandbox add programmable and OS-level enforcement.

The mental model to bring: modes are the default network policy, rules are firewall entries, and hooks are a programmable admission webhook. As with firewalls, **an allowlist is a boundary and a denylist on a Turing-complete interface is a speed bump.** The docs say this themselves: a Bash deny rule "covers the invocation Claude usually produces and isn't a security boundary around the program."

## Why it matters

Overeager behavior and honest mistakes are the first two items in the threat model Anthropic designed auto mode around, ahead of prompt injection and misalignment. Their incident examples are mundane: overly broad branch cleanup, hunting for other credentials after an auth error, and retrying a deploy with verification skipped ([Anthropic, "How we built Claude Code auto mode"](https://www.anthropic.com/engineering/claude-code-auto-mode)). None of these is an attack. All of them are what you get when an agent is helpful in the wrong direction. Permissions are how you make "the wrong direction" unavailable rather than merely discouraged.

## How it works

### Modes

| Mode | What runs without asking | Use for |
|---|---|---|
| `default` (shown as **Manual**) | reads only | sensitive work, unfamiliar code |
| `acceptEdits` | reads, file edits, common filesystem commands (`mkdir`, `touch`, `mv`, `cp`...) | iterating on code you're reviewing |
| `plan` | reads, plus classifier-approved commands when auto mode is available; edits blocked until you approve the plan | exploring before changing; the plan-review step in [05](05-detecting-drift.md) |
| `auto` | everything, with background classifier checks | long tasks, reducing prompt fatigue |
| `dontAsk` | reads in the working directories plus pre-approved tools; **anything that would prompt is denied** | locked-down CI and scripts |
| `bypassPermissions` | everything | isolated containers and VMs only |

Switch modes with Shift+Tab in the CLI, or `--permission-mode <mode>`. Recent versions start interactive sessions in auto mode by default; check the docs for your version. `.claude/settings.json` in a project cannot put you into `auto` or `bypassPermissions`. Those values in project settings don't take effect, so a cloned repo can't escalate itself.

Some things no mode auto-approves, not even `bypassPermissions`: explicit `ask` rules, `rm`/`rmdir` on critical paths, tools that require user interaction, and a few others. **Deny rules block in every mode, including `bypassPermissions`. Allow rules have no effect in `bypassPermissions`.**

### Rules and precedence

```json
{
  "permissions": {
    "allow": ["Bash(python3 -m pytest *)", "Bash(git diff *)", "Bash(make test)"],
    "ask":   ["Bash(git push *)", "Bash(kubectl *)", "Bash(terraform *)"],
    "deny":  ["Read(./.env)", "Read(./secrets/**)", "Edit(./.claude/hooks/**)", "Bash(git push --force *)"]
  }
}
```

- **Evaluation order is deny, then ask, then allow.** The docs: "The first match in that order determines the outcome, and rule specificity doesn't change the order." An allow rule can't carve an exception out of a deny rule.
- **Compound commands are split** on `&&`, `||`, `;`, `|`, `|&`, `&` and newlines, and a rule must match each subcommand. Deny and ask rules apply if *any* subcommand matches, including inside subshells and `$(...)`.
- **Some wrappers are stripped** before matching (`timeout`, `time`, `nice`, `nohup`, `stdbuf`), so `Bash(npm test *)` matches `timeout 30 npm test`. Environment runners (`npx`, `docker exec`, `devbox run`, `direnv exec`) are not stripped, so `Bash(devbox run *)` approves `devbox run rm -rf .`.
- **Put `*` after the subcommand.** `Bash(git log *)` allows only `git log`; `Bash(git *)` allows every git command.

### Hooks and rules together

From the permissions docs:

- A PreToolUse hook's `allow` doesn't bypass permission rules. Deny and ask rules are evaluated whatever the hook returns.
- A hook that exits 2 blocks the call *before* rules are evaluated, so it beats allow rules.

So the documented pattern for "run most Bash freely, except a few things" is: put `"Bash"` in `allow`, and register a PreToolUse hook that rejects the specific commands. That is what [`code/hooks/pre_tool_guard.py`](code/hooks/pre_tool_guard.py) is for. Its value over a deny rule is that it can look at the whole command with real logic: git global options, protected paths in redirects, deny reasons that say what to do instead.

### What a Bash deny rule doesn't stop

The docs' own table:

| Rule | Stops | Doesn't stop |
|---|---|---|
| `Bash(curl *)` | `curl https://example.com` | `/usr/bin/curl ...`, `sh -c 'curl ...'` |
| `Bash(rm *)` | `rm -rf build/` | `/bin/rm -rf build/`, `bash -c 'rm -rf build/'` |
| `Bash(git push *)` | `git push origin main` | `git -C . push origin main`, `git -c push.default=current push origin main`, `git 'push' origin main` |

The docs also warn that "Bash permission patterns that try to constrain command arguments are fragile": `Bash(curl http://github.com/ *)` misses `curl -X GET http://github.com/...`, `https://`, redirects, and `URL=... && curl $URL`. For network restrictions that must hold, deny the network tools in Bash, allow `WebFetch(domain:...)`, and use the sandbox's network allowlist.

## Worked example: three configurations for three contexts

### Bad: "allow everything, deny the scary stuff"

```json
{
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": ["Bash"],
    "deny": ["Bash(rm -rf *)", "Bash(git push --force *)", "Bash(cat .env)"]
  }
}
```

*Why it fails:* it reads like a policy and behaves like a suggestion. `find . -name '*.py' -delete`, `python3 -c "import shutil; shutil.rmtree('.')"`, `git -C . push --force origin main` and `grep -r KEY .env` all pass. The agent doesn't have to be malicious, just resourceful: if `rm -rf` is denied while it is trying to clean a build directory, the next most likely move is a different way to delete it. A denylist over a shell is a list of spellings.

### Good, interactive development

Use the shape of [`code/settings.example.json`](code/settings.example.json):

- `acceptEdits` mode, so edits flow and git makes them reviewable.
- A narrow `allow` list for the commands the agent runs constantly (tests, `git diff`, lint), so prompts are rare enough to be read ([06](06-human-in-the-loop.md)).
- `ask` for publishing and infrastructure (`git push`, `kubectl`, `terraform`).
- `deny` for secrets (`Read(./.env)`, `Read(./secrets/**)`) and for the guardrails themselves (`Edit(./.claude/hooks/**)`, `Edit(./.claude/settings.json)`, the test-approval file).
- `pre_tool_guard.py` for the logic rules can't express. It catches `git -C . push --force origin main`:

```text
$ echo '{"tool_name":"Bash","tool_input":{"command":"git -c push.default=current push --force origin main"}}' \
    | python3 hooks/pre_tool_guard.py
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
 "permissionDecisionReason": "[guard:force_push_main] Force-push to a protected branch. Push to a feature branch and open a PR."}}
```

The hook is still pattern matching. `bash -c "$(echo Z2l0IHB1c2g= | base64 -d)"` beats it. It is tuned for the overeager-agent threat, not the adversary. For the adversary, see the next configuration and [Module 16](../16-security-and-containment/README.md).

### Good, unattended CI fan-out

```bash
claude -p "Migrate $file from the v1 to the v2 client. Done means: make test-unit exits 0. Return OK or FAIL." \
  --permission-mode dontAsk \
  --allowedTools "Read" "Edit" "Bash(make test-unit)" "Bash(git diff *)"
```

This is an **allowlist**. `dontAsk` turns every would-be prompt into a denial, so the agent can do exactly four things. That shape comes straight from the docs' "run in CI with an exact allowlist" setup. (The docs note that cloud sessions ignore `dontAsk` from settings files; pass it on the command line.) Run it on 2 or 3 files before the fleet, as the best-practices page advises for fan-out. Add the Stop gate for the done-check.

### Good, fully unattended in a container

```bash
docker run --rm --network=agent-egress -v "$PWD:/work" -u 1000 agent-image \
  claude -p "$(cat PROMPT.md)" --dangerously-skip-permissions
```

`bypassPermissions` is acceptable *only* because the boundary moved to the container: non-root, a mounted worktree, egress through an allowlisting proxy, and no credentials inside ([Anthropic, "Claude Code sandboxing"](https://www.anthropic.com/engineering/claude-code-sandboxing)). Deny rules and hooks still run. Permission rules no longer matter much, because the box is the policy.

## Pitfalls

- **A denylist used as a boundary.** *Detect:* for each deny rule, try three alternative spellings (absolute path, `sh -c`, a different tool). If any of them work and the action matters, move the control into a hook with real parsing, or into the sandbox.
- **`*` in the wrong place.** `Bash(git *)` in `allow` allows `git push --force`. *Detect:* Claude Code warns at startup about some of these. Read the warnings, and review allow rules for a `*` that comes before the subcommand.
- **Environment runners in allow rules.** `Bash(npx *)` or `Bash(docker exec *)` allows anything. *Detect:* grep allow rules for runners, and replace them with runner-plus-command rules.
- **Expecting allow rules to apply in `bypassPermissions`.** They don't. Only deny rules and hooks remain. *Detect:* if a CI job relies on allow rules for safety, confirm it isn't running with `--dangerously-skip-permissions`.
- **Guardrail files the agent can edit.** *Detect:* `deny` rules or guard entries must cover `.claude/settings*.json`, `.claude/hooks/**`, the gate's state, and any approval files.
- **Broad allow rules surviving into auto mode.** The auto-mode post says broad allow rules are dropped on entering auto mode, and the permission-modes docs say narrow ones like `Bash(npm test)` stay in effect. Don't count on a broad rule being present or absent; test the mode you'll run in.

## In your day job

- Replace any `"allow": ["Bash"]` with the 5 to 10 commands the agent actually needs (scan your session transcripts for the commands it actually runs), and route the rest through ask or the guard.
- For CI agents, write the command line first (`dontAsk` plus an explicit `--allowedTools`), and only then the prompt.
- Put your guardrail files (`.claude/settings.json`, hooks, approval files) behind deny rules in the same commit that adds them.
- When someone asks "is it safe to run in bypass mode?", the answer is a question back: what's the container, what's the egress policy, and where are the credentials?
