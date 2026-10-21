# REVIEW.md: ledgerd

Written by the code owners for the machine reviewer (and for humans new to the repo).
Keep this file short. It is read on every review, and every line costs attention.
If a finding repeats three times, fix it at the source (a lint rule, a test, CLAUDE.md)
and delete the line here.

## What this service is
A Go service that keeps a double-entry ledger, replicated with Raft across 5 voters.
Clients call `POST /postings` with an `Idempotency-Key`. Correctness beats latency,
and latency beats everything else.

## What failure looks like here
Report these as **Important**. Each needs a file, a line, and the interleaving or input that breaks it.
- **Lost or duplicated writes.** A posting acknowledged to a client that is not durable on a quorum, or applied twice for one idempotency key.
- **Raft safety violations.** Voting twice in a term, granting a vote before `votedFor` is persisted, committing an entry from a previous term by counting replicas, or a leader serving reads without a lease or ReadIndex.
- **Durability ordering.** Any reply sent before `fsync` returns. Any `go` statement in front of a storage write on the request path.
- **Unbounded resources.** Queues, maps or goroutines without a bound or backpressure on the request path.
- **Migration hazards.** Table rewrites, locks held for more than a statement, `NOT NULL` without a default on a hot table, non-`CONCURRENTLY` index builds.
- **Silent test weakening.** Deleted assertions, `t.Skip`, removed `-race`, loosened timeouts in tests.

## What does not count
- Style, naming, comment wording, import order. `gofumpt` and `golangci-lint` already run in CI.
- Speculative refactors ("this could be cleaner").
- Findings that depend on guessing what a function does from its name. Open it, or do not report it.

## Evidence rules
- Every finding names `file:line` in the new version of the file and quotes the line.
- Concurrency findings name the two operations and the order that breaks.
- Say "pre-existing" if the problem is on a line this diff did not touch.

## Nit cap
At most 3 nits per review. If you have more, report the 3 most useful.

## Paths to skip
- `*.pb.go`
- `internal/gen/*`
- `vendor/*`
- `docs/adr/*`

## Output
Start the summary with a count ("2 important, 1 nit"). If there is nothing to fix, say
"0 findings. Nothing to fix." and stop. Do not pad.

## Owners
- `internal/raft/`, `config/cluster/`: @consensus-owners
- `internal/wal/`, any `fsync` path: @storage-owners
- `migrations/`: @data-owners
