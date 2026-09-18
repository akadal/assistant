#!/bin/sh
# sleep-check.sh — mechanises the opportunistic consolidation trigger (AGENTS.md §0.3, §6).
#
# Rule: if there IS an unprocessed log in the inbox and no consolidation has happened today,
# run one before starting the real work. The test is "has today been consolidated", not an
# elapsed-hours threshold: a nightly run fires at a fixed time, so the previous run's own trace
# lands AFTER that time and an hours threshold can never be met.
#
# Because "processed" is defined by file location (invariant #3), the state is read entirely
# from file names; mtime is never used (cloning or checking out destroys mtime).
#
# Exit: 0 = a consolidation is due (the reason goes to stdout), 1 = not due.

cd "$(dirname "$0")/../.." || exit 1

INBOX=$(ls memory/inbox/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "$INBOX" -eq 0 ] 2>/dev/null && exit 1

# Lock: the repo is multi-machine, so two machines can start consolidating the same inbox — the
# same logs get distilled twice and the archive moves collide. The lock is shared through git
# (memory/.sleep-lock, written and removed by sleep-run.sh). The check lives in the trigger rather
# than in prose, so every path — manual, opportunistic, scheduled — goes through the same gate.
LOCK=memory/.sleep-lock
if [ -f "$LOCK" ]; then
  L_EPOCH=$(sed -n 's/^epoch=//p' "$LOCK")
  AGE=$(( $(date +%s) - ${L_EPOCH:-0} ))
  if [ "$AGE" -lt 7200 ]; then
    echo "NOT DUE: $(sed -n 's/^machine=//p' "$LOCK") is consolidating (lock ${AGE}s old)"
    exit 1
  fi
fi

LAST=$(ls memory/archive/inbox/*.md 2>/dev/null | sed 's|.*/||' \
       | grep -o '^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' | sort | tail -1)

if [ -z "$LAST" ]; then
  echo "SLEEP DUE: inbox has $INBOX log(s), no consolidation on record yet"
  exit 0
fi

# Compare against TODAY, not yesterday. Comparing against yesterday made the nightly run block
# ITSELF: a consolidation archives the logs of the day it runs on (the run's own source-pull step
# writes one), so LAST becomes the run's own date and the next night YESTERDAY == LAST, printing
# "not due". Measured 2026-09-18 on the repository this project is derived from: the nightly job
# had been running every other night — and at the moment of measurement the last consolidation was
# 28 hours old with 8 unprocessed logs in the inbox, while the gate still said not due.
# Same-day double runs are still blocked: a run archives today's log, so LAST == TODAY.
TODAY=$(date +%F)
if [ "$LAST" \< "$TODAY" ]; then
  echo "SLEEP DUE: inbox has $INBOX log(s), last consolidation $LAST (nothing today)"
  exit 0
fi
exit 1
