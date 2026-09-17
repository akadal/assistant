#!/bin/sh
# sleep-run.sh — unattended consolidation runner (AGENTS.md §6).
#
# WHY: the opportunistic trigger ties consolidation to opening a session. Skip a few days and the
# inbox piles up; open two machines on the same day and both start consolidating the same inbox —
# the same logs get distilled twice and the archive moves collide. A scheduler pins the trigger to
# a fixed hour, and a lock pins it to one machine at a time.
#
# This script does NO distilling. The rules stay in AGENTS.md and rules/consolidation.md; all that
# lives here is the lock plus one harness call. The harness command is swappable, so the multi-AI
# rule holds: point `memory/.sleep-command` at whichever CLI you use.
#
# Lock: the repo is multi-machine and git is the only shared channel. `memory/.sleep-lock` is
# committed and pushed when a run starts and deleted when it ends; a lock older than 2 hours is
# treated as a crashed run and taken over.
#
# Schedule it on ONE machine only — the one that is usually powered on. Every other machine keeps
# the opportunistic trigger. Duplicating the schedule turns the collision into a nightly event.
#   cron:      0 4 * * *  sh /path/to/repo/memory/tools/sleep-run.sh
#   launchd:   a StartCalendarInterval job running the same line
#   Windows:   Task Scheduler, daily 04:00, action `sh.exe "C:/path/to/sleep-run.sh"`
#
# The standalone CLI needs its own login. A desktop app's credentials are not inherited by a
# scheduled process — log the CLI in once, or the nightly run fails on authentication.
#
# Usage: sh memory/tools/sleep-run.sh [--dry-run] [--force]
# Exit:  0 = ran / not due · 1 = another machine is consolidating · 2 = error

ROOT=$(cd "$(dirname "$0")/../.." && pwd) || exit 2
cd "$ROOT" || exit 2

LOCK="memory/.sleep-lock"
STATE="memory/tools/.state"
LOG="$STATE/sleep-run.log"
STALE=7200                       # 2h: a lock older than this belongs to a crashed run
MACHINE=$(cat memory/.machine 2>/dev/null || hostname)
DRY=""; FORCE=""

for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --force)   FORCE=1 ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done

mkdir -p "$STATE"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; [ -n "$DRY" ] && echo "$*"; return 0; }

# Harness command, per machine. Reads the prompt on stdin, writes plain text to stdout.
# Priority: ASSISTANT_SLEEP_COMMAND > memory/.sleep-command (gitignored) > default.
sleep_command() {
  [ -n "${ASSISTANT_SLEEP_COMMAND:-}" ] && { echo "$ASSISTANT_SLEEP_COMMAND"; return; }
  [ -s memory/.sleep-command ] && { head -1 memory/.sleep-command; return; }
  echo "claude -p --permission-mode bypassPermissions --output-format text"
}

PROMPT='This is a scheduled, unattended consolidation run (AGENTS.md §6). Nobody is watching.
The lock is held, git pull has run and the trigger has been verified — do not repeat those checks.
Read memory/rules/consolidation.md and run the consolidation end to end: source pull,
pre-sleep checkpoint, the LLM pass (triage · sort · merge · COMPRESS · resolve conflicts ·
refresh the indexes and state.md · sweep todo.md), move processed logs into
memory/archive/inbox/. TWO GATES BEFORE COMMITTING: python3 memory/tools/lint.py AND
python3 memory/tools/sleep-audit.py — no commit until both are green. If the audit is red, fix
the finding (RATCHET/BLOAT = compress that file or move its detail under
memory/archive/<domain>/YYYY/; FABRICATION/LOSS = show the source or put the line back) and run it
once more. If it is still red, git reset --hard pre-sleep, commit nothing, and say why in the
summary. Then one atomic commit, git push origin main.
Do NOT apply anything behind an approval gate (merging entities, aliases, unsourced removals, a new
domain) — write it into memory/questions.md and carry on. Leave memory/.sleep-lock alone.
Ask nothing, wait for no approval. Print a one-paragraph summary when you are done.'

