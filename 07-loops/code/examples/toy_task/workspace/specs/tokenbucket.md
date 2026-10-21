# TokenBucket spec

## Acquire
`try_acquire(n)` succeeds iff at least `n` tokens are available (`>=`, not `>`). A
failed acquire consumes nothing. `n <= 0` raises `ValueError`.

## Refill
Tokens refill continuously at `refill_per_sec` and are capped at `capacity`. A bucket
idle for an hour holds exactly `capacity` tokens, never more.

## Oracle
`python -m pytest -q spec_tokenbucket.py`. The oracle is read-only for the agent.
