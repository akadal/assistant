#!/usr/bin/env python3
"""eval.py — golden-set runner + cost logging (docs/DESIGN.md §9.1, §10).

Usage:
  python3 eval.py run      # walks the questions in golden-set.md interactively
  python3 eval.py report   # prints summary metrics from eval-log.csv

How a run works: each question is shown, you (or the assistant) produce the answer, and a
HUMAN enters the score. Grade by hand for the first three months — an LLM judge makes it far
too easy to fool yourself; promote one only once it agrees with you ≥90% of the time.

Each record: date, question id, category, language, correct (0/1), turns, tokens, note.
The north star — accuracy divided by median effective cost — is reported as a single number.
"""

from __future__ import annotations

import csv
import re
import statistics
import sys
from datetime import date
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
GOLDEN = TOOLS / "golden-set.md"
LOG = TOOLS / "eval-log.csv"

# Some Windows consoles default to a legacy codepage and mangle non-ASCII output.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

FIELDS = ["date", "question_id", "category", "language", "correct", "turns", "tokens", "note"]
CATEGORIES = ("single-fact", "synthesis", "temporal", "update", "abstention", "confusion-trap")

# docs/DESIGN.md §10.2 — v1 thresholds
THRESHOLDS = {
    "accuracy": 0.75,
    "abstention": 0.80,
    "single_fact_median_turns": 2,
}


def load_questions() -> list[dict]:
    if not GOLDEN.exists():
        return []
    text = GOLDEN.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(
        r"^## (Q\d+)\s*\n.*?category:\s*(\S+).*?language:\s*(\S+).*?question:\s*(.+?)\n.*?expected:\s*(.+?)(?:\n##|\n---|\Z)",
        text, re.S | re.M,
    ):
        out.append({
            "id": m.group(1),
            "category": m.group(2).strip(),
            "language": m.group(3).strip(),
            "question": " ".join(m.group(4).split()),
            "expected": " ".join(m.group(5).split()),
        })
    return out


def cmd_run() -> int:
    qs = load_questions()
    if not qs:
        print("No questions in golden-set.md yet. Add yours first — the template is in the file.")
        return 1
    print(f"{len(qs)} question(s). Grading is manual: correct? [y/n] (on an abstention question, "
          f"saying \"not in my memory\" IS the correct answer). Ctrl+C stops early.\n")
    fresh = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if fresh:
            w.writeheader()
        for q in qs:
            print(f"--- {q['id']} [{q['category']}/{q['language']}]")
            print(f"Question: {q['question']}")
            print(f"Expected: {q['expected']}")
            try:
                correct = input("Correct? [y/n]: ").strip().lower().startswith("y")
                turns = int(input("Turns (tool calls): ").strip() or "0")
                tokens = int(input("Tokens read (approx): ").strip() or "0")
                note = input("Note (optional): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nStopped early; what you entered is in the log.")
                break
            w.writerow({
                "date": date.today().isoformat(), "question_id": q["id"],
                "category": q["category"], "language": q["language"],
                "correct": int(correct), "turns": turns, "tokens": tokens, "note": note,
            })
            f.flush()
    cmd_report()
    return 0


def cmd_report() -> int:
    if not LOG.exists():
        print("No eval-log.csv yet — run 'run' first.")
        return 1
    rows = list(csv.DictReader(LOG.open(encoding="utf-8")))
    if not rows:
        print("The log is empty.")
        return 1
    latest: dict[str, dict] = {}
    for r in rows:  # keep only the most recent run per question
        latest[r["question_id"]] = r
    rs = list(latest.values())
    n = len(rs)
    accuracy = sum(int(r["correct"]) for r in rs) / n
    turns = [int(r["turns"]) for r in rs]
    tokens = [int(r["tokens"]) for r in rs]
    median_turns = statistics.median(turns)

    print(f"\n=== Golden-set report ({date.today().isoformat()}) ===")
    print(f"Questions      : {n} (target: 20)")
    print(f"Accuracy       : {accuracy*100:.0f}% (v1 threshold: {THRESHOLDS['accuracy']*100:.0f}%)")
    print(f"Median turns   : {median_turns:.1f} (single-fact target ≤{THRESHOLDS['single_fact_median_turns']})")
    print(f"Median tokens  : {statistics.median(tokens):.0f} (single-fact target ≤1000)")
    print(f"North star     : {accuracy/max(median_turns, 0.5):.2f} accuracy per median turn")
    for cat in CATEGORIES:
        sub = [r for r in rs if r["category"] == cat]
        if sub:
            hits = sum(int(r["correct"]) for r in sub)
            print(f"  {cat:16s}: {hits/len(sub)*100:.0f}% ({hits}/{len(sub)})")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    sys.exit({"run": cmd_run, "report": cmd_report}.get(cmd, cmd_run)())