# --- 1. be current --------------------------------------------------------
# --ff-only alone is not enough. Across several machines a failed push leaves an
# orphan commit behind and the branch diverges; --ff-only then says "Not possible to
# fast-forward" and gives up, so sleep would never run again on that machine. Our
# commits are append-only markdown on a single branch, so rebasing is safe.
if ! git pull --ff-only origin main >/dev/null 2>&1; then
  if ! git pull --rebase --autostash origin main >/dev/null 2>&1; then
    git rebase --abort >/dev/null 2>&1
    log "ERROR pull failed (real conflict or no network) — run aborted"
    exit 2
  fi
  log "branch had diverged; rebased onto origin/main"
fi

# --- 2. is it due ---------------------------------------------------------
if [ -z "$FORCE" ]; then
  REASON=$(sh memory/tools/sleep-check.sh)
  if [ $? -ne 0 ]; then log "skipped: ${REASON:-not due}"; exit 0; fi
  log "trigger: $REASON"
else
  log "trigger: --force"
fi

# --- 3. lock --------------------------------------------------------------
if [ -f "$LOCK" ]; then
  L_MACHINE=$(sed -n 's/^machine=//p' "$LOCK")
  L_EPOCH=$(sed -n 's/^epoch=//p' "$LOCK")
  AGE=$(( $(date +%s) - ${L_EPOCH:-0} ))
  if [ "$AGE" -lt "$STALE" ]; then
    log "STOP: $L_MACHINE is consolidating (started ${AGE}s ago) — run skipped"
    exit 1
  fi
  log "WARN $L_MACHINE lock is stale (${AGE}s) — taking over"
fi

if [ -n "$DRY" ]; then
  log "dry run: no lock taken, harness not called"
  log "command would be: $(sleep_command)"
  exit 0
fi

printf 'machine=%s\nstarted=%s\nepoch=%s\n' "$MACHINE" "$(date '+%F %T %z')" "$(date +%s)" > "$LOCK"
git add "$LOCK" >/dev/null 2>&1
git commit -q -m "sleep lock: $MACHINE" >/dev/null 2>&1
if ! git push -q origin main >/dev/null 2>&1; then
  # Race: someone pushed in between. Back off and look again.
  git reset --hard HEAD~1 >/dev/null 2>&1
  git pull --ff-only origin main >/dev/null 2>&1     || git pull --rebase --autostash origin main >/dev/null 2>&1     || git rebase --abort >/dev/null 2>&1
  if [ -f "$LOCK" ]; then
    log "STOP: lost the race to $(sed -n 's/^machine=//p' "$LOCK")"
    exit 1
  fi
  log "ERROR could not push the lock — run aborted"
  exit 2
fi

release() {
  git pull --ff-only origin main >/dev/null 2>&1     || git pull --rebase --autostash origin main >/dev/null 2>&1     || git rebase --abort >/dev/null 2>&1
  [ -f "$LOCK" ] || return 0
  rm -f "$LOCK"
  git add -A -- "$LOCK" >/dev/null 2>&1
  git commit -q -m "sleep lock released: $MACHINE" >/dev/null 2>&1
  git push -q origin main >/dev/null 2>&1 || log "WARN could not push the lock release"
}
trap release EXIT INT TERM

# --- 4. harness pass ------------------------------------------------------
log "consolidation starting ($MACHINE)"
COMMAND=$(sleep_command)
# If your harness runs session hooks, guard them so this nested call does not re-trigger them.
printf '%s' "$PROMPT" | sh -c "$COMMAND" >> "$LOG" 2>&1
CODE=$?
if [ "$CODE" -eq 0 ]; then
  log "consolidation finished"
else
  log "ERROR consolidation harness exit $CODE — see the end of this log"
fi
exit 0
