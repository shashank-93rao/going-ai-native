# 02: The five workflow patterns, each with its gate

## The idea

"Building effective agents" names five composable patterns ([Anthropic](https://www.anthropic.com/engineering/building-effective-agents)). Treat them as the standard library of LLM orchestration, much as fan-out, pipeline and scatter-gather are the standard library of service composition:

| Pattern | Shape | Anthropic's "when to use" (verbatim) |
|---|---|---|
| **Prompt chaining** | A → gate → B → gate → C | "the task can be easily and cleanly decomposed into fixed subtasks" |
| **Routing** | classify → one of N handlers | "distinct categories that are better handled separately" |
| **Parallelization** | *sectioning*: split into independent parts. *Voting*: same task n times | "the divided subtasks can be parallelized for speed" (or multiple perspectives are needed for higher confidence) |
| **Orchestrator-workers** | an LLM plans subtasks → workers → merge | "complex tasks where you can't predict the subtasks needed" |
| **Evaluator-optimizer** | generate → evaluate → feed back → repeat | "we have clear evaluation criteria" |

This course adds one rule to each: **name the gate.** Each pattern has a natural place for a code check, and the pattern is only as reliable as that check. All five are implemented in [`code/patterns.py`](code/patterns.py), each in about 20 lines on `ainative_kit`.

## Why it matters

Patterns without gates fail silently, and the failure surfaces three steps later. A chain whose first step produces slightly malformed JSON hands the second step garbage, and the second step writes a fluent summary of the garbage. A router that returns `"networking"` when you only have handlers for `database|deploy|other` either crashes or, worse, gets fuzzy-matched to the wrong handler. An evaluator-optimizer whose evaluator is another LLM asked "is this good?" converges on whatever that LLM likes. Anthropic's harness-design write-up found that agents "reliably skew positive when grading their own work" ([Anthropic, "Harness design for long-running application development"](https://www.anthropic.com/engineering/harness-design-long-running-apps); calibration is covered in [11-llm-as-judge](../11-llm-as-judge/README.md)).

In distributed-systems terms: every inter-stage boundary is an API, and an API without schema validation passes corruption downstream.

## How it works

### 1. Prompt chaining: gate between steps

```python
@dataclass
class Step:
    name: str
    prompt: Callable[[dict[str, str]], str]
    gate: Callable[[str, dict[str, str]], str | None] = lambda out, ctx: None   # None = pass
    retries: int = 1

def chain(client, steps, inputs):
    ctx = dict(inputs)
    for step in steps:
        prompt = step.prompt(ctx)
        for attempt in range(step.retries + 1):
            out = ask(client, prompt, system=step.system, model=step.model)
            reason = step.gate(out, ctx)
            if reason is None:
                break
            prompt = f"{step.prompt(ctx)}\n\nYour previous answer was rejected: {reason}\nFix that and answer again."
        else:
            raise GateFailed(step.name, out, reason)
        ctx[step.name] = out
    return ctx
```

**The gate** returns a *reason string*, not a boolean. The reason goes back into the retry, and it ends up in the exception and the trace. A gate that says "timestamps not present in the log: ['2026-10-16T15:05:00Z']" is a fix instruction. A gate that says "invalid" is not.

**Good gates** are checks code can do cheaply. Is the output valid JSON, and does it match the schema? Is every cited ID, timestamp or file path present in the input (groundedness)? Is it under the length limit? Does it contain the required sections?

### 2. Routing: validate the label in code

```python
def route(client, item, handlers, *, classifier_system, default, model=None) -> Routed:
    raw = ask(client, item, system=classifier_system, model=model, max_tokens=20).strip().lower()
    label = re.sub(r"[^a-z_]", "", raw.split()[0]) if raw else ""
    fell_back = label not in handlers
    return Routed(default if fell_back else label, handlers[default if fell_back else label](item), fell_back)
```

**The gate** is label-set membership. Log the fallback rate: a rising `fell_back` rate is a drift signal, either new input categories or a model change. The classifier is the canonical place for a **cheap model** (`claude-haiku-5-5` in the incident example). Classification is a narrow task, and it runs on every input.

### 3. Parallelization: sectioning and voting

**Sectioning** runs independent subtasks concurrently, using `ThreadPoolExecutor`:

```python
def parallel_sections(sections: dict[str, Callable[[], str]], max_workers=4) -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {name: pool.submit(fn) for name, fn in sections.items()}
        return {name: f.result() for name, f in futures.items()}
```

*Gate:* each section's output is validated on its own, and the merge is code. The sections must really be independent, meaning no section needs another's output. If one does, you have a chain.

**Voting** asks the same question n times and takes the answer that clears a quorum:

```python
def vote(client, prompt, *, n, parse, quorum=0.5, temperature=1.0) -> Vote:
    answers = [parse(client.complete([{"role": "user", "content": prompt}], temperature=temperature).text)
               for _ in range(n)]
    best, count = Counter(answers).most_common(1)[0]
    return Vote(best if count / n > quorum else None, dict(Counter(answers)))
```

*Gate:* the quorum itself. `winner=None` means **abstain and escalate**, which is the useful output. Votes from one model on one prompt are correlated. Voting reduces sampling variance, but it does nothing about a systematic misconception the model holds. For decorrelation, vary the prompt, the model, or the evidence each voter sees. Anthropic's code-review system uses verifier agents that vote on each candidate finding and posts only the consensus ones (see [04](04-clean-context-reviewers.md) and [17-ai-native-engineer-and-team](../17-ai-native-engineer-and-team/README.md)).

### 4. Orchestrator-workers: the plan is data, the cap is code

```python
def orchestrator_workers(client, task, *, plan_system, validate, worker, synthesize, max_subtasks=8, max_workers=4):
    plan = parse_json(ask(client, task, system=plan_system))
    plan = plan.get("subtasks", []) if isinstance(plan, dict) else plan
    good = [p for p in plan if validate(p)]
    dropped = [p for p in plan if not validate(p)] + good[max_subtasks:]
    good = good[:max_subtasks]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        outputs = list(pool.map(worker, good))
    return OrchestratorResult(good, outputs, synthesize(outputs), dropped)
```

What separates this from sectioning is that **the model decides the subtasks at runtime**. That makes the plan untrusted input, so it gets three gates:
- `validate`: each subtask must be well-formed and refer to things that exist. No path traversal, no invented repos.
- `max_subtasks`: a spawn cap enforced in code. Anthropic's research system early on spawned "50 subagents for simple queries" ([Anthropic, multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)).
- `synthesize`: preferably code, or at least a single writer. See [03](03-multi-agent-and-the-single-writer-rule.md).

### 5. Evaluator-optimizer: the evaluator must be a real check

```python
def evaluator_optimizer(generate, evaluate, *, max_rounds=4, stall_rounds=2) -> OptimizeResult:
    attempts, best, since_improved = [], None, 0
    for _ in range(max_rounds):
        cand = generate(attempts)                  # sees all previous attempts and their feedback
        att = Attempt(cand, evaluate(cand))
        attempts.append(att)
        if best is None or att.verdict.score > best.verdict.score:
            best, since_improved = att, 0
        else:
            since_improved += 1
        if att.verdict.ok:
            return OptimizeResult(att, attempts, "passed")
        if since_improved >= stall_rounds:
            return OptimizeResult(best, attempts, "stalled")
    return OptimizeResult(best, attempts, "max_rounds")
```

Three stop rules: pass, budget, and stall. "Two rounds in a row make no progress" is the same stall rule Claude Code's dynamic workflows recommend ([Claude Code docs, workflows](https://code.claude.com/docs/en/workflows)). **The evaluator is the whole pattern.** If it is a compiler, a test suite, a SQL engine plus a reference result, or a schema validator, this pattern hill-climbs reliably. If it is an LLM asked "is this good?", you are optimizing against that LLM's taste. The SQL example ([examples.md](examples.md#3-evaluator-optimizer-sql-generation-with-a-real-checker)) uses SQLite as the evaluator, plus a hidden fixture so the generator can't game it.

## Worked example: reviewing an online schema migration

**Situation.** Engineers submit Postgres migrations, and you want an automated pre-review: is it safe to run online, what does it lock, and what is the rollback?

### Bad: one mega-prompt

```text
Review this migration. Tell me if it's safe to run online, what locks it takes, estimate
how long, write a backfill plan and a rollback plan.
<migration>ALTER TABLE orders ADD COLUMN region text NOT NULL DEFAULT 'eu-west';
CREATE INDEX idx_orders_region ON orders(region);</migration>
```

(illustrative output)
```text
This migration is generally safe. Adding a column with a default is fast in modern Postgres.
The index creation may take some time on large tables. Rollback: drop the column and index.
```

It misses the one thing that matters: `CREATE INDEX` without `CONCURRENTLY` takes a SHARE lock that blocks writes for the whole build. The single prompt mixes five tasks, and the output has no structure to check. There is nothing to gate.

### Good: route, then section, then vote, with gates

```python
# 1. ROUTE by statement type: deterministic first, since sqlglot/pg_query can parse DDL
stmts = parse_ddl(migration)                       # code, not a model
kinds = {classify_stmt(s) for s in stmts}          # {"add_column", "create_index"}

# 2. SECTION: independent analyses in parallel, each with a narrow prompt and a JSON contract
sections = {
    "locks":    lambda: ask(client, LOCKS_PROMPT.format(sql=migration)),     # -> [{"stmt", "lock_mode"}]
    "rollback": lambda: ask(client, ROLLBACK_PROMPT.format(sql=migration)),  # -> {"down_sql": "..."}
}
out = parallel_sections(sections)

# 3. GATES: each output checked against facts code can verify
locks = parse_json(out["locks"])
KNOWN = {"create_index": "SHARE", "create_index_concurrently": "SHARE UPDATE EXCLUSIVE"}
for item in locks:                                  # the model's claim vs a lookup table
    expect = KNOWN.get(classify_stmt(item["stmt"]))
    if expect and item["lock_mode"] != expect:
        raise GateFailed("locks", out["locks"], f"{item['stmt']!r}: expected {expect}")
assert_parses(parse_json(out["rollback"])["down_sql"])   # the rollback must at least be valid SQL

# 4. VOTE on the one binary decision that blocks a deploy, and abstain on disagreement
v = vote(client, SAFE_ONLINE_PROMPT.format(sql=migration, locks=locks), n=5, parse=yes_no)
decision = v.winner or "needs-human"
```

(illustrative output)
```json
{"locks": [{"stmt": "CREATE INDEX idx_orders_region ...", "lock_mode": "SHARE"}],
 "safe_online": "no", "tally": {"no": 5},
 "suggestion": "CREATE INDEX CONCURRENTLY idx_orders_region ON orders(region);"}
```

Each piece is now separately checkable. The lock analysis is checked against a lookup table, the rollback is parsed, and the safety decision has a quorum with an explicit abstain path. When it is wrong, the trace shows which gate let it through.

## Pitfalls

- **Gates that only check format.** Valid JSON with invented content passes a schema check. Add at least one *groundedness* check: every ID, timestamp or path in the output must occur in the input. Detect the gap by asking what invented value would pass your gate.
- **Sectioning dependent work.** If section B's prompt needs section A's answer, the parallel version runs B on a guess. Detect it when B's prompt template references A's output.
- **Voting on a correlated panel.** Five samples of the same prompt at temperature 1.0 share the same blind spots. Detect it by running the vote on known-hard cases: if it is unanimous and wrong, voting isn't buying independence.
- **Unbounded orchestrators.** No `max_subtasks` means the model sets your fan-out, and therefore your bill. Detect it by plotting subtasks per run. A long tail means you need a cap.
- **LLM-only evaluators in evaluator-optimizer.** Detect it with the question "could the generator satisfy this evaluator without being correct?" If yes, add a code check or a hidden test set.
- **Retrying without the reason.** A retry that re-sends the same prompt is a re-roll. Feed the gate's reason back, as `chain` does.

## In your day job

- When you review an LLM pipeline, draw it as a DAG and mark every edge with its gate. An unmarked edge is a finding.
- Route with the cheapest model that passes your routing eval, and alert on fallback rate.
- Before building an evaluator-optimizer, write the evaluator first and prove it can fail on a known-bad input ([07-loops](../07-loops/README.md) calls this "prove the oracle can fail").
- Make `GateFailed.reason` a first-class span attribute in your traces ([15-observability-and-production](../15-observability-and-production/README.md)).
