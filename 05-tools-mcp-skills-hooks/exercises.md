# Exercises

Offline exercises use `FakeClient` and need no API key. Run tests from the course root with
`.venv/bin/python -m pytest -q 05-tools-mcp-skills-hooks/code`.

---

## 1. Give `payments_search` a cursor that can't lie (offline, 45 min)

**Goal.** The cursor in `query_db_redesign.payments_search` is an integer offset. If new payments arrive between pages, rows shift and the agent sees duplicates or misses rows: the classic offset-pagination bug.

**Steps.**
1. Write a failing test: fetch page 1 (limit 3), insert a newer failed payment, fetch page 2 with the returned cursor, and assert that no payment ID appears on both pages.
2. Replace the offset with a keyset cursor: encode `(created_at, id)` of the last row (base64 JSON is fine) and query `WHERE (created_at, id) < (?, ?)`.
3. Make an invalid cursor return a `ToolError` that says to pass back the cursor exactly or omit it.

**Done when.**
- Your new test passes and all existing tests still pass.
- The cursor is opaque in the response (the model can't usefully edit it).

**Stretch.** Add `payments_search(..., response_format="detailed")` coverage that asserts IDs appear only in detailed mode.

---

## 2. Measure an error message (offline, 40 min)

**Goal.** Show, with the scripted model, which parts of an error message matter.

**Steps.**
1. In a new test file, write three variants of the unknown-group error for `kafka_consumer_lag`: (a) `KeyError: 'ledger-writer'`, (b) `Unknown consumer group 'ledger-writer'. Call kafka_list_consumer_groups.`, (c) the current "Did you mean" version.
2. Extend `scripted_oncall_model` (in your copy) so that when the error names `kafka_list_consumer_groups`, it calls that tool and then picks the closest name from the result.
3. Run `run_agent` with each variant and record `turns`, `stop_reason`, and total result characters.

**Done when.**
- A table in your test docstring shows turns and outcome for (a), (b), (c), and each row is asserted in the test.
- You can explain in one sentence why (b) costs one more turn than (c) and what you'd trade for it (for example, when the listing is too long to suggest a single match).

**Stretch.** Run the same three variants against a real model (`ANTHROPIC_API_KEY` set, `get_client()`) 10 times each and report recovery rate. Label it as your measurement, with n.

---

## 3. Serve the deploy-status MCP server for real (real tooling, 30 min)

**Goal.** Run `deploy_status_mcp.py` under a real MCP host.

**Steps.**
1. In a scratch venv: `pip install "mcp[cli]"`. Don't install it into the course venv.
2. `mcp dev 05-tools-mcp-skills-hooks/code/deploy_status_mcp.py` and call both tools from the Inspector, including an unknown service.
3. `claude mcp add deploy-status -- /path/to/scratch/venv/bin/python /abs/path/deploy_status_mcp.py`, start Claude Code, and ask "did anything ship to ledger-writer in the last hour?"
4. Add a `print("debug")` to a tool, restart, and observe what happens to the stdio stream. Remove it and switch to `logging` on stderr.

**Done when.**
- Claude Code calls `mcp__deploy-status__deploys_status` and quotes the rollout status.
- For an unknown service, the model's next turn uses the suggested name (check the transcript).
- You can describe the `print()` failure mode in one sentence.

**Stretch.** Serve it over Streamable HTTP (`mcp run ... --transport streamable-http`) bound to 127.0.0.1 and register it with `claude mcp add --transport http`.

---

## 4. Trigger-eval the Kafka skill (real coding agent, 60 min)

**Goal.** Find out whether `investigate-kafka-consumer-lag` loads when it should, and only then.

**Steps.**
1. Copy `code/skills/investigate-kafka-consumer-lag/` into a scratch repo's `.claude/skills/`.
2. Write `trigger_prompts.jsonl` with 15 rows `{"prompt": ..., "should_trigger": true|false}`: 5 explicit ("investigate consumer lag on ledger-writer-v2"), 5 implicit ("PagerDuty says ledger-writer is falling behind"), 5 negative controls ("why is my Kafka producer test flaky?", "write a consumer in Go").
3. Run each with `claude -p "<prompt>" --output-format stream-json --verbose` (or your agent's JSON trace mode) and detect whether the skill was loaded from the trace.
4. Compute precision and recall. Change only the `description`, and re-run.

**Done when.**
- You have precision and recall for two description variants, with the raw JSONL results saved.
- The better variant has no negative-control triggers.

**Stretch.** Measure task success with and without the skill on 3 seeded lag scenarios (use the `data/` fixtures as fake `kafka-consumer-groups.sh` output via a stub script on PATH).

---

## 5. Extend the kubectl hook (offline, 45 min)

**Goal.** Harden `hooks/block_kubectl_delete.py` against the next three things an agent might try.

**Steps.**
1. Add failing tests to `test_hook.py` for: `kubectl scale deploy x --replicas=0` in prod (deny), `kubectl drain node-1` in prod (deny), and `alias k=kubectl; k delete pod x` (decide: deny or ask, and justify it in a comment).
2. Fix a real gap: for `KUBECONFIG=~/.kube/prod.yaml kubectl delete pod x`, the hook asks `kubectl config current-context` using the *hook's* environment, not the inline `KUBECONFIG`. Parse leading `VAR=value` assignments and pass them to the lookup. Test it by making the lookup injectable.
3. Implement until green. Keep the deny reasons actionable.

**Done when.**
- All new tests pass, and no existing test changes.
- The hook still runs in under 100 ms for a non-kubectl command (time it with `time`).

**Stretch.** Install it in a real Claude Code project with a kind/minikube cluster whose context is named `prod-local`, and watch Claude react to the deny reason.

---

## 6. Code-as-action with a real sandbox (real tooling, 60–90 min)

**Goal.** Replace `run_code_action`'s `exec` with an isolated executor.

**Steps.**
1. Write `sandbox_exec.py` that runs the model's script in `docker run --rm --network none --memory 256m --cpus 0.5 --read-only python:3.12-slim python -c ...` with a timeout.
2. The bound tools can't be passed as Python functions any more. Expose them as a small HTTP or stdin/stdout RPC that the container can reach (and nothing else), or pre-compute the fixture into a mounted read-only JSON file for this exercise.
3. Run `code_as_action.demo()` against your executor.

**Done when.**
- `import os; os.listdir('/')` works but `open('/etc/hostname','w')` fails, and `urllib.request.urlopen('https://example.com')` fails.
- A `while True: pass` script is killed by your timeout, and the tool result says so.

**Stretch.** Emit a tracer span per bound-tool call from inside the RPC server, so one `execute_python` span has 295 children.

---

## 7. Make one of your CLIs agent-native (your codebase, 2 hours)

**Goal.** Apply [07](07-execution-environments-and-agent-surfaces.md) to a real internal tool.

**Steps.**
1. Pick a CLI agents already call in your team. Grep agent traces (or ask your team) for its three most common failures.
2. Add `--json` to the most-used read command, distinct exit codes for caller vs transient errors, and non-TTY behavior for any prompt.
3. Write an `llms.txt` for its docs.
4. Re-run the three failing cases with an agent.

**Done when.**
- The three failure cases now succeed, or fail with an error that names the fix.
- The change is in a PR with the before/after agent transcripts attached.
