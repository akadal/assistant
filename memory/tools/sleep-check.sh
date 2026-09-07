#!/bin/sh
# sleep-check.sh — mechanises the opportunistic consolidation trigger (AGENTS.md §0.3, §6).
#
# Rule: if there IS an unprocessed log in the inbox and the last consolidation was more than
# 24 hours ago, run a consolidation before starting the real work.
#
# Because "processed" is defined by file location (invariant #3), the state is read entirely
# from file names; mtime is never used (cloning or checking out destroys mtime).
#
# Exit: 0 = a consolidation is due (the reason goes to stdout), 1 = not due.

cd "$(dirname "$0")/../.." || exit 1

INBOX=$(ls memory/inbox/*.md 2>/dev/null | wc -l | tr -d ' ')
[ "$INBOX" -eq 0 ] 2>/dev/null && exit 1

LAST=$(ls memory/archive/inbox/*.md 2>/dev/null | sed 's|.*/||' \
       | grep -o '^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' | sort | tail -1)

if [ -z "$LAST" ]; then
  echo "SLEEP DUE: inbox has $INBOX log(s), no consolidation on record yet"
  exit 0
fi

YESTERDAY=$(date -v-1d +%F 2>/dev/null || date -d 'yesterday' +%F)
if [ "$LAST" \< "$YESTERDAY" ]; then
  echo "SLEEP DUE: inbox has $INBOX log(s), last consolidation $LAST (>24h ago)"
  exit 0
fi
exit 1
