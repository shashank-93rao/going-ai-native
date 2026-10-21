# RESEARCH: <question or ticket>

<!--
How to use this template (research-plan-implement, after Dex Horthy / HumanLayer)
- Produced by a read-only session (plan mode, or Explore subagents). No code changes.
- It describes how the system works TODAY, with file:line evidence. No proposals yet.
- You review it hard: one wrong line here becomes many wrong lines of code.
- Keep it short enough that a fresh planning session can read it and stay well under half
  its context window.
-->

Question: <what we need to understand>
Commit researched: <sha>

## Summary (5 lines max)

## Relevant code
| Location | What it does | Evidence |
|---|---|---|
| `path/file.py:120-168` | ... | quoted line or test name |

## How data / control flows
<!-- Numbered steps from entry point to side effect. Name threads, locks, transactions, retries. -->
1. ...

## Existing tests and how to run them
```bash
```

## Constraints and invariants discovered
<!-- Things the code assumes that a change could break. -->

## Unknowns (do not guess)
<!-- What the research could not establish, and how to find out. -->
