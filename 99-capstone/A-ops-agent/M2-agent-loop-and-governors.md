# A-M2: Agent loop with tools and governors
**Time:** one weekend day. **Offline:** tests yes; real-model runs need a key. **Modules:** [07](../../07-loops/README.md), [05](../../05-tools-mcp-skills-hooks/README.md), [01](../../01-llms-for-systems-engineers/README.md), [06](../../06-agent-architectures/README.md), [03](../../03-context-engineering/README.md).

## Goal
Turn `starter_agent.py` into an agent you would trust to run unattended for one episode: a real model, tools whose results and errors help it, and governors that stop it before it burns budget or loops.

## Why it matters
Governors are what make a loop safe to leave alone. A model that keeps calling the same tool is the agent equivalent of a retry storm. Without a cap it does not fail; it just keeps spending. Module 07 covers the mechanics. Here you size them from data instead of guessing.

## Steps
1. **Run the starter with a real model** on 12 scenarios (two per kind) and read every transcript. Do not change anything yet.
   ```bash
   python starter_agent.py --n 12 --traces runs/m2-baseline/traces.jsonl --out runs/m2-baseline/grades.jsonl
   ```
2. **Write a real system prompt** from SPEC.md. Keep it a spec: job, authority table, stop conditions, output contract for `resolve_incident`. Version it (`prompts/system_v1.md`) and log the hash with every run.
3. **Improve tool results for the model, not for you.** Two concrete changes worth making:
   - `get_logs` returns up to 20 lines. Add a `grep` argument, so the agent can filter instead of reading everything.
   - Wrap every tool result with the logical time (`tick`) so the agent can tell "before my rollback" from "after".
   Measure each change. A tool change is a behavior change.
4. **Add governors** beyond the three in the starter:
   - *Stall detector:* N consecutive steps with no new information (same result hash as a previous call).
   - *Mutation cap:* at most 2 mutations per episode. A third means it is flailing.
   - *Simulated wall clock:* each tool advances `env.tick`; cap at, say, 40 ticks.
   - *On trip:* page a human with the stop reason. Never end silently.
5. **Size the thresholds from data.** After 12–24 real runs, set `max_steps` to roughly 1.5x the p95 step count of *passing* runs. Record the distribution.
6. **Test every governor offline** with `FakeClient` scripts, as `test_repeat_guard_stops_a_stuck_model` does.
7. **Record cost per episode.** Tokens in and out per run are in the trace; multiply by your current price sheet (check the [pricing page](https://www.anthropic.com/pricing) when you do this; prices change).

## Worked example: the repeat guard is not enough
A real failure mode (illustrative output) where every call differs, so the identical-call guard never trips:

```text
step 6  get_logs {"service": "orders", "limit": 20}
step 7  get_logs {"service": "orders", "limit": 50}
step 8  get_logs {"service": "orders", "limit": 100}
step 9  get_logs {"service": "db", "limit": 100}
step 10 get_logs {"service": "orders", "limit": 200}
```

Each result is the same set of lines, because the sim only has a handful. A stall detector keyed on the *result* catches it:

```python
@dataclass
class StallGuard:
    """Trip when `patience` consecutive tool results add nothing new."""
    patience: int = 3
    _seen: set[str] = field(default_factory=set)
    _stale: int = 0

    def observe(self, result: dict) -> bool:
        h = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        self._stale = self._stale + 1 if h in self._seen else 0
        self._seen.add(h)
        return self._stale >= self.patience
```

And a test that proves it trips while the repeat guard would not:

```python
def test_stall_guard_catches_paraphrased_loop():
    client = FakeClient(lambda m, k: tool("get_logs", {"service": "orders", "limit": 10 + len(m)}, id=f"t{len(m)}"))
    r = run_episode(client, make_scenario(9, kind="false_alarm"), Governors(max_steps=20, stall_patience=3))
    assert r.stop_reason == "stall"
```

## Deliverables
- `agent/` with your loop, `prompts/system_v1.md`, tool wrapper changes
- Governor tests (one per governor), all offline
- `runs/m2-baseline/` with traces and grades for your first real-model run
- A short table: steps and tokens distribution (p50/p95) for passing vs failing runs, and the thresholds you chose

## Done when
- [ ] The agent completes 12 real-model episodes with every stop reason recorded.
- [ ] At least five governors (steps, tokens, identical repeats, stall, mutation cap), each with an offline test.
- [ ] A governor trip produces a `page_human` call or an inbox item, never a silent stop.
- [ ] Thresholds are justified by the observed distribution in a table.
- [ ] Cost per episode is reported in tokens and in currency, with the date of the price sheet.

## Reuse
- `../code/starter_agent.py` (`run_episode`, `Governors`, `_history`)
- The loop from scratch and the governor catalog in [07-loops](../../07-loops/README.md)
- Tool and error-message design in [05-tools-mcp-skills-hooks](../../05-tools-mcp-skills-hooks/README.md)

## Pitfalls
- **Governors in the prompt.** "Do not call more than 20 tools" is a hope. The loop enforces it. Detect it: grep your prompt for numbers that should be in code.
- **Silent truncation.** If you trim long tool results, tell the model ("…180 more lines; use grep"). Silent truncation looks like missing data to it.
- **Parallel tool calls.** Models can return several `tool_use` blocks in one turn. The starter handles them in order. If two are mutations, your mutation cap must count both, and the M6 gate must see each separately.
- **Treating temperature 0 as deterministic.** It is not, for hosted models. Your runs vary even at temperature 0, which is why M5 starts with a noise check ([01-llms-for-systems-engineers](../../01-llms-for-systems-engineers/README.md)).
