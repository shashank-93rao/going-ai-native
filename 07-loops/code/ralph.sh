#!/usr/bin/env bash
# ralph.sh: the minimal fresh-context Ralph loop, with the governors bolted on.
#
# Same prompt every iteration, a brand-new agent process each time, state on disk.
# Huntley's original is one line:  while :; do cat PROMPT.md | claude-code ; done
# This version adds what an unattended loop needs: an iteration cap, a stop file,
# a stall breaker, an oracle the agent cannot write, commit-on-green, and typed exit codes.
#
#   AGENT_CMD="claude -p --dangerously-skip-permissions --max-turns 40 --max-budget-usd 3" \
#   ORACLE_CMD="python -m pytest -q spec_tokenbucket.py" \
#   ./ralph.sh                      # run from inside the workspace, in a container
#
# Exit codes: 0 success, 1 iteration cap, 2 blocked, 3 oracle broken, 5 stalled, 6 stop file.
set -u

: "${AGENT_CMD:?set AGENT_CMD (prompt is piped to stdin)}"
: "${ORACLE_CMD:?set ORACLE_CMD (exit 0 = pass)}"
MAX_ITERS="${MAX_ITERS:-20}"
STALL_LIMIT="${STALL_LIMIT:-3}"     # iterations with no new plan item closed and no oracle change
PROMPT_FILE="${PROMPT_FILE:-PROMPT.md}"
STATE=".ralph"
mkdir -p "$STATE/logs"

open_items() { grep -c '^- \[ \]' fix_plan.md 2>/dev/null || true; }
fail_count() { # pytest-flavoured: "3 failed" -> 3; anything else -> exit-code based
  local n; n=$(grep -Eo '[0-9]+ failed' "$1" | head -1 | cut -d' ' -f1)
  echo "${n:-0}"
}
run_oracle() { bash -c "$ORACLE_CMD" >"$STATE/oracle.out" 2>&1; echo $?; }
git_on() { [ -d .git ]; }
commit() { git_on && git add -A && git -c user.name=ralph -c user.email=ralph@localhost commit -qm "$1" || true; }

rc=$(run_oracle)
if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then echo "[ralph] oracle broken (rc=$rc)"; exit 3; fi
best_open=$(open_items); best_fail=$(fail_count "$STATE/oracle.out"); stall=0

for ((i = 1; i <= MAX_ITERS; i++)); do
  [ -f "$STATE/STOP" ] && { echo "[ralph] stop file present"; exit 6; }
  if [ "$(open_items)" -eq 0 ] && [ "$(run_oracle)" -eq 0 ]; then
    echo "[ralph] plan empty and oracle green after $((i - 1)) iterations"; exit 0
  fi

  head=$(git_on && git rev-parse --short=7 HEAD 2>/dev/null || echo nogit)
  log="$STATE/logs/iter_$(printf %03d "$i")_${head}.log"
  bash -c "$AGENT_CMD" <"$PROMPT_FILE" >"$log" 2>&1       # fresh context: new process every time
  agent_rc=$?

  [ -f "$STATE/BLOCKED" ] && { echo "[ralph] blocked: $(cat "$STATE/BLOCKED")"; exit 2; }
  rc=$(run_oracle)
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then echo "[ralph] oracle broken (rc=$rc)"; exit 3; fi
  now_open=$(open_items); now_fail=$(fail_count "$STATE/oracle.out")

  if [ "$now_open" -lt "$best_open" ] || [ "$now_fail" -lt "$best_fail" ]; then
    stall=0; best_open=$now_open; best_fail=$now_fail
    commit "ralph: iter $i open=$now_open failed=$now_fail"
  else
    stall=$((stall + 1))
  fi
  echo "{\"iter\": $i, \"agent_rc\": $agent_rc, \"oracle_rc\": $rc, \"open\": $now_open, \"failed\": $now_fail, \"stall\": $stall}" | tee -a "$STATE/log.jsonl"
  [ "$stall" -ge "$STALL_LIMIT" ] && { echo "[ralph] stalled: $stall iterations without progress"; exit 5; }
done

if [ "$(open_items)" -eq 0 ] && [ "$(run_oracle)" -eq 0 ]; then echo "[ralph] done on last iteration"; exit 0; fi
echo "[ralph] iteration cap $MAX_ITERS reached"; exit 1
