# Code for module 14

Everything is stdlib plus `ainative_kit`. The hooks import nothing beyond the stdlib, so you can copy them into any repo's `.claude/hooks/`.

```bash
# from the course root
.venv/bin/python -m pytest -q 14-steering-and-guardrails/code
```

The end-to-end tests in `test_stop_gate.py` create a temporary git repo and run a real pytest oracle, so `git` must be on PATH.

## Files

| File | What it does | Run it |
|---|---|---|
| `validators.py` | JSON-Schema-lite validator (type, enum, ranges, lengths, pattern, items, required, additionalProperties) plus cross-field semantic checks and an evidence-grounding check. Reports *all* errors with paths. | library |
| `repair_loop.py` | Retry-with-feedback around the validator: max attempts, no-progress stop, truncation-specific feedback, tracer spans. The demo triages a Kafka rebalance-storm page. | `python repair_loop.py` (fake offline; real API if `ANTHROPIC_API_KEY` is set and `AINATIVE_FAKE` isn't) |
| `hooks/pre_tool_guard.py` | PreToolUse hook: denies destructive or bypassing commands (`rm -rf /`, force-push to main, `--no-verify`, `reset --hard`, `curl \| sh`, test deselection, reading secrets) and writes to protected paths (secrets, `.git/`, lockfiles, its own hooks/settings/state, the test-approval file). Returns `ask` for pushes and infra changes. Fails closed on unreadable input. | `echo '{"tool_name":"Bash","tool_input":{"command":"git push -f origin main"}}' \| python3 hooks/pre_tool_guard.py` |
| `hooks/test_tamper_check.py` | Diff checker for weakened assertions (`==` to `>=`, `assertEqual` to `assertTrue`, loosened tolerances, widened `pytest.raises`, `ANY`), skips/xfail, commented-out or vacuous assertions, deleted tests, and config exclusions. Human approvals come from `.agent/approved-test-changes.txt`. | `python3 hooks/test_tamper_check.py --diff data/weakened_assertion.diff` (exit 1 on findings) or `git diff HEAD \| python3 hooks/test_tamper_check.py --diff -` |
| `hooks/stop_gate.py` | Stop hook: tamper check plus oracle; `decision: block` with compact failure output; its own per-session budget (the built-in cap resets on tool calls); a "change approach" note on repeated failures; `continue: false` when the oracle is broken or the budget is spent. | Config via env: `STOP_GATE_CMD`, `STOP_GATE_MAX_BLOCKS`, `STOP_GATE_TIMEOUT`, `STOP_GATE_BASE`, `STOP_GATE_TAMPER`, `STOP_GATE_ONE_SHOT` |
| `hooks/unified_diff.py` | Minimal `git diff` parser shared by the tamper check and the drift monitor. | library |
| `drift_monitor.py` | Flags out-of-plan files, scope creep, dependency/CI changes, test deletions, diff-size overruns, edit loops and repeated failures. Verdict ok/warn/stop (exit 0/1/2). `--hook` mode runs as a Stop hook using `.agent/plan.json`: warn goes to the user, stop blocks. | `python drift_monitor.py --plan data/plan.json --diff data/drift_run.diff --events data/run_events.jsonl` |
| `settings.example.json` | Claude Code wiring: `acceptEdits`, narrow allow list, ask for push/infra, deny for secrets and for the guardrails themselves, PreToolUse guard, two Stop hooks. | copy to `.claude/settings.json` and edit |
| `data/` | `weakened_assertion.diff`, `clean_fix.diff`, `drift_run.diff`, `plan.json`, `run_events.jsonl`: the artifacts used in the concept files and tests. | |

## Installing into a repo

```bash
mkdir -p .claude/hooks .agent
cp <course>/14-steering-and-guardrails/code/hooks/*.py .claude/hooks/
cp <course>/14-steering-and-guardrails/code/drift_monitor.py .claude/hooks/
cp <course>/14-steering-and-guardrails/code/settings.example.json .claude/settings.json
echo ".claude/state/" >> .gitignore
```

Then edit `STOP_GATE_CMD` (in `settings.json` → `env`) to your fast test target, and write `.agent/plan.json` per task if you want the drift hook.

## Notes and limits
- `pydantic` isn't in the course venv, so `validators.py` is hand-rolled. In production, use pydantic or `jsonschema` *plus* the semantic checks. The semantic layer is the part libraries don't give you.
- `pre_tool_guard.py` is pattern matching over shell text. It catches overeager mistakes, not an adversary (`bash -c "$(base64 -d ...)"` gets past it). Containment is [Module 16](../../16-security-and-containment/README.md).
- `test_tamper_check.py` is a heuristic over diff lines. Exercise 2 asks you to mutation-test it.
- The stop gate runs the oracle with `PYTHONDONTWRITEBYTECODE=1`. Without it, a same-size edit in the same mtime second (`==` → `>=`) was served stale cached bytecode while this module was being built. A regression test pins this.
