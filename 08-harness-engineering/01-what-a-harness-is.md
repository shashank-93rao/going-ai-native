# 01: What a harness is, and whether context is enough

## The idea
An agent's result is a function of six things. Only one of them is the model:

| Part | What it is | Who controls it in a coding agent |
|---|---|---|
| **Model** | Weights, plus knobs such as reasoning effort | The vendor, and you choose which one |
| **Prompt** | System prompt and the task prompt | The agent product (Claude Code, Codex) plus you |
| **Tools** | What the agent can do: read, edit, run, search, query | The product, plus the CLIs, scripts and MCP servers you add |
| **Context** | What the agent can know: files, docs, retrieved snippets, tool output | **You, through the repo** |
| **Verifiers** | What tells it, and you, whether the work is right: tests, lints, type checks, judges | **You, through the repo and CI** |
| **Environment** | Where it runs: sandbox, worktree, services, data, logs | **You, through dev tooling** |

The **harness** is everything except the weights. When you use an off-the-shelf coding agent, the vendor owns the loop and the base prompt. The remaining parts are yours, and they live in your codebase: context, the extra tools, verifiers and environment. **Harness engineering, in a codebase, is the work of making those four parts good enough that the agent can work without you.**

This module organizes that work into three pillars by the question each answers for the agent:
1. **Understand**: what is this system, what must not break, and where do I make the change?
2. **Verify**: is my change correct, judged by something other than my own opinion?
3. **Diagnose**: something is wrong; where, and why?

## Why it matters
Two published results put a number on the harness.

- **LangChain, February 2026.** They held the model fixed (gpt-5.2-codex) and changed only the harness. Their deepagents-cli went from **52.8% to 66.5%** on Terminal-Bench 2.0, which moved it from outside the top 30 to the top 5. The changes were all harness-side:
  - a middleware that forces a verification pass against the task spec before the agent may exit;
  - a startup step that maps the directory and locates tools;
  - a loop detector that intervenes after N edits to the same file;
  - time-budget warnings;
  - a "reasoning sandwich" of high effort to plan and verify and lower effort to implement.

  Running at the highest reasoning effort everywhere scored *worse* (53.9%) because of timeouts ([LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)).
