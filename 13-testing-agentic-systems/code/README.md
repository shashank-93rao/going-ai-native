# Code: testing agentic systems

Everything runs offline. Tests use `FakeClient` with scripted policies. Scripts use `get_client(fake=...)`, so they use the real API when `ANTHROPIC_API_KEY` is set and `AINATIVE_FAKE` is not.

```bash
# from the course root
.venv/bin/python -m pytest -q 13-testing-agentic-systems/code      # 48 tests, about 1 second
```

Scripts must be run with `shared/` on the path (the tests get it from the root `conftest.py`):

```bash
export PYTHONPATH=shared AINATIVE_FAKE=1
.venv/bin/python 13-testing-agentic-systems/code/flaky.py           # flakiness report + transition matrix
.venv/bin/python 13-testing-agentic-systems/code/replay_demo.py     # record/replay and the 4 replay cases
.venv/bin/python 13-testing-agentic-systems/code/mutation_demo.py   # mutation score: agent-written vs spec suite
.venv/bin/python 13-testing-agentic-systems/code/tautology_lint.py  # lint the sample agent-written tests
.venv/bin/python 13-testing-agentic-systems/code/codex_trace.py     # skill-eval checks over codex --json traces
```

## Files

| File | What it is |
|---|---|
| `world.py` | `OpsWorld`: a deterministic simulated ops environment. Two services × staging/prod, tools `get_status`, `get_logs`, `deploy`, `rollback`, `scale`, `delete_deployment`. Seeded `FaultPlan` (transient 503, lost ack, infra crash), idempotency by `request_id`, an action log, and `violations()` invariants |
| `ops_agent.py` | The minimal agent loop (`run_agent`) with `Tracer` spans. Stops on `end_turn`, `step_budget`, or `infra_error` |
| `policies.py` | Scripted "models" for FakeClient. `promote_policy` follows the rules, and each flag injects one bug (`skip_staging`, `skip_verify`, `new_id_on_retry`, `premature_stop`, `delete_prod_first`, `loop_forever`). `noisy_policy(seed)` draws one bug per run |
| `trajectory_checks.py` | Outcome, claim-vs-state, forbidden calls, step budget, promotion order, retry discipline, `first_failure`, and the transition failure matrix |
| `user_sim.py` | τ-bench-style `UserGoal`, `ScriptedUser`, `LLMUser`, `run_conversation`, `audit_user_sim` (leaks, dictated solutions, false stop, turn cap) |
| `flaky.py` | N-trial runner, pass@k / pass^k estimators, Wilson CI, infra-retry on a fresh environment, and a CI verdict (STABLE / FLAKY / BROKEN / ENVIRONMENT) |
| `replay_demo.py` | `RecordingClient` / `ReplayClient` demo, a cassette `.meta.json` sidecar, and `cassette_staleness` |
| `metamorphic.py` | Alert classifier, label-preserving transforms, and brittle vs robust fake models |
| `mutation_demo.py` | AST mutants of `promotion_allowed`, and the mutation scores of an agent-written suite vs a spec suite |
| `tautology_lint.py` | AST lint for tautological tests, with fix hints |
| `codex_trace.py` | OpenAI skill-evals style checks over `codex exec --json` JSONL: forbidden commands, process order, efficiency, negative controls |
| `test_trajectories.py` | Agent vs world: happy path, abort, retries, a negative control per bug, the outcome-only blind spot, the matrix, determinism, infra classification |
| `test_properties.py` | Hypothesis: invariants across seeds × faults, idempotency, fault-equivalence, forbidden calls across noisy seeds, `find()` for the retry bug, paraphrase invariance, and `find()` for the brittle classifier |
| `test_user_sim.py`, `test_flaky.py`, `test_replay.py`, `test_mutation.py`, `test_codex_trace.py` | Tests for the other files |
| `data/codex_trace_*.jsonl` | **Hand-written** traces in the event shape from the Codex non-interactive docs (`thread.started`, `item.started`/`item.completed` with `command_execution` and `agent_message`, `turn.completed` with usage). Not captured from a real run |
| `data/skill_eval_prompts.csv` | Skill-eval cases in the OpenAI post's `id,should_trigger,prompt` format, plus a `trace` column. Row `deploy-03` is the negative control |
| `data/agent_written_test_sample.py.txt` | A hand-written sample of tautological tests (named `.txt` so pytest doesn't collect it) |

## Using a real model
- `flaky.deploy_trial(faults, real=True)` uses `get_client()`, so with a key it runs the real model against the simulated world. The noisy policy is ignored in that case, because the model provides its own variance.
- `replay_demo.record(path)` records a real run when a key is set. `replay()` is always offline.
- Simulated users: pass `LLMUser(get_client(fake=...), goal)` to have a real model play the user. Read [03](../03-deterministic-worlds-and-simulated-users.md) on simulator pitfalls first.
- Real coding-agent traces: `codex exec --json "<prompt>" > trace.jsonl`, then `check_trace(load_events(Path("trace.jsonl")), should_trigger=True)`. For Claude Code, convert `claude -p --output-format stream-json` events into the same `commands()` list (the event names differ; this module doesn't ship that adapter).

No extra packages are needed beyond the course venv (`anthropic`, `pytest`, `hypothesis`).
