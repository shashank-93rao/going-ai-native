# Exercises: module 17

Exercises 1, 4 and 5 run fully offline. Exercises 2 and 3 are better with a real API key. Exercises 6 to 8 are about your own team and take place over days or weeks.

Run all commands from `17-ai-native-engineer-and-team/code/` with `PYTHONPATH=../../shared` (or install the kit with `pip install -e .` from the course root).

---

## Exercise 1: Route your own history (60 min, offline)
**Goal.** Find out how your team's actual review effort compares with a risk-tier policy.

**Steps.**
1. Copy `data/review_policy.json` to `my_policy.json` and rewrite its rules for one of your repos: which paths and patterns are high risk, who owns them.
2. Export the last 100 merged PRs as diffs, for example:
   ```bash
   git log --merges --first-parent -n 100 --format=%H main | while read h; do
     git diff "$h^1" "$h" > "/tmp/prs/$h.diff"; done
   ```
3. Run `review_router.py` on each, and join the result with how many approvals each PR actually got and how long it waited (from your Git host's API).
4. List the PRs where the router and reality disagree by more than one tier.

**Done when.**
- You have a table of tier vs actual approvals for 100 PRs.
- At least five disagreements are explained in one line each ("router too strict: generated code", "we under-reviewed this migration").
- You changed at least one rule in `my_policy.json` as a result, and added a test for it.

**Stretch.** Add a rule type the router doesn't support (for example "file deleted" or "binary file changed") and a test for it.

---

## Exercise 2: A REVIEW.md that changes reviewer behaviour (90 min, real API recommended)
**Goal.** Show that a REVIEW.md written for your repo changes what a model reviewer reports.

**Steps.**
1. Write a REVIEW.md for one of your repos, following `templates/REVIEW.md`: what failure looks like, what does not count, evidence rules, nit cap, skip paths, output format.
2. Pick three real diffs: one with a known real bug (from a past revert), one clean, one with only style issues.
3. Run `verifier_vote.py` on each, first with a generic one-line REVIEW.md ("Review this code carefully"), then with yours. Use `--n 3`.
4. Record posted findings, dropped style and dropped minority for each run.

**Done when.**
- A 3x2 table (diffs by REVIEW.md version) with posted / dropped counts.
- With your REVIEW.md, the bug diff has the real bug posted, the clean diff has 0 posted findings, and the style diff has 0 posted findings. If not, you wrote down why and what you changed.

**Stretch.** Run each cell 5 times and report how often the real bug is posted. Single runs are noisy ([module 12](../12-hill-climbing/README.md)).

---

## Exercise 3: Build a reviewer eval from incident PRs (2-3 hours, real API)
**Goal.** Measure your machine reviewer's recall on bugs that actually hurt you, and how it changes with the number of voters.

**Steps.**
1. Collect 10 PRs that caused an incident or were reverted. For each, ask the code owner to confirm the bug's file and line. Store them as JSONL:
   ```json
   {"id": "inc-2026-03", "diff_path": "evals/inc-2026-03.diff", "bug_file": "internal/raft/election.go", "bug_line": 43}
   ```
2. Add 10 known-clean PRs (merged, never reverted, no follow-up fix within 60 days).
3. Write `reviewer_eval.py` that runs `review()` on each case and counts: hit (a posted cluster within 2 lines of the bug), miss, and false alarms on clean PRs.
4. Run with N = 1, 3 and 5.

**Done when.**
- A table of recall (on incident PRs) and false-alarm rate (on clean PRs) for N = 1, 3, 5.
- A one-paragraph interpretation: did voting improve precision, recall, both or neither? (Expect precision to improve more than recall; correlated misses don't vote away.)
- `reviewer_eval.py` has a test that runs on two FakeClient cases offline.

**Stretch.** Vary the reviewers (two different models, or three focus prompts: concurrency, durability, API contract) and see whether recall at N = 3 rises.

---

## Exercise 4: Two-phase review, hunters then verifiers (90 min, offline)
**Goal.** Implement the architecture Anthropic describes, where bug hunters propose findings and separate verifier agents vote on each one, and compare it with the independent-replicas variant in `verifier_vote.py`.

**Steps.**
1. Write `hunt_and_verify.py`. Phase 1: K hunters return findings (reuse `parse_findings`). Phase 2: for each distinct candidate, N verifiers each get the diff plus *that one finding* and answer `{"verdict": "real" | "not_real", "reason": "..."}`.
2. Post a candidate only if a strict majority of verifiers say real. Drop style candidates before phase 2 to save calls.
3. Test with a FakeClient responder that returns different verdicts per candidate.

**Done when.**
- Tests cover: a real bug confirmed by 2 of 3 verifiers is posted; a hallucinated finding rejected by 2 of 3 is dropped; style candidates never reach phase 2 (assert on `client.calls`); a malformed verifier answer counts as an abstention.
- A short note comparing the number of model calls for both variants on a diff with 4 candidates.

**Stretch.** Give verifiers a tool to read the full file at a path (fake it with a dict), so they can refute name-based guesses.

---

## Exercise 5: A model classifier that can only raise the tier (60 min, offline)
**Goal.** Add a model-based tier classifier on top of the deterministic router, with the invariant that it can never lower the tier.

**Steps.**
1. Write `classify_tier(client, diff, floor: RoutingDecision) -> RoutingDecision`. Ask the model for `{"tier": "low|medium|high", "reason": "..."}` given the diff and the router's reasons.
2. Combine: final tier = max(router tier, model tier). Malformed model output leaves the router's decision unchanged and adds a reason.
3. Tests with FakeClient.

**Done when.**
- Tests pass for: model says higher (tier raised, reason recorded), model says lower (tier unchanged), model output malformed (unchanged, reason recorded).
- A Hypothesis test: for any router decision and any model tier, the result is never below the router's tier.

---

## Exercise 6: Measure yourself (2 weeks, real coding agent)
**Goal.** Get a personal, METR-style estimate of whether agents speed you up, by task class.

**Steps.**
1. Before starting, write down your forecast speedup per task class.
2. For two weeks, log every task: class, start time, merged time, and whether it was reverted or reworked within 30 days (fill this in later).
3. For one task class with enough volume (usually bug-with-reproducer or mechanical), flip a coin per task to decide agent-first or manual. Don't skip tasks because of the coin. If you do, log the skip; METR found these skips biased its results.
4. Compute medians with a bootstrap 95% interval per arm.

**Done when.**
- At least 20 logged tasks and at least 10 randomized ones.
- A table: forecast vs measured, with intervals, and the number of skipped tasks.
- One sentence on whether your feeling matched the data.

---

## Exercise 7: Write your team's AGENT_POLICY.md (60 min)
**Goal.** Turn your team's implicit agent practices into an enforceable policy.

**Steps.**
1. Inventory every agent your team runs: who launches it, with which credentials, where results go, what it costs.
2. Start from `templates/AGENT_POLICY.md` and adapt each section. For every rule, write "Enforced by:" with a mechanism, or mark it "not yet enforced".
3. Get it reviewed by two teammates as a PR.

**Done when.**
- Every agent in your inventory has an owner, a budget and a kill switch, or a dated plan to get one.
- At least half the rules have a named enforcement mechanism.
- `test_templates.py`-style checks exist for your version (required sections, tier table matches your router policy).

---

## Exercise 8: An interview exercise that a careless agent fails (3 hours, real coding agent)
**Goal.** Design a build-and-attack interview exercise for your domain and prove it discriminates.

**Steps.**
1. Pick a past incident in your system. Turn it into a 3-hour build brief with one planted decision (like the webhook `event_id` vs `payment_id` in [concept 05](05-hiring-and-evaluating-ai-native-engineers.md)).
2. Write the red-team agent prompt and a binary rubric of 6 to 8 items.
3. Run the exercise yourself with a coding agent, deliberately careless: paste the brief, accept everything, don't read diffs. Then run the red team against the result.
4. Run it again carefully.

**Done when.**
- The careless run fails at least two rubric items and at least one red-team attack succeeds against it.
- The careful run passes the rubric.
- If the careless run passes, you changed the exercise and re-ran it.

**Stretch.** Pilot it on a colleague and adjust timing.
