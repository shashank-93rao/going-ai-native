# Examples: frameworks in practice

Five scenarios from a payments platform team. Model outputs not produced by this module's code are marked *(illustrative output)*.

---

## 1. The approval that outlived the pod

**Situation.** Your team runs the triage agent as a Kubernetes worker that consumes PagerDuty webhooks. It asks for approval before `restart_service` by posting to Slack and polling a Redis key. On-call approves 25 minutes later. The worker was evicted during a node drain 10 minutes in.

**Naive approach and what happens.** The run state lived in the worker's memory. The approval key sits in Redis with nothing waiting on it. PagerDuty re-fires the alert, a new run starts from scratch, re-reads logs, and asks again. The on-call sees two approval requests for the same incident and approves both. If the second run had chosen a different action, you would have had two conflicting mutations.

**AI-native approach.**
1. Port the loop to the graph in `code/langgraph_agent.py`. The `approve` node calls `interrupt()` with an Agent-Inbox-style payload.
2. Use `PostgresSaver` as the checkpointer, and set `thread_id = f"pd-{incident_id}"`. That makes the incident id the partition key.
3. The Slack button handler, in any process, calls `graph.invoke(Command(resume={"type": "accept"}), {"configurable": {"thread_id": ...}})`.
4. Dedupe at the trigger: if `graph.get_state(cfg).next` is non-empty, the incident already has a live run, so post "already triaging" instead of starting another.
5. Pass `tool_use_id` to the restart API as an idempotency key.

```python
cfg = {"configurable": {"thread_id": f"pd-{incident_id}"}}
if graph.get_state(cfg).next:          # parked or running: do not start a second run
    return "already triaging"
graph.invoke({"alert_id": alert_id, "messages": [...]}, cfg)
```

**What to check.**
- Kill the worker while a run is parked, then resume from another pod. The run completes, and the model is called once more, not four times (`test_resume_from_a_fresh_graph_uses_the_checkpoint_not_the_model`).
- Replay from the checkpoint before `tools`, and confirm the restart count is unchanged.

---

## 2. "The framework changed our prompt"

**Situation.** A teammate migrated the agent to `create_agent` with three middlewares. A week later, the agent recommends restarts on capacity alerts about 1 time in 10 *(illustrative)*. Nothing in your diff touched the prompt.

**Naive approach and what happens.** You add "NEVER restart for capacity problems" in capitals to the system prompt. It gets better for a few days. Nobody knows why it broke or why it got better.

**AI-native approach.**
1. Enable LangSmith tracing (`LANGSMITH_TRACING=true`) and open one failing trace. Read the `llm` run's actual inputs.
2. Diff them against the raw agent's request. The raw version is still in the repo, and its parity test shows exactly what it sends.
3. Typical findings: a summarization middleware compressed the `query_logs` result and dropped `disk usage 97%`, so the model saw only "WARN retention not set". Or a dynamic-prompt middleware placed its text *after* your constraints.
4. Fix the cause (summarise only messages older than N turns, and never tool results from the current turn). Add an eval case built from that trace through an annotation queue's "Add to Dataset".

**What to check.**
- The parity test, extended to the `create_agent` version: system prompt and tool schemas match `triage_world.py`.
- The `no_forbidden_tools` evaluator on the capacity case passes across repeated trials, not just once.

---

## 3. "What if we'd said no?": building eval cases with time travel

**Situation.** Post-incident review for ALERT-4211. The restart cleared the symptom but hid the leak for two more days. The reviewer asks what the agent would have done if the human had rejected the restart.

**Naive approach and what happens.** Someone writes a new prompt that simulates a rejection and runs it from scratch. It is a different run: different log timestamps, different model sampling. It answers a different question.

**AI-native approach.**
1. Load the incident thread and find the checkpoint where `next == ("approve",)`.
2. Fork: `graph.invoke(None, snap.config)` re-raises the interrupt. Resume with `{"type": "response", "args": "not during peak"}`.
3. Point the forked run at a scratch Store namespace, because the Store is not rolled back by a fork (`test_store_is_cross_thread_and_not_rolled_back_by_time_travel`).

Real output from `python langgraph_agent.py`:

```text
== 3. time travel: fork before approval, replay with a rejection ==
re-paused: True
DIAGNOSIS: checkout-api connection pool exhausted by a leak in OrderRepository.findOpen.
ACTION: restart was rejected by the on-call human; paging checkout-api owners.
restarts (unchanged, fork never restarted): ['checkout-api']
```

**What to check.**
- The fork has the same messages up to the gate as the original (same tool results, same log lines).
- Add both branches to the dataset as cases for "behaviour after rejection" ([Module 13](../13-testing-agentic-systems/README.md)).

---

## 4. Picking an SDK for the dependency-upgrade bot

**Situation.** Platform wants a bot that bumps library versions across 40 Go and Java services, runs the tests, and opens PRs. Someone proposes reusing the triage agent's LangGraph setup.

**Naive approach and what happens.** You write `read_file`, `write_file`, `run_tests` and `git` tools as graph tools. Two weeks in you are implementing context compaction, because `go test ./...` output overflows the window. You are rebuilding Claude Code, badly.

**AI-native approach.**
1. Ask the three questions. Gate: block `git push` to protected branches and network egress. Paused state: none needed, because runs are minutes long and restartable from scratch. Visibility: traces for review, without a byte-level parity requirement.
2. Choose the Claude Agent SDK. Use built-in file and bash tools in a sandbox, a `PreToolUse` hook on `Bash` that denies `git push origin main`, `disallowed_tools=["WebFetch"]`, and `max_turns=60`.
3. Each service is one session. Fan out with a plain job queue, not with an agent framework.

```python
async def deny_protected_push(input_data, tool_use_id, context):
    cmd = input_data["tool_input"].get("command", "")
    if "git push" in cmd and any(b in cmd for b in ("main", "master", "release/")):
        return {"hookSpecificOutput": {"hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": "Push to a feature branch and open a PR instead."}}
    return {}
```

**What to check.**
- A test prompt that tries to push to main is denied, and the denial reason reaches the model.
- Pass rate on a seeded set of 10 upgrade tasks, with and without the hook ([Module 08](../08-harness-engineering/README.md)).

---

## 5. Online evals on the restart path

**Situation.** The triage agent is live. Restarts are rare (about 2% of runs) but high-stakes. Product wants a quality dashboard.

**Naive approach and what happens.** You enable an LLM-judge online evaluator on all traces at a 10% sample. Restarts are 2% of traffic, so a 10% sample yields about 0.2% of runs: a handful of restart traces a week, scored by an uncalibrated judge. The dashboard is green and means nothing.

**AI-native approach.**
1. Add two online evaluators with filters. **Filter `tool = restart_service`, sample 100%**: a code evaluator checks that the log lines in the trace match an approved restart pattern (pool exhaustion, wedged process). **All other traces, sample 5%**: a calibrated judge checks that the `DIAGNOSIS:` line is supported by the tool outputs ([Module 11](../11-llm-as-judge/README.md)).
2. Add an automation: every restart trace goes to an annotation queue for the owning team. Reviewed items go to the `oncall-triage` dataset.
3. Keep the offline gate: `evaluate_locally` on the golden set in CI, before any prompt or model change ships.

**What to check.**
- The restart-path evaluator has a test with a known-bad trace (`test_evaluators_catch_a_bad_restart`).
- The weekly count of reviewed restart traces equals the weekly count of restarts.
