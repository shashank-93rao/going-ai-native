# Examples

Four scenarios, each backed by runnable code in [code/](code/README.md). All outputs shown come from the offline scripts, which use deterministic fake models. The *checkers, gates and policies* are real code. The *model text* is scripted, so read it as illustrative of what a model would say, not as a measurement of one.

---

## 1. Incident summary: routing + prompt chaining

**Code:** [`code/incident_summary.py`](code/incident_summary.py) · **Data:** [`code/data/incidents.jsonl`](code/data/incidents.jsonl)

### Situation
After every page, someone pastes the PagerDuty, Grafana and Slack lines into a doc and writes a five-line summary for `#incidents`. Summaries are late, inconsistent, and sometimes wrong about durations. You want a draft within a minute of RESOLVED.

### Naive approach and what happens
```text
SYSTEM: You are an SRE assistant.
USER: Summarize this incident for #incidents: <300 lines of log>
```
(illustrative output)
```text
Impact: orders-api latency was elevated for about 20 minutes starting at 02:05 UTC due to a
database issue. The team identified a long-running migration and resolved the issue.
```
The timestamp 02:05 is not in the log; the page fired at 02:11:04. The duration is wrong: it was 12 minutes. "A database issue" drops the one useful fact, which is that `CREATE INDEX` without `CONCURRENTLY` blocked writes. And there is nothing to check: one prompt produced one blob.

### AI-native approach

**Step 1: route with the cheap model.** The incident type changes what matters, since a DB incident cares about lock modes and replication lag, and a deploy cares about versions.

```python
CLASSIFIER_SYSTEM = (
    "Classify the incident log into exactly one label: database, deploy, capacity, other.\n"
    "database = locks, replication, migrations, query plans. deploy = a rollout or config push "
    "preceded the symptoms. capacity = load, lag or saturation fixed by scaling.\n"
    "Answer with the label only.")
routed = route(client, log, handlers, classifier_system=CLASSIFIER_SYSTEM, default="other",
               model="claude-haiku-5-5")
```

**Step 2: chain step 1 extracts a timeline, with a route-specific focus.** For example, the database route asks the model to "Note lock types, migration IDs, replication lag values and which replica." **Gate:** valid JSON, *every timestamp occurs verbatim in the raw log*, chronological order, and services named in the log.

```python
def timeline_gate(out, ctx):
    data = parse_json(out)
    stamps = [e.get("ts", "") for e in data.get("timeline", [])]
    missing = [s for s in stamps if s not in ctx["log"]]
    if missing:
        return f"timestamps not present in the log: {missing}"
    if stamps != sorted(stamps):
        return "timeline is not in chronological order"
    ...
```

**Step 3: compute the duration in code.** TRIGGERED to RESOLVED is a subtraction, so the model is never asked to do it.

**Step 4: chain step 2 writes the summary from the timeline only.** **Gate:** at most 120 words, names every impacted service, cites no timestamp outside the timeline, and includes a `Duration:` line.

Output of `python code/incident_summary.py` (the summary text is scripted by the fake, while the routing, gates and duration are real):
```text
== INC-4471  route=database
Impact: orders-api degraded.
Duration: 12 minutes (2026-10-14T02:11:04Z to 2026-10-14T02:24:00Z).
...
== INC-4480  route=deploy
...
== INC-4492  route=capacity
Duration: 41 minutes (2026-10-18T09:40:00Z to 2026-10-18T10:21:00Z).
```

When the model invents a timestamp, the gate rejects it and the retry prompt carries the reason:
```text
Your previous answer was rejected: timestamps not present in the log: ['2026-01-01T00:00:00Z']
Fix that and answer again.
```
After the retry budget is spent, `GateFailed(step="timeline")` is raised and the page owner writes the summary by hand. The test `test_gate_failure_is_retried_with_reason_then_raises` covers this path.

### What to check
- Route fallback rate per week. A rise means new incident types or a model change.
- Gate failure rate per step. Timeline failures above about 5% suggest the extraction prompt or the model needs work.
- Spot-check 10 summaries a month against the raw log. The gates catch invented facts, not *omitted* ones.

---

## 2. Orchestrator-workers: cross-repo dependency audit

**Code:** [`code/dependency_audit.py`](code/dependency_audit.py) · **Data:** [`code/data/repos/`](code/data/repos), [`code/data/advisories.json`](code/data/advisories.json). The advisories are course fixtures modelled on real ones, and their versions are not authoritative.

### Situation
Security asks which services pin a vulnerable version of anything in this week's advisory list. There are four repos with mixed ecosystems (pip, npm, Go modules), and one repo has two manifests. Next week there will be different repos.

### Naive approach and what happens
One agent with `read_file` and `list_dir` is told to "audit all repos against advisories.json". It reads `payments-svc` and `ledger-svc` thoroughly, skims `web-portal/package.json`, never notices `web-portal/requirements.txt`, and reports that `axios 1.6.0` in `notify-svc` is vulnerable (illustrative output). In fact 1.6.0 *is* the fixed version: the model did the version comparison in its head. Coverage is unknown and comparisons are unverified.

