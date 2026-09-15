#!/usr/bin/env python3
"""question-pick.py — picks the one question to ask this session.

Why this exists: the drip rule ("at most one question per session") said *how many* but never
*which one* or *when*. Measured result in the reference deployment: `questions.md` sat with the
same five items for 11 days; four of them were tied to classes that meanwhile started, so they
rotted unasked. The drip rule is kept; the selection is now mechanical and the session-start hook
injects it into context. The queue shrinks by being drained, not by being trimmed.

Selection: items with `asked` at the cap are skipped (consolidation closes those with the status
quo). The rest are ordered by EFFECTIVE DUE DATE — the `due` date if present, otherwise the date
the question was written plus 30 days, so an undated question moves to the front as it ages.
Overdue items come first: one last chance before they close.

Usage:
  python memory/tools/question-pick.py           # one context line (silent if none, exit 0)
  python memory/tools/question-pick.py --asked   # bump the selected item's counter after asking
  python memory/tools/question-pick.py --json

Dependencies: stdlib only. Grammar authority: `memory/rules/format.md` (`questions_grammar`).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QUESTIONS = ROOT / "memory" / "questions.md"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

UNDATED_LIFE = 30   # a question with no `due` is treated as due this many days after it was written
ASKED_CAP = 2       # once asked this many times, it never surfaces again (consolidation closes it)

ITEM_RE = re.compile(
    r"^- \[(?P<written>\d{4}-\d{2}-\d{2})\] (?P<kind>approval|conflict|fact)"
    r"(?: · due (?P<due>\d{4}-\d{2}-\d{2}))?"
    r"(?: · asked (?P<asked>\d+))? — (?P<body>.*)$"
)


def items(text: str) -> list[dict]:
    out = []
    for no, ln in enumerate(text.splitlines()):
        m = ITEM_RE.match(ln)
        if m:
            d = m.groupdict()
            d["line_no"] = no
            d["asked"] = int(d["asked"] or 0)
            out.append(d)
    return out


def effective_due(item: dict) -> dt.date:
    if item["due"]:
        return dt.date.fromisoformat(item["due"])
    return dt.date.fromisoformat(item["written"]) + dt.timedelta(days=UNDATED_LIFE)


def pick(its: list[dict]) -> dict | None:
    eligible = [i for i in its if i["asked"] < ASKED_CAP]
    return min(eligible, key=effective_due) if eligible else None


def summary(body: str) -> str:
    m = re.search(r"\*\*(.+?)\*\*", body)
    text = m.group(1) if m else body.split(" Status quo:")[0]
    return " ".join(text.split())


def mark_asked(item: dict) -> None:
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    ln = lines[item["line_no"]]
    n = item["asked"] + 1
    if item["asked"]:
        ln = ln.replace(f" · asked {item['asked']} — ", f" · asked {n} — ", 1)
    else:
        ln = ln.replace(" — ", f" · asked {n} — ", 1)
    lines[item["line_no"]] = ln
    QUESTIONS.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    if not QUESTIONS.exists():
        return 0
    its = items(QUESTIONS.read_text(encoding="utf-8"))
    chosen = pick(its)

    if "--asked" in sys.argv:
        if chosen:
            mark_asked(chosen)
            print(f"asked counter bumped: {summary(chosen['body'])[:60]}")
        return 0

    if "--json" in sys.argv:
        print(json.dumps({} if not chosen else {
            "written": chosen["written"], "kind": chosen["kind"], "due": chosen["due"],
            "asked": chosen["asked"], "question": summary(chosen["body"]),
        }, ensure_ascii=False))
        return 0

    if not chosen:
        return 0

    today = dt.date.today()
    left = (effective_due(chosen) - today).days
    if left < 0:
        when = f"{-left} days OVERDUE"
    elif chosen["due"]:
        when = f"due {chosen['due']} ({left} days)"
    else:
        when = f"no due date, waiting {(today - dt.date.fromisoformat(chosen['written'])).days} days"

    print(f"Question of the day [{chosen['kind']} · {when} · asked {chosen['asked']}]: "
          f"{summary(chosen['body'])}")
    print("  → Ask it once, at a natural moment, in a single sentence (at most one question per "
          "session). Then run `python memory/tools/question-pick.py --asked`. If it gets answered, "
          "append the answer to the inbox and remove the item from questions.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
