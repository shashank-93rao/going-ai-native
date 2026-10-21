# Module 04 code

Everything here runs offline. Run the tests from the course root:

```bash
.venv/bin/python -m pytest -q 04-agentic-coding-workflows/code
```

| File | What it is |
|---|---|
| `fanout.py` | The fan-out driver. Runs a headless agent command per target with a concurrency limit, verifies each target with your verify command, retries with verifier feedback, and has a canary phase, a circuit breaker, a serialized `--on-success` hook, resumable JSONL results, and cost accounting from `claude -p --output-format json`. |
| `fake_agent.py` | Deterministic stand-in for `claude -p` / `codex exec`. It migrates `emit_event(t, x)` to `publisher.publish(t, x, key=x["id"])` and misbehaves on purpose when a file contains `# FAKE: fail | break | flaky | lie | sleep=N`. |
| `check_callsite.py` | The verifier (oracle) for that migration: the file parses, no legacy call remains, and every `publish()` passes `key=`. |
| `migrate_demo.py` | The 40-call-site migration from `examples.md` scenario 3, end to end, with four planted failures. |
| `tautology_lint.py` | AST heuristics for tests that can't fail (no assertion, `x == x`, asserting a mock's `return_value`, expected value computed by the code under test, swallowed assertions), plus a diff scan for removed asserts and new skips. |
| `diff_reviewer.py` | Clean-context reviewer that checks a diff against a SPEC and keeps only findings whose quoted evidence actually appears in the diff. Uses `ainative_kit`, so it runs against a `FakeClient` with no key. |
| `templates/` | `SPEC.md`, `plan.md` and `research.md` templates used throughout the module. |
| `test_fanout.py`, `test_review_tools.py` | Tests. Every "agent" is a fake shell command. |

## Running the scripts

```bash
cd 04-agentic-coding-workflows/code

# The 40-target migration demo (about 1 second)
../../.venv/bin/python migrate_demo.py --keep /tmp/mig   # inspect /tmp/mig/results.jsonl afterwards

# The driver on your own targets, with the fake agent
../../.venv/bin/python fanout.py --targets targets.txt \
  --agent "python fake_agent.py {target} --feedback {feedback}" \
  --verify "python check_callsite.py {target}" \
  --concurrency 8 --retries 1 --canary 3 --max-failures 5 --results results.jsonl

# Print the rendered commands without running anything
../../.venv/bin/python fanout.py --targets targets.txt --agent 'claude -p "migrate $FANOUT_TARGET"' --dry-run

# Lint agent-written tests, and check a diff for disarmed tests
../../.venv/bin/python tautology_lint.py tests/test_idempotency.py
git diff main -- tests/ | ../../.venv/bin/python tautology_lint.py --diff -

# Reviewer demo (FakeClient unless ANTHROPIC_API_KEY is set; AINATIVE_FAKE=1 forces the fake)
AINATIVE_FAKE=1 ../../.venv/bin/python diff_reviewer.py
../../.venv/bin/python diff_reviewer.py --spec SPEC.md --diff <(git diff main)
```

`diff_reviewer.py` adds `shared/` to `sys.path` itself when it runs as a script. The tests get it from the root `conftest.py`.

## Pointing the driver at a real agent

The driver doesn't care which agent it runs. These templates match the CLI docs as read on 2026-10-19. Re-check the flags on your version.

```bash
# Claude Code: bare mode for reproducibility, explicit tools, nothing else allowed
--agent 'claude --bare -p "$(cat prompt.md)
Target: $FANOUT_TARGET
Feedback from the last verification (may be empty): $(cat "$FANOUT_FEEDBACK")" \
  --allowedTools "Read,Edit" --permission-mode dontAsk --output-format json --max-budget-usd 1'

# Codex: exec defaults to a read-only sandbox, so allow workspace writes explicitly
--agent 'codex exec --sandbox workspace-write --ephemeral "$(cat prompt.md) Target: $FANOUT_TARGET"'
```

Rules of thumb that the driver encodes:
- Placeholders such as `{target}` are shell-quoted for you. Inside a double-quoted prompt, use `"$FANOUT_TARGET"` and `"$FANOUT_FEEDBACK"` instead.
- Don't let parallel agents run `git commit`, because they race on `.git/index.lock`. Do the commit in `--on-success`, which runs under one lock: `--on-success 'git add {target} && git commit -qm "migrate {name}"'`.
- Start with `--canary 3`. If any canary fails, the batch stops, and you fix the prompt rather than the targets.
- `bare` mode (`--bare`) needs `ANTHROPIC_API_KEY`, because it doesn't read OAuth credentials.
