#!/usr/bin/env python3
"""upstream-sync.py — take mechanism updates from the upstream template, once per new release.

Why this exists: a repository created with "Use this template" shares no history with the
template. `git pull upstream main` does not work, so updates came only through the manual,
path-scoped checkout in `docs/UPGRADING.md` — and a manual step nobody is reminded of is never
run. Copies drift months behind the lint rules and gates they would want.

What it does, every sleep:
  1. Cheap look: one `git ls-remote upstream`. Same commit as last time → silent, done.
  2. New commit → fetch it and sort every mechanism file into one of three piles:
     - untouched: the local file is byte-identical to SOME version upstream ever shipped. The
       owner never edited it, so taking the new version loses nothing → updated automatically.
     - customised: the local file matches no upstream version. The owner (or their agent) changed
       it on purpose → never overwritten; listed in the inbox with the command to inspect it.
     - the owner's own: a path upstream never had → not ours, not mentioned.
  3. New sections under "Breaking changes" in `docs/UPGRADING.md` are listed in the inbox: some
     upgrades need the owner to act on files that are theirs.
  4. Lint before and after. If the update turns a green lint red, it is rolled back and the
     inbox says so — a sleep must never inherit a red gate from an unattended update.
  5. One separate commit (invariant #2: risky operations get their own commit, revertable alone),
     carrying an `Upstream-Seen: <sha>` trailer. That trailer is the only state: shared through
     git like everything else, so a second machine does not repeat the work or the inbox note.

"Untouched" is decided without a base commit on purpose: a template copy has no merge base, and
recording one in a state file would be one more thing to lose. The blob-history test needs
nothing but the upstream history itself.

Off by default: with no `upstream` remote the tool says so and exits 0. The upstream repository
itself (origin == upstream) is skipped. A network failure never blocks a sleep.

Usage:
  python3 memory/tools/upstream-sync.py            # look, and apply if there is something new
  python3 memory/tools/upstream-sync.py --check    # look only; exit 0 = new upstream commit
  python3 memory/tools/upstream-sync.py --dry-run  # show the three piles, write nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent.parent
INBOX = ROOT / "memory" / "inbox"
REMOTE = "upstream"
BRANCH = "main"
TRACE = "upstream-sync"
TRAILER = "Upstream-Seen"
# The mechanism half of the repository (docs/UPGRADING.md). README.md is left out on purpose:
# once the repository is theirs, the front page is theirs too.
MECHANISM = ["AGENTS.md", "CLAUDE.md", "INSTALL.md", "CONTRIBUTING.md", "docs", "setup",
             "memory/rules", "memory/tools"]
# Under a mechanism path but owned by the user.
OWNED = {"memory/tools/golden-set.md", "memory/tools/eval-log.csv"}
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def git(*a, check=False):
    p = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=300, env=ENV)
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {p.stderr.strip()[:300]}")
    return p


def machine() -> str:
    f = ROOT / "memory" / ".machine"
    if f.is_file() and f.read_text(encoding="utf-8").strip():
        return f.read_text(encoding="utf-8").strip()
    return os.environ.get("ASSISTANT_MACHINE") or socket.gethostname().split(".")[0].lower()


def norm_url(u: str) -> str:
    u = u.strip().lower().removesuffix(".git").rstrip("/")
    return re.sub(r"^(https?://|git@|ssh://git@)", "", u).replace(":", "/")


def last_seen() -> str | None:
    p = git("log", f"--grep=^{TRAILER}:", "-n", "1", "--format=%B")
    m = re.search(rf"^{TRAILER}:\s*([0-9a-f]{{40}})", p.stdout, re.M)
    return m.group(1) if m else None


def tree(rev: str) -> dict[str, str]:
    out = git("ls-tree", "-r", rev, "--", *MECHANISM, check=True).stdout
    files = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        if meta.split()[1] == "blob" and path not in OWNED:
            files[path] = meta.split()[2]
    return files


def history(rev: str) -> dict[str, set[str]]:
    """Every blob each mechanism path has ever had upstream."""
    out = git("log", rev, "--format=", "--raw", "--no-abbrev", "--no-renames", "--",
              *MECHANISM, check=True).stdout
    seen: dict[str, set[str]] = {}
    for line in out.splitlines():
        if not line.startswith(":"):
            continue
        meta, path = line.split("\t", 1)
        _, _, old, new, _ = meta.split()
        seen.setdefault(path, set()).update(b for b in (old, new) if set(b) != {"0"})
    return seen


def lint_green() -> bool:
    p = subprocess.run([sys.executable, str(TOOLS / "lint.py")], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    return p.returncode == 0


def breaking_headings(rev: str) -> list[str]:
    """'### ' sections of docs/UPGRADING.md that upstream has and this copy does not."""
    def heads(text: str) -> set[str]:
        return {l[4:].strip() for l in text.splitlines() if l.startswith("### ")}
    new = git("show", f"{rev}:docs/UPGRADING.md").stdout
    path = ROOT / "docs" / "UPGRADING.md"
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    return [h for h in sorted(heads(new) - heads(old))]


def sort_files(rev: str, prev: str | None):
    up, local, hist = tree(rev), tree("HEAD"), history(rev)
    before = tree(prev) if prev and git("cat-file", "-e", f"{prev}^{{commit}}").returncode == 0 else {}
    update, add, delete, custom = [], [], [], []
    for path in sorted(set(up) | set(local)):
        u, l = up.get(path), local.get(path)
        if u == l:
            continue
        if l is None:
            # Shipped last time and gone here → the owner deleted it; do not bring it back.
            (custom if path in before else add).append(path)
        elif l not in hist.get(path, ()):
            # An upstream file the owner edited — reported once per upstream change to it,
            # not on every release.
            if path in hist and before.get(path) != u:
                custom.append(path)
            # else: the owner's own file — not ours to mention
        elif u is None:
            delete.append(path)
        else:
            update.append(path)
    return update, add, delete, custom


def append_inbox(block: str) -> Path:
    now = dt.datetime.now()
    INBOX.mkdir(parents=True, exist_ok=True)
    path = INBOX / f"{now:%Y-%m-%d}--{machine()}.md"
    header = ""
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        header = (f"---\ntype: log\ndate: {now:%Y-%m-%d}\nmachine: {machine()}\n---\n"
                  f"# {now:%Y-%m-%d} ({machine()})\n")
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"{header}\n## {now:%H:%M}\n\n{block.rstrip()}\n")
    return path


def note(sha: str, prev: str | None, applied: list[str], removed: list[str], custom: list[str],
         breaking: list[str], rolled_back: bool) -> str:
    lines = [f"({TRACE}) The upstream template moved to {sha[:7]}."]
    if prev:
        n = git("rev-list", "--count", f"{prev}..{sha}").stdout.strip()
        if n:
            lines[0] += f" {n} commit(s) since the last look; `git log {prev[:7]}..{sha[:7]}` lists them."
    if rolled_back:
        lines.append(f"The update turned lint red, so it was rolled back and nothing changed. "
                     f"Take it by hand with docs/UPGRADING.md; {len(applied)} file(s) were ready.")
    elif applied:
        kept = [x for x in applied if x not in removed]
        if kept:
            lines.append(f"Updated automatically ({len(kept)}, none of them edited here): "
                         + ", ".join(kept))
        if removed:
            lines.append("Removed, as upstream removed them (unedited here): " + ", ".join(removed))
    if custom:
        lines.append(f"Customised here, so NOT updated ({len(custom)}). Ask the owner whether to "
                     f"take upstream's version, keep theirs, or merge — inspect with "
                     f"`git diff HEAD {sha[:7]} -- <path>`: " + ", ".join(custom))
    if breaking:
        lines.append("New breaking-change notes in docs/UPGRADING.md — read them, they may ask "
                     "for edits to the owner's own files: " + "; ".join(breaking))
    return "\n\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="look only; exit 0 = something new")
    ap.add_argument("--dry-run", action="store_true", help="show the piles, write nothing")
    a = ap.parse_args()

    url = git("remote", "get-url", REMOTE).stdout.strip()
    if not url:
        print(f"upstream-sync: no '{REMOTE}' remote, skipped (docs/UPGRADING.md to switch it on)")
        return 1 if a.check else 0
    if norm_url(url) == norm_url(git("remote", "get-url", "origin").stdout):
        print("upstream-sync: this is the upstream repository itself, skipped")
        return 1 if a.check else 0

    p = git("ls-remote", REMOTE, f"refs/heads/{BRANCH}")
    if p.returncode or not p.stdout.strip():
        print(f"upstream-sync: WARNING could not reach {REMOTE} — skipped, sleep goes on")
        return 1 if a.check else 0
    sha, prev = p.stdout.split()[0], last_seen()
    if sha == prev:
        print(f"upstream-sync: up to date ({sha[:7]})")
        return 1 if a.check else 0
    if a.check:
        print(f"upstream-sync: new upstream commit {sha[:7]} (last seen {prev[:7] if prev else 'never'})")
        return 0

    if git("status", "--porcelain").stdout.strip() and not a.dry_run:
        print("upstream-sync: working tree not clean — skipped, will look again next sleep")
        return 0
    git("fetch", "-q", REMOTE, BRANCH, check=True)

    update, add, delete, custom = sort_files(sha, prev)
    breaking = breaking_headings(sha)
    applied = update + add + delete
    if a.dry_run:
        for name, items in (("update", update), ("add", add), ("delete", delete),
                            ("customised (kept)", custom), ("breaking", breaking)):
            print(f"{name}: {', '.join(items) if items else '-'}")
        return 0

    green_before = lint_green()
    if update or add:
        git("checkout", sha, "--", *(update + add), check=True)
    if delete:
        git("rm", "-q", "--", *delete, check=True)
    rolled_back = False
    if applied and green_before and not lint_green():
        git("reset", "-q", "--hard", "HEAD", check=True)
        git("clean", "-fdq", "--", *add)
        rolled_back = True

    if custom or breaking or rolled_back or applied:
        append_inbox(note(sha, prev, applied, delete, custom, breaking, rolled_back))
    done = 0 if rolled_back else len(applied)
    msg = (f"upstream sync: {done} mechanism file(s) taken from {sha[:7]}"
           + (f", {len(custom)} customised kept" if custom else "")
           + (" (rolled back: lint)" if rolled_back else "")
           + f"\n\n{TRAILER}: {sha}\n")
    git("add", "-A", check=True)
    git("commit", "-q", "--allow-empty", "-m", msg, check=True)
    if git("push", "-q", "origin", BRANCH).returncode:
        git("pull", "-q", "--rebase", "--autostash", "origin", BRANCH)
        if git("push", "-q", "origin", BRANCH).returncode:
            print("upstream-sync: WARNING push failed; the commit is local and leaves with the next push")
    print(msg.splitlines()[0])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"upstream-sync: ERROR {e} — skipped, sleep goes on", file=sys.stderr)
        sys.exit(0)
