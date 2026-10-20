#!/usr/bin/env python3
"""session-wrapup.py — close a session on purpose and leave the conversation in the inbox.

Why this exists: capture used to depend on discipline. At the end of a working session the agent
was supposed to remember to append what mattered; when it forgot, the session was gone. Some
harnesses paper over this with an end-of-session summariser that asks a cheap model to guess what
was important, and a guess is the right thing to keep as a safety net. But when a session is
closed deliberately there is nothing to guess: the agent that did the work already knows what was
decided, why, and what is still open. This tool writes that block, runs lint as the gate, and
commits and pushes it.

**This is not sleep.** It runs no consolidation, sorts nothing and never touches L1. Sleep is a
separate, locked, heavier process (AGENTS.md §6) with its own two gates; a wrap-up should take a
second, not ten minutes. What this leaves behind is the raw material sleep will distil tonight.

**Use a distinct trace.** The block is marked `(wrapup)` so consolidation can tell it apart from
an automatic end-of-session summary: the latter is an inference and triages at the lowest
confidence, this one is a statement by the agent that was there.

**The block speaks for one session only.** People run several sessions at once, and a session
that declares "X is half finished" can be describing work another session finished ten minutes
ago. There is no lock here and nothing waits: the tool simply stamps the block when other
transcripts were written recently, so consolidation reads "still open" as one session's snapshot
rather than the state of the repository. Sessions on *other machines* are invisible from here,
so the mechanical half is not enough on its own; the rule in `memory/rules/consolidation.md`
(conflict resolution) carries the rest.

**Trigger word is yours.** Radio protocol gives you "over" and "out"; pick what you like. If your
harness supports slash commands, bind one to this tool. If your harness also runs an automatic
end-of-session summariser, make it skip a session that was already wrapped, or the same
conversation lands in the inbox twice, the second time worse.

Usage:
  python memory/tools/session-wrapup.py --text "What was done / decided / left open"
  echo "..." | python memory/tools/session-wrapup.py
  python memory/tools/session-wrapup.py --text "..." --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent.parent
INBOX = ROOT / "memory" / "inbox"
TRACE = "wrapup"
NEIGHBOUR_MINUTES = 30

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def machine() -> str:
    f = ROOT / "memory" / ".machine"
    if f.is_file():
        name = f.read_text(encoding="utf-8").strip()
        if name:
            return name
    return os.environ.get("ASSISTANT_MACHINE") or socket.gethostname().split(".")[0].lower()


def git(*a, **k):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=120, **k)


def concurrent_sessions() -> int:
    """How many OTHER session transcripts were written in the last NEIGHBOUR_MINUTES.

    Harness specific and deliberately forgiving: it knows where Claude Code keeps transcripts and
    returns 0 for anything else. A wrong 0 only costs the stamp; it never blocks the wrap-up.
    """
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return 0
    slug = "".join(c if c.isalnum() else "-" for c in str(ROOT))
    dirs = [base / slug] if (base / slug).is_dir() else [p for p in base.iterdir() if p.is_dir()]
    cutoff = time.time() - NEIGHBOUR_MINUTES * 60
    recent = [f for d in dirs for f in d.glob("*.jsonl") if f.stat().st_mtime >= cutoff]
    return max(0, len(recent) - 1)          # the current session is one of them


def build_block(text: str) -> str:
    head = f"({TRACE}) Session wrapped up."
    others = concurrent_sessions()
    if others:
        head += (f" {others} other session(s) were open at the same time; anything left open "
                 f"below is this session's view, not the state of the repository.")
    return f"{head}\n\n{text}"


def append_to_inbox(block: str, now: dt.datetime) -> Path:
    INBOX.mkdir(parents=True, exist_ok=True)
    path = INBOX / f"{now:%Y-%m-%d}--{machine()}.md"
    header = ""
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        header = (f"---\ntype: log\ndate: {now:%Y-%m-%d}\nmachine: {machine()}\n---\n"
                  f"# {now:%Y-%m-%d} ({machine()})\n")
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"{header}\n## {now:%H:%M}\n\n{block.rstrip()}\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="the wrap-up block; read from stdin when omitted")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written")
    a = ap.parse_args()

    text = (a.text if a.text is not None else sys.stdin.read()).strip()
    if not text:
        print("session-wrapup: empty block; a session does not close without saying what happened",
              file=sys.stderr)
        return 2

    block = build_block(text)
    if a.dry_run:
        print("--- DRY RUN ---\n" + block)
        return 0

    now = dt.datetime.now()
    path = append_to_inbox(block, now)

    lint = subprocess.run([sys.executable, str(TOOLS / "lint.py")],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    if lint.returncode:
        print("session-wrapup: LINT RED, nothing committed. The block is on disk:\n"
              + lint.stdout[-1500:], file=sys.stderr)
        return 1

    if git("add", "-A").returncode or git("commit", "-q", "-m", f"inbox: session wrapped up ({TRACE})").returncode:
        print("session-wrapup: WARNING could not commit (the block is on disk)", file=sys.stderr)
        return 1
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    p = git("push", "-q")
    if p.returncode:
        # On a multi-machine repository a rejected push is normal: another machine pushed first.
        git("pull", "--rebase", "--autostash", env=env)
        p = git("push", "-q", env=env)
    if p.returncode:
        print(f"session-wrapup: WARNING push failed: {p.stderr.strip()[:200]}", file=sys.stderr)
        return 1

    print(f"wrapped up: {path.relative_to(ROOT)} written, lint green, pushed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