- **OpenAI's "Harness engineering" post, February 2026.** A team that grew from three to seven engineers reports shipping an internal product of roughly a million lines and about 1,500 merged PRs over about five months, with no hand-written code. The engineers' work moved to the environment ([OpenAI](https://openai.com/index/harness-engineering/)):
  - an AGENTS.md of about 100 lines that serves as a map into a versioned `docs/` directory;
  - custom lints whose error messages carry remediation instructions;
  - a strict layered architecture enforced mechanically;
  - an app instance and an observability stack per worktree, which the agent queries with LogQL and PromQL;
  - recurring cleanup agents.

  These are reported results from one team, not a controlled experiment. The *techniques* are what transfer.

Anthropic's infrastructure-noise study adds a sobering detail. On Terminal-Bench 2.0, resource configuration alone moved scores by about 6 points ([Anthropic, "Quantifying infrastructure noise"](https://www.anthropic.com/engineering/infrastructure-noise)). The environment is part of the result whether you engineer it or not.

## How it works: the full answer to "is context enough?"

### What each pillar unlocks
Map the three things you want agents to do independently against the pillars they require:

| Agent capability | Understand | Verify | Diagnose | What fails without the missing pillar |
|---|---|---|---|---|
| **Build a feature** | required | required | helpful | Without Verify, it ships code that compiles and violates an invariant. Without Understand, it builds in the wrong layer or misses the constraint. |
| **Fix a known bug** (repro given) | required | required | helpful | Without Verify, it "fixes" by editing the test. |
| **Identify a problem** (symptom only) | required | required | **required** | Without Diagnose, it guesses from code reading and fixes a plausible bug that is not the one in the logs. |
| **Fix a production-style incident** | required | required | **required** | Same as above, plus it cannot confirm the fix addresses the observed evidence. |

So the honest answer to the question has three parts:

1. **Context is necessary but not sufficient.** It answers "what" and "where". It cannot answer "is this right?", which is a verifier's job, or "what actually happened?", which takes queryable evidence.
2. **"Independently" means without a human acting as the verifier.** Every check you leave in your head is a point where the agent has to stop and ask, or proceed on a guess. Harness engineering is the work of moving those checks out of your head and into the repo.
3. **"Enough" is empirical.** It depends on the codebase, the task class and the model. You find out by running a seeded suite and computing an autonomy rate ([05](05-measuring-autonomy-rate.md)). A harness that gives 90% on features and 30% on incidents tells you exactly where to keep a human, and what to build next.

### What stays human even with a great harness
- **Ambiguous intent.** "Make checkout feel faster" has no oracle until someone writes one, such as a p95 budget.
- **Novel architecture.** Deciding to replace the outbox with CDC is an ADR-level judgment. Agents can draft the ADR, but the decision is yours.
- **Evidence outside the harness.** An incident caused by a partner's API change is invisible if partner responses are not logged anywhere the agent can query.
- **Invariants nobody wrote down.** If "a customer is charged at most once" exists only as tribal knowledge, the agent cannot preserve it, and neither can your next hire.

Each of these is a *harness gap* rather than a law of nature. The skill is noticing which gaps are worth closing.

### Decision rule
> **Synthesis:** for each task class, grant autonomy in proportion to the strength of its verifier. If a hidden-test-style check exists and the autonomy rate on that class is high, let agents run and review by risk tier. If the verifier is weak, use agents for the draft and keep the human as the verifier. If the class has no verifier, build one first; that is the highest-leverage harness work you can do.

## Worked example: a detailed prompt vs a harness, on the same feature
You have been using AI "mostly with detailed prompts", so start there. The task is `feat-currency` from this module's suite: add a `currency` field to `create_order`.

### Version A: a detailed prompt, thin repo
```text
Add currency support to create_order in orders/api.py. Signature:
create_order(conn, idem_key, customer_id, amount_cents, currency="USD").
Validate ISO 4217 (3 uppercase letters), raise OrderError otherwise. Add a
currency column to the orders table with DEFAULT 'USD'. Include currency in the
response dict, in get_order, and in the OrderPlaced outbox payload. Keep the
existing tests passing and add tests for the new behaviour.
```
This is a good prompt by most standards. The agent does exactly what it says. The diff touches `db.py` and five places in `api.py`, adds a test, and `pytest` is green. Here is that diff graded by the eval (the edits are this suite's `naive` variant; the grading output is real):

```text
$ python autonomy_eval.py --agent "{python} {here}/fake_agent.py --policy naive {workdir} {prompt}" --tasks feat-currency
task                       kind      ok   hidden  visible  lint  tamper  secs
feat-currency              feature   FAIL False   True     True  -       1.4
```
Visible tests pass, the lint is clean, and it is still wrong. The hidden test that fails:

```text
E   Failed: DID NOT RAISE IdempotencyConflict
FAILED _hidden_tests/test_hidden.py::test_same_key_different_currency_conflicts
```
The agent never added `currency` to the `body` dict that feeds `request_hash`. A client that retries `k1` with JPY instead of USD silently gets the USD order back. That is a correctness bug in an idempotent API, and no amount of prompt detail about *this feature* would have caught it. You would have had to remember invariant I2 while writing the prompt, every time, for every feature.

### Version B: the same short prompt, harnessed repo
The prompt shrinks to the requirement itself (the `prompt` in `tasks/feat-currency/task.toml`). The knowledge moved into the repo:

- `orders/AGENTS.md`, loaded when the agent works in `orders/`:
  ```markdown
  - `request_hash` covers client-supplied body fields only. Adding a request field?
    Add it to `body`, or retries with a different value will silently replay (I2).
  ```
- `INVARIANTS.md` I2 names its typical break: "a new request field is left out of `body`".
- The hidden test plays the role your CI's contract test should play. Exercise 3 asks you to promote it to a visible test.

With those in place, the reference diff adds one more line:
```python
    body = {"customer_id": customer_id, "amount_cents": amount_cents, "currency": currency}
```
and the eval passes:
```text
feat-currency              feature   PASS True    True     True  -       1.41
```

### Why B is the better engineering
- The invariant is written once, next to the code it governs, and is loaded only when relevant (progressive disclosure, [02](02-pillar-understand.md)).
- It survives across sessions, engineers and models. A detailed prompt survives one session.
- It can be checked: a contract test or a lint can enforce it, while a prompt can only request it.

## Pitfalls
- **Treating the harness as "the prompt, but longer".** *Detect it* when your AGENTS.md is past a few hundred lines and reads like a style guide. Move rules that can be checked into lints and tests, and keep the file as a map.
- **Crediting the model for harness gains, or the reverse.** *Detect it* when you change the model and the harness in the same week and report one number. Vary one axis at a time ([12-hill-climbing](../12-hill-climbing/README.md)).
- **Assuming that passing visible tests means done.** *Detect it* by grading a sample of agent PRs against hidden or post-hoc tests. If the visible-pass rate is much higher than the hidden-pass rate, your visible tests under-specify the invariants.
- **Building pillar 1 only.** Docs are the easiest pillar to write and the easiest to feel good about. *Detect it* by running incident-type tasks. If the autonomy rate is near zero on those while features look fine, you are missing Diagnose.

## In your day job
- List the three to five invariants of your most critical service, the ones you would check by hand in review. For each, write down what currently enforces it. Most will say "me".
- Take the last agent PR you rejected and classify the root cause: missing context, missing verifier, or missing evidence. That tells you which pillar to build first.
- Stop pasting the same background into prompts. If you have typed it twice, it belongs in the repo.
