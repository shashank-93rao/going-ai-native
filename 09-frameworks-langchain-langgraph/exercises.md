# Exercises

Exercises 1 to 5 run offline with `FakeClient`. Exercises 6 to 8 need a real API key, or packages not in the course venv (install them in a separate venv, not the course one).

Run tests from the course root with `.venv/bin/python -m pytest -q 09-frameworks-langchain-langgraph/code`.

---

## 1. Break the parity test on purpose (20 min, offline)

**Goal.** See what "the framework changes what the model sees" looks like as a test failure.

**Steps.**
1. In `langgraph_agent.py`, change the `model` node to append `"\nBe concise."` to the system prompt.
2. Run `test_parity.py`. Read which assertion fails first.
3. Revert, then change the `tools` node to put `is_error: False` on every successful tool result.
4. Run again. Decide whether this difference matters to the model, and write one sentence on how you would decide with an eval rather than by opinion.

**Done when.** You have seen both failures, both reverts pass, and you have written the sentence.

**Stretch.** Add a parity assertion on `tools=` (the tool schemas sent on each call).

---

## 2. Add a static breakpoint variant (30 min, offline)

**Goal.** Compare `interrupt()` with `interrupt_before`.

**Steps.**
1. Add a `build_graph(..., static_gate=True)` option that removes the `approve` node, routes risky calls straight to `tools`, and compiles with `interrupt_before=["tools"]`.
2. Since a static breakpoint cannot carry a decision, record approval with `graph.update_state(cfg, {"approvals": {...}})` and then `graph.invoke(None, cfg)`.
3. Write a test that the restart does not happen until `update_state` and resume.

**Done when.** The new test passes, and you can say in two sentences why the docs recommend `interrupt()` for HITL. Hint: what happens on read-only turns with `interrupt_before=["tools"]`?

**Stretch.** Make the static version pause only when a risky tool is pending.

---

## 3. A side effect before the interrupt (30 min, offline)

**Goal.** Feel the "node re-runs on resume" semantics.

**Steps.**
1. In `approve`, before `interrupt()`, call a fake `notify_slack(call)` that appends to a list on `OpsWorld`.
2. Write a test that runs to the interrupt, resumes with accept, and asserts how many Slack notifications were sent.
3. Fix it two ways: (a) move the notification into its own `notify` node before `approve`; (b) keep it in place, but make it idempotent by `tool_use_id`.

**Done when.** The test first fails with 2 notifications, then passes with 1 for both fixes.

**Stretch.** Do the same for a crash: make `tools` raise after the restart call succeeds, resume, and count restarts. Is the `tool_use_id` dedupe enough?

---

## 4. Double texting on OSS (45 min, offline)

**Goal.** Implement one of the four double-texting strategies yourself.

**Steps.**
1. Write `submit(graph, thread_id, message, strategy)` with `strategy in {"reject", "enqueue"}`.
2. "Reject": if `graph.get_state(cfg).next` is non-empty (parked or mid-run), raise `ThreadBusy`.
3. "Enqueue": keep a per-thread `collections.deque` and drain it after each run reaches `next == ()`.
4. Test both with a thread parked at the approval gate and a second alert message arriving.

**Done when.** Both strategies have passing tests, and you have written down which one you would choose for the triage agent, and why.

**Stretch.** Implement "rollback": fork from the thread's first checkpoint and start fresh with the new input. What happens to side effects that already ran?

---

## 5. Add a fourth case and a summary evaluator (30 min, offline)

**Goal.** Extend the eval harness.

**Steps.**
1. Add `ALERT-4214` to `triage_world.py`: `ledger-worker`, symptom "consumer lag 1.2M on ledger.events", with logs showing `CommitFailedException: rebalance in progress` repeating. Decide the correct action (restart, or recommend an owner?) and justify it in the dataset row's `metadata.why`.
2. Extend `scripted_policy` and add the row to `data/triage_cases.jsonl`.
3. Add a summary evaluator `restart_recall` alongside `restart_precision`.
4. Add a test for a deliberately wrong output that drives recall to 0.

**Done when.** All tests pass, and both implementations still score identically.

**Stretch.** Write the LLM-judge evaluator you would use for "DIAGNOSIS is supported by the logs" and list the 3 to 5 labelled traces you would calibrate it on first ([Module 11](../11-llm-as-judge/README.md)).

---

## 6. LangSmith for real (45 min, needs `ANTHROPIC_API_KEY` and `LANGSMITH_API_KEY`)

**Goal.** Run the module's eval as a real LangSmith experiment, and compare raw against LangGraph.

**Steps.**
1. Set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT=oncall-triage`, then run `python langsmith_eval.py` without `AINATIVE_FAKE`.
2. Open both experiments and compare per-example scores, latency and tokens.
3. Run a pairwise evaluation over the two experiment names with `randomize_order=True` and a comparative evaluator that prefers the shorter correct trajectory.
4. Create an annotation queue with a two-key rubric (`diagnosis_supported`, `action_safe`) and review all six runs.

**Done when.** You have two experiments, one pairwise result, and six reviewed queue items, plus a note on any case where the raw and LangGraph runs differed with a real model, and why. (Hint: sampling. Run each configuration several times before you conclude anything; [Module 12](../12-hill-climbing/README.md).)

**Stretch.** Configure an online evaluator filtered to traces that called `restart_service`.

---

## 7. Port to `create_agent` with middleware (60 min, needs `langchain` and `langchain-anthropic` in a separate venv)

**Goal.** Reproduce the triage agent with LangChain's prebuilt agent and check what changed.

**Steps.**
1. Implement the three tools with `@tool`, and build the agent from [02](02-langchain-essentials.md): `TurnBudget`, `ToolRetryMiddleware` and `HumanInTheLoopMiddleware(interrupt_on={"restart_service": {...}})`, with a checkpointer.
2. Trace one run per alert to LangSmith.
3. Diff the system prompt and tool schemas in the trace against `triage_world.py`.
4. Run the eval harness against the new target.

**Done when.** The eval runs, and you have a written list of every difference between the `create_agent` request and the raw request, each marked "harmless" or "needs an eval", with the reason.

**Stretch.** Add `SummarizationMiddleware` and find the shortest conversation that makes it drop a log line the diagnosis depends on.

---

## 8. Deep Agents ablation (90 min, needs `deepagents` and an API key)

**Goal.** Measure whether the Deep Agents components help a short-horizon agent.

**Steps.**
1. Build the four configurations from the table in [06](06-deep-agents-and-ambient.md): baseline, then + todos, + filesystem offload, + log-digger subagent.
2. Run each configuration 5 times on the 3-case (or, after exercise 5, 4-case) dataset.
3. Record pass rate, mean turns and mean tokens per configuration.

**Done when.** You have a table of results with the number of trials, and a one-paragraph conclusion that says which components you would keep and states the uncertainty.

**Stretch.** Make the task longer (triage five correlated alerts in one run) and repeat. Does the answer change?