### AI-native approach
The subtasks aren't known until you look, which is the definition of orchestrator-workers. The division of labour:

| Who | Does what | Why |
|---|---|---|
| Orchestrator (LLM) | Reads the repo listing and emits one subtask per manifest, with its ecosystem | Manifest discovery across conventions is fuzzy |
| `validate` (code) | Drops subtasks with path traversal, wrong ecosystem, or nonexistent files | The plan is untrusted input |
| `max_subtasks` (code) | Caps fan-out | Bounds cost, and guards against over-spawning |
| Workers (LLM, **read-only**) | Extract `{name, version}` from one manifest | Parsing many formats is a model strength |
| Grounding check (code) | Drops any extracted dependency whose name or version isn't in the manifest text | Stops hallucinated dependencies |
| Advisory match (code) | `version_tuple(pin) < version_tuple(fixed_in)` | Comparison is arithmetic |
| `synthesize` (code, the single writer) | Builds the report table | One place writes the result |

The planner's system prompt:
```text
You plan a dependency audit. You get a listing of repositories and their files. Emit one subtask per
dependency manifest as JSON: {"subtasks": [{"repo": "<repo>", "manifest": "<file name>",
"ecosystem": "pypi|npm|go"}]}. Only list files that appear in the listing. Output JSON only.
```

Output of `python code/dependency_audit.py`:
```text
audited 5 manifests

| repo | package | version | advisory | fixed in |
|---|---|---|---|---|
| ledger-svc | golang.org/x/net | v0.19.0 | ADV-COURSE-004 | 0.23.0 |
| notify-svc | express | 4.18.2 | ADV-COURSE-007 | 4.19.2 |
| payments-svc | cryptography | 41.0.7 | ADV-COURSE-002 | 42.0.0 |
| payments-svc | requests | 2.31.0 | ADV-COURSE-001 | 2.32.0 |
| web-portal | jinja2 | 3.1.2 | ADV-COURSE-003 | 3.1.3 |
```
`notify-svc axios 1.6.0` is correctly absent, because the boundary is exclusive. `web-portal/requirements.txt` is covered. The tests also feed a malicious plan (`"repo": "../../etc"`), a wrong-ecosystem subtask, and a ghost repo, and assert that all three are dropped.

### What to check
- `manifests_audited` against a `find` count of manifest files. That is your coverage oracle, and it costs nothing.
- `warnings` (dropped ungrounded dependencies). A nonzero count is a worker extraction problem, so read the manifest yourself.
- Never let a worker write the report. If you add an LLM-written executive summary, generate it *from the table* and gate it so every package it mentions is in the table.

---

## 3. Evaluator-optimizer: SQL generation with a real checker

**Code:** [`code/sql_optimizer.py`](code/sql_optimizer.py)

### Situation
A product manager asks: "For completed orders created in September 2026 (UTC), return one row per region with columns region, order_count, revenue_cents, ordered by revenue_cents descending." You want the model to write the SQL, and you want it to be correct, not just plausible.

### Naive approach and what happens
A single call, with the query pasted into the dashboard. Here is what a model commonly writes (illustrative; this is the scripted first attempt):
```sql
SELECT c.region, COUNT(*) AS order_count, SUM(oi.qty * oi.unit_price_cents) AS revenue_cents
FROM orders o JOIN customers c ON c.id = o.customer_id JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'completed' AND o.created_at BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY c.region ORDER BY revenue_cents DESC
```
It has two bugs that every analyst has shipped at least once:
- `COUNT(*)` after joining `order_items` counts **items, not orders** (join fan-out).
- `BETWEEN ... '2026-09-30'` against ISO timestamps excludes the whole of September 30th, because every timestamp on that day (even `'2026-09-30T00:00:00Z'`) sorts after `'2026-09-30'` as a string.

It runs, returns three plausible rows, and nobody notices.

### AI-native approach
The evaluator is **SQLite**, not a second model:
1. **Guard:** exactly one `SELECT`/`WITH` statement, and the connection is `PRAGMA query_only = ON` anyway.
2. **Compile:** `EXPLAIN <sql>`. SQLite's error message (`no such table: customerz`) is the feedback.
3. **Execute under a cost budget:** a progress handler aborts after 2M VM steps, the SQLite version of `statement_timeout`. A 4-way cross join hits it.
4. **Column contract:** `["region", "order_count", "revenue_cents"]`.
5. **Results vs a reference query** on a *visible* fixture (seed 7) and a *hidden* one (seed 1009). Feedback describes only the visible fixture, so a generator that pastes the expected rows as literals passes visible and fails hidden: "Correct on the visible fixture but wrong on a hidden one. Do not hard-code values."

The fixtures are generated to contain the traps real data has: multi-item orders, cancelled orders, and timestamps on the afternoon of the 30th.

