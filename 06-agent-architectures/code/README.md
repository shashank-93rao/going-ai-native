# Module 06 code

Everything runs offline. The scripts use `get_client(fake=...)`: with `ANTHROPIC_API_KEY` set (and `AINATIVE_FAKE` unset) they call the real API, and otherwise they use a deterministic fake. **The fakes stand in for the model only.** Every gate, checker, cap, log fold and policy is real code.

## Run the tests

From the course root:

```bash
.venv/bin/python -m pytest -q 06-agent-architectures/code
```

## Run the scripts

The scripts import `ainative_kit` from `shared/`, so put it on the path (or `pip install -e .` from the root):

```bash
cd 06-agent-architectures/code
export PYTHONPATH=../../shared AINATIVE_FAKE=1     # drop AINATIVE_FAKE to use the real API
../../.venv/bin/python incident_summary.py         # routing + chaining with gates
../../.venv/bin/python dependency_audit.py         # orchestrator-workers over data/repos
../../.venv/bin/python sql_optimizer.py            # evaluator-optimizer, SQLite as the evaluator
../../.venv/bin/python single_writer.py            # broken multi-writer vs single writer
../../.venv/bin/python reviewer.py                 # clean-context reviewer with evidence gate
../../.venv/bin/python run_log.py                  # crash after a side effect, resume, one ticket
../../.venv/bin/python double_texting.py           # every policy over two arrival patterns
```

With a real key, `sql_optimizer.py` and `single_writer.py` still use their scripted attempts and coder, because their demos replay a fixed story. `incident_summary.py`, `dependency_audit.py` and `reviewer.py` send their real prompts to the model.

## Files

| File | What it is | Concept |
|---|---|---|
| `patterns.py` | `Augmented`, `agent_loop`, `chain` (+`GateFailed`), `route`, `parallel_sections`, `vote`, `orchestrator_workers`, `evaluator_optimizer` | [01](../01-augmented-llm-and-workflows-vs-agents.md), [02](../02-five-workflow-patterns.md) |
| `incident_summary.py` | Route by incident type with the cheap model, then a two-step chain with groundedness gates; duration computed in code | [examples #1](../examples.md#1-incident-summary-routing--prompt-chaining) |
| `dependency_audit.py` | LLM planner, validated and capped plan, read-only extraction workers, deterministic advisory match, single-writer report | [examples #2](../examples.md#2-orchestrator-workers-cross-repo-dependency-audit) |
| `sql_optimizer.py` | Guard, EXPLAIN, VM-step budget, column contract, reference results on visible and hidden fixtures | [examples #3](../examples.md#3-evaluator-optimizer-sql-generation-with-a-real-checker) |
| `single_writer.py` | `Repo` with compare-and-set, parallel writers (blind and OCC), single writer with read-only helpers, `undefined_calls` check | [03](../03-multi-agent-and-the-single-writer-rule.md), [examples #4](../examples.md#4-a-broken-multi-writer-design-and-the-fix) |
| `reviewer.py` | `build_review_request(spec, diff)`, evidence gate, severity filter in code, `vote_findings` | [04](../04-clean-context-reviewers.md) |
| `run_log.py` | `EventLog` (torn-tail tolerant), `fold`, `DurableRun` with checkpoints, intents, idempotency keys, `InDoubt`, `TicketAPI` | [05](../05-durable-runs-event-sourcing-idempotency.md) |
| `double_texting.py` | Discrete-time simulator: reject / enqueue / interrupt / rollback / adaptive / concurrent (±OCC), `validate_transcript` | [06](../06-double-texting-and-concurrency.md) |
| `test_patterns.py` | Unit tests for every pattern, including a barrier test proving that sectioning really runs concurrently | |
| `test_examples.py` | Incident gates, audit coverage and plan validation, SQL checker (fan-out, boundary, hard-coding, cost budget) | |
| `test_single_writer_and_reviewer.py` | Write skew under OCC, lost update vs OCC, single-writer correctness, reviewer isolation and filters | |
| `test_durability.py` | Crash matrix (parametrized), no re-sampling on resume, in-doubt, torn writes, checkpoint == full fold, every double-texting policy, and a hypothesis property that serializing policies never corrupt the transcript | |
| `data/` | `incidents.jsonl`, `repos/*/` manifests, `advisories.json` (course fixtures, not real advisory data) | |

No packages beyond the course venv are needed: `sqlite3` is in the standard library, and `hypothesis` is already installed.
