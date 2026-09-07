# Golden set — versioned evaluation questions (docs/DESIGN.md §10.1)

This file starts empty on purpose. The questions have to come from **your** life, or the
measurement is meaningless. Add them as your memory fills up — roughly five in the first week,
then the rest over the following month.

Rules:

- Target **20 questions**; an old question is **never deleted** (only new ones are appended, IDs stay sequential).
- Distribution at full size: single-fact 6 · synthesis 3 · temporal 3 · update 3 · abstention 3 · confusion-trap 2+
- Mix languages if your memory is multilingual, and include at least three cross-language questions
  (ask in language A about content stored in language B) — this is where retrieval usually breaks first.
- Grade by hand for the first three months.
- Write some of the questions **two or more weeks after** the events they ask about. Natural
  forgetting is what makes the test realistic; questions written from fresh memory are too kind.

Run them with: `python3 memory/tools/eval.py run` — results land in `eval-log.csv`.

## Question format

```
## Q<n>
category: single-fact | synthesis | temporal | update | abstention | confusion-trap
language: <language tag, e.g. en, de, tr, or "cross">
question: <one line, worded the way you would actually ask it>
expected: <the core of the correct answer; for abstention, "must say it is not in memory">
```

## What each category is for

| Category | What it tests | Example shape |
|---|---|---|
| single-fact | Plain retrieval | "What is X's thesis topic?" |
| synthesis | Pulling one answer from several sessions | "What decisions did I make on project Y?" |
| temporal | Ordering and validity over time | "Did I decide that before or after Z?" |
| update | Returning the *current* value, not the old one | Something whose value changed |
| abstention | Not making things up | Something genuinely not in memory |
| confusion-trap | Domain isolation | Two namesakes, or similar entities in different domains |

A leak on a confusion-trap question is an alarm, not a rounding error: it means the single-home
rule has been violated somewhere.

---

<!-- Add your questions below this line. Nothing here yet — that is the expected state on day one. -->
