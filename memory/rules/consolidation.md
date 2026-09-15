# consolidation.md — the sleep-consolidation task definition

This file is read **only during a consolidation run** (`docs/DESIGN.md` §5.2). It is triggered by
hand (`/sleep`, or just "run a consolidation"), or opportunistically at the start of a session
(`AGENTS.md` §0.3).

## Flow (mechanical wrapper around one LLM pass)

0. **Source pull (if configured):** pull whatever changed since the last fetch from the external
   read taps defined in `secret/sources.md`, and append a summary plus a provenance trace to the
   inbox. On error, tell the user and continue — a dead tap never blocks a consolidation.
1. **Pre-flight (script):** is the working tree clean → create a `pre-sleep` checkpoint commit.
2. **LLM pass** (as much sub-context per domain as it needs):
   - **Input:** the unprocessed `inbox/` logs + the relevant `_index` files + the target files +
     the *entire* alias table from `people/_index.md` (it is small, and namesake detection needs all of it).
   - **Task:**
     1. Triage — do not distil what carries no lasting value.
     2. Sort — pick the target file; open a new one if none fits (naming: `rules/format.md`).
     3. Merge/update — follow the fact grammar; if you find a duplicate, turn it into a link (single-home).
     4. **COMPRESS** — as hard as you can. Budgets are targets, not ceilings. Because the raw data
        is still in the archive, aggressive distillation is lossless (`docs/DESIGN.md` §13.4).
        **Quota:** every run pulls **at least three** files that sit above 90% of their ceiling
        down to (or near) their target. This is not a new idea — the sentence above said it from
        day one and was still ignored: in the reference deployment, 20 of 61 topic files ended up
        in the 95-100% band with none over the ceiling, and two sat exactly at the ceiling. That
        is "avoid the red", not "distil". Note also *where* the bloat is: moving text into
        `## History` is usually the wrong move (those sections were 1.2 KB in total). Bloat comes
        from operational detail — measurement narratives, command dumps, screen-by-screen flows.
        Those go to `memory/archive/<domain>/YYYY/`, leaving a `←[[archive-id]]` marker in L1.
        `sleep-audit.py` enforces this with its BLOAT and RATCHET checks.
     5. Resolve conflicts — using the ordered rules below.
     6. Refresh the `## Hot` / `## Files` blocks of every touched index; refresh `state.md`.
     7. Sweep `todo.md`: drop completed `[x]` items (the record lives in git); firm up the
        `[[link]]`s on the open ones.
   - **Output:** file updates + `questions.md` items (**no cap** — see the question queue section).
3. **Two gates (scripts):** `python3 memory/tools/lint.py` **and**
   `python3 memory/tools/sleep-audit.py` — both must be green before the commit. Lint checks the
   schema; the audit checks the distillation itself (fabrication, loss, bloat, ratchet, L2
   integrity). If either is red the model gets exactly one repair attempt; if still red, abort
   (`git reset --hard pre-sleep`). Once sleep runs unattended, this pair replaces the human diff
   review — it is not optional.
