# PLAN: <feature name>

<!--
How to use this template
- Written by the agent in plan mode (or a planning session) from SPEC.md and research.md.
- Reviewed by you BEFORE implementation. This is the cheapest place to catch a wrong approach.
- Phases are small enough for one session each, and each phase ends in a runnable check.
- The implementing session ticks boxes and appends to the Progress log, so a fresh session
  can resume from this file alone. Treat it as the durable state of the work, like a WAL.
-->

Spec: ./SPEC.md (requirements R1..Rn)
Research: ./research.md
Base commit: <sha>

## Approach (one paragraph)
<!-- The whole idea in plain words. If you cannot write this, you are not ready to implement. -->

## Phases

### Phase 1: <name>  (covers R1)
- [ ] Write failing test(s): `tests/...::test_...`  -> run, confirm it FAILS for the right reason
- [ ] Change: `path/file` - what and why
- [ ] Verify: `<command>` exits 0
- [ ] Commit: "<structural|behavioral>: <message>"

### Phase 2: <name>  (covers R2, I1)
- [ ] ...

## Files expected to change
<!-- The reviewer compares the final diff against this list. Surprises need a reason. -->
- `path/file`

## Risks and how we'll notice
- <risk> -> <test, metric, or log line that would reveal it>

## Stop and ask a human if
<!-- Escape hatches. The agent should stop rather than improvise. -->
- a test outside the listed files needs to change
- the approach needs a new dependency or a schema change not in SPEC.md
- the same verification fails twice after a fix attempt

## Decision notes
<!-- Append-only. Prevents oscillating between two designs across sessions. -->
- <date> chose ... because ...

## Progress log
<!-- Append-only. One line per completed step, with the evidence. -->
- <date> Phase 1 done: `pytest tests/test_x.py` 4 passed (commit abc123)