Output of `python code/sql_optimizer.py` (the three SQL attempts are scripted, and every verdict and feedback line is computed by the checker):
```text
--- round 1  score=0.5  ok=False
... COUNT(*) ... BETWEEN '2026-09-01' AND '2026-09-30' ...
FEEDBACK: Wrong result on the visible fixture: 3 rows, expected 3. First differing row: got ('us-east', 34, 88952),
expected ('us-east', 14, 100645). order_count is too high: check for join fan-out or a missing filter.

--- round 2  score=0.5  ok=False
... COUNT(DISTINCT o.id) ... BETWEEN '2026-09-01' AND '2026-09-30' ...
FEEDBACK: Wrong result on the visible fixture: 3 rows, expected 3. First differing row: got ('us-east', 13, 88952),
expected ('us-east', 14, 100645). order_count is too low: a filter is excluding rows; check range boundaries.

--- round 3  score=1.0  ok=True
... COUNT(DISTINCT o.id) ... o.created_at >= '2026-09-01' AND o.created_at < '2026-10-01' ...
FEEDBACK: ok

stopped_by: passed
```

Note: round 2 didn't improve the score, so the stall counter reached 1 of 2. One more flat round and the loop would have stopped with `stalled` and returned the best attempt so far.

### What to check
- In production you rarely have a reference query. Replace check 5 with **invariants** that must hold, such as `SUM(revenue_cents)` over all regions equalling an independent total query, `order_count <= (SELECT COUNT(*) FROM orders ...)`, and no NULL regions, plus a small set of known-answer questions in CI.
- Feedback must be actionable without leaking the answer. Rows from the visible fixture are fine. The reference SQL is not.
- Track rounds-to-pass. If it creeps up after a model change, rerun the effort sweep from [12-hill-climbing](../12-hill-climbing/README.md).

---

## 4. A broken multi-writer design, and the fix

**Code:** [`code/single_writer.py`](code/single_writer.py)

### Situation
Two tickets land in the same sprint for a small service: "Rename `fetch_user` to `get_user` everywhere" and "Make `nightly_sync` fetch each user through the client module." Someone proposes running two coding agents in parallel, one per ticket, to save time.

The seed repo:
```python
# client.py
def fetch_user(user_id):
    return {"id": user_id}
# api.py
from client import fetch_user
def handle_get_user(req):
    return fetch_user(req["id"])
# jobs.py
def nightly_sync(ids):
    return [str(i) for i in ids]
```

### Naive approach and what happens
Both agents read the same snapshot. Agent A renames in `client.py` and `api.py`. Agent B rewrites `jobs.py` to call the fetch function it saw, which is `fetch_user`. The write sets are disjoint, so there is no merge conflict, and **OCC reports zero conflicts as well**. Output of `python code/single_writer.py`:

```text
== parallel writers, blind writes: conflicts=0 problems=['jobs.py: call to undefined fetch_user()',
   'jobs.py: imports fetch_user which client.py does not define']
== parallel writers, with OCC: conflicts=0 problems=['jobs.py: call to undefined fetch_user()',
   'jobs.py: imports fetch_user which client.py does not define']
from client import fetch_user

def nightly_sync(ids):
    return [fetch_user(i) for i in ids]
```

The fake coder is "competent". It applies each task correctly to whatever state it's shown, and the merge is broken anyway. That is the point: **the failure comes from the architecture, not from the model.** It is write skew, the agent version of Cognition's "actions carry implicit decisions".

A second failure mode lives in the same file. Two agents edit `api.py`, one adding logging and one adding an auth check:
- With blind writes, the logging change is **silently lost** (last writer wins). See `test_blind_writes_lose_updates_on_the_same_file`.
- With OCC, the second write hits `Conflict`, re-reads, re-proposes, and both changes survive (`conflicts=1`).

So OCC fixes lost updates and does nothing about decision conflicts.

### AI-native approach
1. **One writer.** Tasks are applied serially, and each sees the *current* state, so the sync task sees `get_user` already in `client.py`.
2. **Read-only helpers** fan out on questions ("Where is `fetch_user` used?"). Their answers go into the writer's prompt as `<notes>`. Helpers have no edit tools.
3. **A check after every write:** `undefined_calls()`, a ten-line static check that every bare call and every `from x import y` resolves. If it fails, the writer gets one fix attempt with the problem list.

```text
== single writer + read-only helper: conflicts=0 problems=none
from client import get_user

def nightly_sync(ids):
    return [get_user(i) for i in ids]
```

### What to check
- In design review, count the W-agents on shared state. More than one needs a partitioning argument, a per-partition oracle, and a merge gate. See [03](03-multi-agent-and-the-single-writer-rule.md).
- The post-write check must cover *cross-file* invariants: imports, interfaces, schemas. Per-file lint doesn't catch write skew.
- If you parallelize anyway, as in the C-compiler model, each partition needs its own oracle, and the merge needs the full test suite.
