# 07-loops code

Everything here runs offline. Model calls go through `ainative_kit`; with no `ANTHROPIC_API_KEY`
(or with `AINATIVE_FAKE=1`) the scripts fall back to scripted `FakeClient`s. Run commands from
the course root.

```bash
.venv/bin/python -m pytest -q 07-loops/code          # all tests, offline (~30 s; many spawn pytest)
```

| File | What it is | Run it |
|---|---|---|
| `agent_loop.py` | The agent loop from scratch: tools, message accumulation, `stop_reason` handling, a completion gate (a Stop-hook analogue with an 8-block cap), governors and a JSONL trace | `PYTHONPATH=shared .venv/bin/python 07-loops/code/agent_loop.py` |
| `governor.py` | `Limits`, `Governor`, typed `ExitCode`s: iteration cap, token and dollar budgets, wall clock, consecutive-error breaker, repetition detection (sliding window, catches A-B-A-B), no-progress on the oracle metric, stop file | imported by the others |
| `oracle.py` | `PytestOracle`, `CommandOracle`, agent-friendly failure summaries, and `prove_it_can_fail()` (mutation-test the oracle before you loop on it) | `PYTHONPATH=shared .venv/bin/python 07-loops/code/oracle.py` |
| `ralph.py` | Fresh-context Ralph driver: same `PROMPT.md` each iteration, a new agent process each time, `fix_plan.md` + `specs/` on disk, commit on progress, revert on regression or false "done", typed exit codes | see below |
| `ralph.sh` | The same idea in ~60 lines of bash, for reading and for copying into a container | see below |
| `self_correct.py` | Generate → verify → fix, plus `measure()`: pass rate by round for external feedback vs bare "review your work", with token cost | `PYTHONPATH=shared .venv/bin/python 07-loops/code/self_correct.py` |
| `examples/toy_task/` | A buggy token-bucket rate limiter (`workspace/`), its spec (`spec_tokenbucket.py`, the oracle), a weak oracle (`spec_smoke.py`), `fix_plan.md`, `specs/`, `PROMPT.md`, FakeClient scripts, mutants, and `fake_ralph_agent.py` (a stand-in for `claude -p`) | used by tests and demos |

## The toy task

`examples/toy_task/workspace/tokenbucket.py` has two seeded bugs: `>` instead of `>=` in
`try_acquire` (FP-1) and a refill that is not capped at capacity (FP-2). The oracle starts at
`FAIL 3/5`. `pytest` ignores `examples/` (see `conftest.py`) because those spec files are meant
to fail until an agent fixes the code.

## Ralph against the toy task, offline

```bash
C=$PWD/07-loops/code
cp -r $C/examples/toy_task/workspace /tmp/ralph-ws && cd /tmp/ralph-ws && git init -q
FAKE_AGENT_MODE=fix PYTHONPATH=$C/../../shared python $C/ralph.py --workspace . \
  --agent-cmd "python $C/examples/toy_task/fake_ralph_agent.py" \
  --oracle-cmd "python -m pytest -q spec_tokenbucket.py"
echo "exit=$?"; git log --oneline
```

`FAKE_AGENT_MODE` can be `fix`, `noop`, `lie`, `regress`, `crash` or `blocked`, to watch each governor trip.

## Ralph with a real agent

Swap the fake for a real headless agent. Do this only in a container or disposable VM, because
skipping permissions lets the agent run anything:

```bash
python $C/ralph.py --workspace . \
  --agent-cmd "claude -p --dangerously-skip-permissions --max-turns 40 --max-budget-usd 3" \
  --oracle-cmd "python -m pytest -q spec_tokenbucket.py" --max-iterations 10 --max-hours 2
```

`--max-turns` and `--max-budget-usd` are Claude Code print-mode flags (checked against the CLI
reference on 2026-10-19). They give you a per-iteration governor inside the agent, on top of the
per-loop governor in `ralph.py`.

`ralph.sh` reads the same settings from the environment:

```bash
AGENT_CMD="python $C/examples/toy_task/fake_ralph_agent.py" FAKE_AGENT_MODE=fix \
ORACLE_CMD="python -m pytest -q spec_tokenbucket.py" bash $C/ralph.sh; echo "exit=$?"
```

## Prices

`governor.Prices` defaults ($3 input / $15 output per million tokens) are placeholders that make the
dollar budget testable. Set them from the current pricing page for your model before you rely on a
dollar cap.