4. **Close-out:** move the processed logs into `archive/inbox/` → one atomic commit (the message
   carries a cost figure and a `wc` size summary) → human diff review → `git push`.

   **Name-collision rule (mechanical):** if a second consolidation runs on the same day,
   `archive/inbox/<date>--<machine>.md` already exists. An existing target is **never overwritten**
   (L2 is immutable, invariant #1); add a sequence suffix instead: `<date>--<machine>-2.md`.

If a run goes wrong: `git reset --hard pre-sleep` and run it again. Re-running is cheaper than
making a 40k-token pass resumable.

## Conflict resolution (first match wins)

0. **State transition or recording error?** If the provenance points at the same event, assume an
   error → `[void: t]`.
1. **Temporality:** if it is a state transition, apply the update (the old line drops into
   `## History` with a closing date).
2. **Layered source trust, then recency:** user's own statement > user's document > third
   party / model inference. Low-trust new information may not overwrite high-trust old
   information → `questions.md`. A phrase carrying a temporariness signal ("for now", "this term")
   does not overwrite a durable fact; it is written alongside it.
3. **Ask threshold:** a high-impact area (identity, relationships, health, finance) or two
   user statements close together in time → do not resolve automatically, ask. A fact awaiting an
   answer stays in the file marked `(?)`.

## The question queue — how it drains

`questions.md` has **no cap**. It shrinks by being drained, not trimmed, through three mechanisms:

1. **Drip.** `tools/question-pick.py` picks exactly one question per session by effective due date
   (the `due` date, or the written date + 30 days) and the session-start hook injects it.
2. **Status-quo close.** Every run: any item whose `due` has passed, or that has been `asked`
   twice, is **closed even without an answer**. The item leaves `questions.md`, the status-quo note
   is written next to the `(?)` fact in the relevant file, and the close is logged to the inbox.
   Silence is not a blocker.
3. **The right queue.** Only things awaiting an *answer* belong here: `approval`, `conflict`,
   `fact`. Decisions and tasks go to `todo.md`.

A status-quo note is **not a decision**: it records what was assumed in the absence of an answer
and stays marked `(?)`. A later statement from the owner overrides it (trust ladder).

## Feedback triage

Blocks tagged `(feedback)` in the inbox are triaged first. They are captured **without
classification** — the agent records what was said and what happened; this file decides whether
anything structural follows.

| Situation | Response |
|---|---|
| The same complaint arrives a **second time** | **Structural change**: a rule, a tool, or a mechanical check. A prose warning is not enough — it was already written the first time. |
| First time, but the cause is a **mechanism gap** (no rule, no trigger, no check) | Structural change. |
| First time, cause was a **one-off slip** | Record the fact; write no rule. If it repeats it moves up a row. |
| The complaint is a **preference** (tone, format, scope) | Goes to the preferences file, not to a rule file. |
| The complaint was fair but the **system was already right** | **Write nothing.** The block is archived and no rule changes. |

Repeat detection is mechanical and needs no separate register file:

```
rg -n "\(feedback\)" memory/archive/inbox/ memory/inbox/
```

The archive is already a permanent, append-only record (invariant #1); a second counter file would
be the same fact's second home (invariant #7) and would go stale.

**The default outcome is "no change."** A structural update has to earn itself: either there is a
match in the archive (a repeat) or a demonstrable mechanism gap. With neither, close the block and
leave the rule files alone. Writing a rule "just in case" is a mistake in this system.

**Inflation brake — mechanise the trigger, not the judgement.** `AGENTS.md` carries a lint budget.
While it is over target, adding a new operating rule requires answering, explicitly, *which old
rule was absorbed or died?*; if the ceiling is red, **nothing new goes in until something comes
out** — zero-sum. Two classes of rule are death candidates: (a) one whose enforcement moved into a
mechanism (the prose collapses to a single line), and (b) a one-off incident rule with no repeat
(the rationale goes to the archive, one sentence stays). This matters because the feedback loop is
exactly what inflates a router: in the reference deployment `AGENTS.md` grew 5.2× in 25 days and
this loop was the main driver. The loop is valuable; the unchecked version of it is not.

## Approval gates (the default — not applied automatically; they land in `questions.md` as a diff)

- (a) merging two entities
- (b) attaching a new name to an existing entity (adding an alias)
- (c) any change that drops content without a source
- (d) opening or closing a domain (threshold: ≥5 unfileable records on the same theme; rate limit:
      at most one proposal per month)

**Mechanical namesake pre-rule:** if a name in a record matches more than one entity in the alias
table, **or** matches none of them exactly, automatic assignment is forbidden → `questions.md`.
This is a mechanical rule, not a polite request to be careful.

## Prohibitions

- Consolidation has no `delete` power; output containing `git rm` is rejected outright. Forgetting
  is a move to `## History` / `archive/` plus dropping the index line.
- `secret/` is not read.
- This task is the write gate. Outside it, nothing writes to `domains/`, `people/`, the root or
  `state.md` — except the human, whose direct edits are a first-class path.
