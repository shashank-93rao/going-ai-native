# SPEC: <feature name>

<!--
How to use this template
- Produce it with the interview prompt (see 03-spec-driven-development.md), then edit by hand.
- It must be self-contained: a fresh session with no chat history should be able to implement it.
- Every requirement gets an ID (R1, R2...) so the plan, the tests, and the reviewer can cite it.
- If a section is genuinely empty, write "None" rather than deleting it. Deleting hides decisions.
- Keep it under ~2 pages. Long specs get skimmed by humans and models alike.
-->

Status: draft | approved (by <name>, <date>)
Owner: <you>
Related: <ticket / RFC / incident link>

## 1. Problem
<!-- 2-4 sentences. What is broken or missing, for whom, and the evidence (incident, metric, ticket). -->

## 2. Goals
<!-- Numbered, testable requirements. Each one should map to at least one test in section 7. -->
- R1: ...
- R2: ...

## 3. Non-goals / out of scope
<!-- The most valuable section for an agent. Name the tempting adjacent work it must NOT do. -->
- ...

## 4. Invariants that must keep holding
<!-- Ordering, idempotency, consistency, auth, backward compatibility, performance budgets. -->
- I1: ...

## 5. Design
### Interfaces
<!-- Exact signatures, endpoints, headers, schemas, config keys. Copy-pasteable. -->

### Data and state
<!-- Tables, columns, indexes, TTLs, migrations. Who writes what. -->

### Failure and concurrency behaviour
<!-- What happens on crash mid-operation, on concurrent duplicates, on timeouts, on retries. -->

### Files and modules involved
<!-- Paths the change is expected to touch. Anything outside this list needs a reason in the PR. -->
- `path/to/file`: why

## 6. Decisions and rejected alternatives
<!-- One line each. Stops the agent re-litigating settled questions mid-implementation. -->
- Chose X over Y because ...

## 7. Verification
### Tests that must exist (and fail before the change)
<!-- Name each test and the requirement it covers. Prefer literals as expected values. -->
- `test_...` covers R1

### Commands
```bash
# fast local check (seconds)
# full suite
# end-to-end check that proves the feature works for real
```

### Done when
<!-- Objective and checkable. This is what a /goal condition or a Stop hook can evaluate. -->
- [ ] all commands above exit 0
- [ ] no test outside <dir> was modified or skipped
- [ ] ...

## 8. Rollout and rollback
<!-- Flags, migration order, how to revert, what to watch (metric / log line). -->

## 9. Open questions
<!-- Anything unresolved. Implementation should not start while this has blocking items. -->
