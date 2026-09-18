#!/usr/bin/env python3
"""sleep-audit.py — mechanical quality audit of a consolidation diff.

Why this exists: once sleep runs unattended (scheduled nightly run), the human diff review is
gone. `lint.py` checks the *schema*; nothing checked the *distillation itself*. The failure it
catches is not hypothetical — it was measured in the reference deployment: `consolidation.md` had
said "budgets are targets, not ceilings; aggressive distillation is lossless" for 25 days, yet
20 of 61 topic files sat in the 95-100% band of the ceiling and none went over. Consolidation was
optimising "don't turn the lint red" instead of "distil". Prose alone could not stop that; a
mechanical gate can.

Five checks, all diff-based (no LLM):
  1. FABRICATION — a dated fact added to L1 must have its date somewhere in the raw layer.
  2. LOSS        — a removed dated line's CONTENT must survive (same file, History, or archive).
  3. BLOAT       — the number of files in the ceiling band must not grow.
  4. RATCHET     — a file pressed against the ceiling may not grow at all.
  5. L2          — archive is append-only; memory *content* is never deleted (operational
                   state such as memory/.sleep-lock is outside that rule).

Usage:
  python memory/tools/sleep-audit.py            # working tree vs HEAD (before committing)
  python memory/tools/sleep-audit.py --last     # audit the most recent 'sleep:' commit
  python memory/tools/sleep-audit.py --last <sha>

Exit: 0 = green (safe to commit), 1 = red (do not commit; fix, or reset --hard pre-sleep).
Dependencies: stdlib + git.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY = ROOT / "memory"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

BAND = 0.95              # above this fraction of the ceiling counts as "pressed against it"
RATCHET_TOLERANCE = 150  # growth below this on an over-target file is normal evolution

# Calibration note: the first version turned red when an over-target file grew by 3 characters.
# That blocks even a factual correction — too strict to live with. The line drawn instead:
# any growth of a file already in the ceiling band is pathological (that is exactly where the
# "lean on the ceiling instead of distilling" behaviour is produced); growth of an over-target
# file that is not yet in the band is normal unless it exceeds RATCHET_TOLERANCE.

DATE_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2})")
L1_RE = re.compile(r"^memory/(domains|people)/.*\.md$")
EXEMPT_RE = re.compile(r"←\s*\[\[|\[\[archive|\(default:")

errors: list[str] = []
warnings: list[str] = []


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout or ""


def budgets() -> dict:
    """format.md is the single schema authority (invariant #4) — budgets are read from it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_lint", Path(__file__).parent / "lint.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return (m.load_config().get("budgets_chars") or {})


def kind(path: str) -> str | None:
    if not L1_RE.match(path):
        return None
    if path == "memory/people/_index.md":
        # Same budget as lint uses [2026-09-18]. If the two gates read different budgets the
        # calibration is only half done -- the "ported but the caller stayed behind" failure.
        return "people_index"
    if path.startswith("memory/people/"):
        return "index" if path.endswith("_index.md") else "entity"
    return "index" if path.endswith("_index.md") else "topic"


def collect(base: str, target: str | None) -> dict:
    span = [base] if target is None else [base, target]
    files = []
    for ln in git("diff", "--name-status", "-M", *span).splitlines():
        p = ln.split("\t")
        if len(p) >= 2:
            files.append((p[0], p[1], p[-1]))

    added, removed = {}, {}
    # Untracked files are invisible to `git diff`. When consolidation moves detail into a NEW
    # archive file, that file is not tracked yet; without this the audit cannot see it and reads
    # the move as a loss (false red) — or worse, leaves a hole where a real loss could hide.
    if target is None:
        for ln in git("status", "--porcelain").splitlines():
            if ln.startswith("?? "):
                rel = ln[3:].strip().strip('"')
                f = ROOT / rel
                if f.is_file() and rel.endswith(".md"):
                    files.append(("A", rel, rel))
                    added.setdefault(rel, []).extend(
                        f.read_text(encoding="utf-8", errors="replace").splitlines())

    current = None
    for ln in git("diff", "-U0", "-M", *span).splitlines():
        if ln.startswith("+++ b/"):
            current = ln[6:]
        elif ln.startswith("+") and not ln.startswith("+++") and current:
            added.setdefault(current, []).append(ln[1:])
        elif ln.startswith("-") and not ln.startswith("---") and current:
            removed.setdefault(current, []).append(ln[1:])
    return {"files": files, "added": added, "removed": removed}


def content(path: str, ref: str | None) -> str:
    if ref is None:
        f = ROOT / path
        return f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
    return git("show", f"{ref}:{path}")


def words(text: str) -> set:
    """Content words: 4+ characters, lowercased. Markdown and punctuation dropped."""
    return {w for w in re.sub(r"[^\w\s]", " ", text.lower()).split()
            if len(w) >= 4 and not w.isdigit()}


def check_fabrication(d: dict, target: str | None) -> None:
    pool = []
    for f in sorted((MEMORY / "archive" / "inbox").glob("*.md")) + sorted((MEMORY / "inbox").glob("*.md")):
        pool.append(f.read_text(encoding="utf-8", errors="replace"))
    for path, lines in d["added"].items():
        if path.startswith("memory/archive/"):
            pool.append("\n".join(lines))
    raw = "\n".join(pool)

    for path, lines in d["added"].items():
        if not kind(path):
            continue
        before = content(path, "HEAD" if target is None else f"{target}^")
        for ln in lines:
            if EXEMPT_RE.search(ln):
                continue
            for date in DATE_RE.findall(ln):
                if date in raw or date in before:
                    continue
                errors.append(f"FABRICATION  {path}: [{date}] is nowhere in the raw layer "
                              f"→ {ln.strip()[:70]}")


def check_loss(d: dict, target: str | None) -> None:
    """A removed dated line's CONTENT must survive somewhere.

    The first version compared only the DATE stamp and failed its own negative test: deleting
    three dated lines left the audit green, because another line (even the archive file's own
    "facts are dated 2026-09-09" sentence) carried the same date. A date is not a fact's identity;
    its content is. The 40% threshold is deliberately loose — consolidation *rewrites* lines when
    it compresses, so demanding an exact match would redden every run. Rewording passes;
    evaporation does not.
    """
    added_pool = []
    for v in d["added"].values():
        added_pool.extend(v)
    pool_added = words(" ".join(added_pool))

    for path, lines in d["removed"].items():
        if not kind(path):
            continue
        pool = pool_added | words(content(path, target))
        for ln in lines:
            if "[void:" in ln or not ln.strip() or not DATE_RE.search(ln):
                continue
            ws = words(re.sub(r"\[\d{4}-\d{2}-\d{2}[^\]]*\]", "", ln))
            if len(ws) < 3:
                continue
            ratio = len(ws & pool) / len(ws)
            if ratio < 0.4:
                errors.append(f"LOSS         {path}: content evaporated ({int(ratio * 100)}% left) "
                              f"→ {ln.strip()[:70]}")


def check_bloat_and_ratchet(d: dict, target: str | None) -> None:
    b = budgets()
    before_ref = "HEAD" if target is None else f"{target}^"
    band_before = band_after = 0

    # Only CHANGED files are walked: an unchanged file contributes equally to both sides and
    # cancels out in the "did the band grow?" question.
    for path in sorted(set(list(d["added"]) + list(d["removed"]))):
        k = kind(path)
        if not k or k not in b or not b[k]:
            continue
        target_b, ceiling = b[k]
        if not ceiling:
            continue
        n_after = len(content(path, target))
        n_before = len(content(path, before_ref))
        if n_before > ceiling * BAND:
            band_before += 1
        if n_after > ceiling * BAND:
            band_after += 1
        if target_b and n_after > n_before:
            growth = n_after - n_before
            if n_before > ceiling * BAND:
                errors.append(f"RATCHET      {path}: was against the ceiling ({n_before}/{ceiling}) "
                              f"and grew (+{growth}) — compress, or move detail to the archive")
            elif n_before > target_b and growth > RATCHET_TOLERANCE:
                errors.append(f"RATCHET      {path}: was over target ({n_before} > {target_b}) and "
                              f"grew by {growth} (tolerance {RATCHET_TOLERANCE}) — compress")

    band_total = 0
    for p in MEMORY.rglob("*.md"):
        rel = p.relative_to(ROOT).as_posix()
        k = kind(rel)
        if not k or k not in b or not b[k] or not b[k][1]:
            continue
        if len(p.read_text(encoding="utf-8", errors="replace")) > b[k][1] * BAND:
            band_total += 1

    if band_after > band_before:
        errors.append(f"BLOAT        files in the top {int(BAND * 100)}% band grew "
                      f"({band_before} → {band_after}) — budgets are targets, not ceilings")
    elif band_total:
        warnings.append(f"{band_total} files sit in the top {int(BAND * 100)}% band "
                        f"(not increased by this run) — see the compression quota in consolidation.md")


def check_l2(d: dict, target: str | None) -> None:
    for status, old, new in d["files"]:
        # "There is no deletion" is about memory CONTENT: fact files, the archive, entities.
        # Operational state (dotfiles under memory/, such as memory/.sleep-lock) and logs moving
        # out of inbox are outside it — releasing the lock IS the protocol (§6), not a breach.
        # The first version counted the lock and turned every sleep commit red; it did not show up
        # in the pre-commit check because the lock is still held at that moment.
        operational = old.startswith("memory/.") or old.startswith("memory/inbox/")
        if status.startswith("D") and old.startswith("memory/") and not operational:
            errors.append(f"L2           {old}: deleted — there is no deletion (invariant #5)")
        if status.startswith("R") and old.startswith("memory/inbox/"):
            if not new.startswith("memory/archive/inbox/"):
                errors.append(f"L2           {old} → {new}: a processed log belongs in archive/inbox/")
            elif content(old, "HEAD" if target is None else f"{target}^").strip() != content(new, target).strip():
                errors.append(f"L2           {new}: content changed while archiving (L2 is immutable)")
        if status.startswith("M") and old.startswith("memory/archive/"):
            errors.append(f"L2           {old}: an archive file was modified (append-only, invariant #1)")


def main() -> int:
    argv = sys.argv[1:]
    target = None
    if "--last" in argv:
        i = argv.index("--last")
        sha = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else ""
        if not sha:
            sha = git("log", "--format=%H", "--grep=^sleep:", "-1").strip()
        if not sha:
            print("sleep-audit: no sleep commit found to audit")
            return 0
        target, base = sha, f"{sha}^"
        print(f"sleep-audit: {sha[:8]} — {git('log', '-1', '--format=%s', sha).strip()}")
    else:
        base = "HEAD"
        print("sleep-audit: working tree vs HEAD (pre-commit)")

    d = collect(base, target)
    if not d["files"]:
        print("sleep-audit: no changes — green")
        return 0

    check_fabrication(d, target)
    check_loss(d, target)
    check_bloat_and_ratchet(d, target)
    check_l2(d, target)

    for w in warnings:
        print(f"WARN   {w}")
    for e in errors:
        print(e)
    if errors:
        print(f"sleep-audit: RED — {len(errors)} finding(s). Do not commit; fix, or "
              f"`git reset --hard pre-sleep`.")
        return 1
    print(f"sleep-audit: green — {len(d['files'])} file(s) audited, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
