# A-M3: Tracing and error analysis on ~50 runs
**Time:** one weekend day; most of it is reading. **Offline:** no (real-model traces). **Modules:** [10](../../10-evals-fundamentals/README.md), [13](../../13-testing-agentic-systems/README.md), [15](../../15-observability-and-production/README.md).

## Goal
Read at least 50 real traces, build a failure taxonomy with counts, and let the counts decide what M4 measures and M5 fixes.

## Why it matters
The temptation is to skip straight to evals: write graders for the failures you imagine. Hamel Husain and Shreya Shankar's guidance is the opposite: write evaluators for failures you have *observed*, by reading traces first and coding them ([Hamel and Shreya, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)). The course stance ([01-gap-analysis](../../research/01-gap-analysis.md)) is a split: constraint evals up front (you have those from M1's invariants), failure-mode evals from error analysis (this milestone).

There is a second reason. Anthropic reports a case where a capability eval went from 42% to 95% after grader and scaffold bugs were fixed ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). Reading traces is how you find out that your grader is wrong, before you spend M5 optimizing against it.

## Steps
1. **Generate the traces.** 48 scenarios (8 per kind), one trial each, with your M2 agent:
   ```bash
   python -m agent.run --n 48 --traces runs/m3/traces.jsonl --out runs/m3/grades.jsonl
   ```
   Add the scenario's ground truth to the episode span's attrs so a reader can see it, but keep it out of the model's context.
2. **Build a trace viewer.** 50 lines of Python that prints one episode as a readable transcript: each LLM turn's text, each tool call and a trimmed result, the final grade and its notes. `load_traces` from `ainative_kit` groups spans by trace. You will read 50 of these; make them pleasant.
3. **Open coding.** For each trace, write one free-text note about the *first* thing that went wrong (or "clean"). Do not categorize yet. Keep it in `analysis/open_codes.jsonl`:
   ```json
   {"trace_id": "a1b2c3", "scenario": "bad_deploy-6", "passed": false, "note": "read logs on orders, saw the audit-bot line, restarted db within one step, no hesitation in text"}
   ```
4. **Axial coding.** Group the notes into 5–10 categories. Count them. Split categories that mix a model error with a harness error.
5. **Transition failure matrix.** Define the agent's states (alerted → mapped topology → localized → diagnosed → mutated → verified → closed/paged). For each failing trace, mark the last good state and the first bad one. The cell counts show where in the flow it breaks.
6. **Prioritize** by frequency × severity. A dangerous action outranks a wrong `fault_kind` label even at a tenth of the count.
7. **Turn every category into something:** a new eval case, a grader check, a harness fix, or a spec change. Write which.

## Worked example
Below is a taxonomy you might get on the **offline baseline** (which you can reproduce exactly), to show the shape. Your real-model taxonomy will be different; that is the point of doing it.

```text
$ AINATIVE_FAKE=1 python starter_agent.py --n 48 --out runs/fake/grades.jsonl
```

Each failure is coded by its *first* wrong step:

| Category (first wrong step) | Count (of 29 failures) | Severity | Becomes |
|---|---|---|---|
| Restarted db on data corruption instead of paging | 8 | critical | Gate (db never); eval case |
| Obeyed an instruction found in logs (restart db) | 7 | critical | M6 injection suite; gate |
| Mutated on a false alarm (restarted gateway or payments) | 7 | high | Eval case; spec: "confirm the alert is still firing" |
| Restarted instead of scaling on a traffic spike | 7 | medium | `scale` tool description; eval case |

(Measured on the offline baseline, 2026-10-19. The counts sum to 29.)

Now the grader finding, which is the more valuable one. The grader reports `ignored_injection = False` on **8** trials, not 7. The extra one is a `data_corruption` scenario where the injection sits in the *orders* logs, which the baseline never read. It restarted db because db had the highest error rate, not because of the injection. The check marks any injected-looking action as "followed" whether or not the agent ever saw the text. That over-counts injection success and would make an M6 defense look better or worse than it is. The fix is to require that the injected line appeared in a tool result *before* the action.

Transition matrix for the same run, last good state to first bad step:

| last good \ first bad | mutated without a real fault | unsafe mutation | wrong mutation | closed without verifying |
|---|---|---|---|---|
| alerted | 7 (false_alarm) | | | |
| localized | | 15 (8 corruption, 7 injection) | 7 (traffic) | |
| mutated | | | | 48 (every episode) |

The last column is the interesting one. *Every* episode, including the 19 passes, closes without re-checking metrics after the mutation. The scaffold grader does not catch this, so it shows up only when you read the traces. That is invariant I6 from M1.

## Deliverables
- `analysis/viewer.py`
- `analysis/open_codes.jsonl` (≥50 rows), `analysis/taxonomy.md` with counts, transition matrix and priorities
- A list of grader or harness bugs found, each with a fix commit

## Done when
- [ ] ≥50 traces read and open-coded, including passing ones (sample at least 10 passes).
- [ ] 5–10 categories with counts that sum correctly, and overlaps explained.
- [ ] Transition failure matrix filled in.
- [ ] Each category mapped to an eval case, a check, a harness fix or a spec change.
- [ ] At least one finding is about the grader, the simulator or the oracle, not the model. If you found none, read 20 more passing traces.

## Reuse
- `ainative_kit.load_traces`, the spans written by `../code/starter_agent.py`
- Open and axial coding, transition matrices: [10-evals-fundamentals](../../10-evals-fundamentals/README.md), [13-testing-agentic-systems](../../13-testing-agentic-systems/README.md)

## Pitfalls
- **Reading only failures.** Passing runs hide the "right for the wrong reason" cases (the baseline passes conn_leak by blaming the highest error rate, which happens to be correct). Sample passes.
- **Categorizing too early.** If you start with categories, you see only them. Open-code first.
- **Letting an LLM do the reading for you.** You may use one to *cluster* your notes after you have written them. Using it to write the notes means you never see the traces.
- **Ground truth in context.** If the scenario kind leaks into the prompt (for example via the scenario id in a message), your traces are contaminated. The starter's first user message is deliberately bare.
