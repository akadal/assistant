# consolidation.md — the sleep-consolidation task definition

This file is read **only during a consolidation run** (`docs/DESIGN.md` §5.2). It is triggered by
hand (`/sleep`, or just "run a consolidation"), or opportunistically at the start of a session
(`AGENTS.md` §0.2).

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
     5. Resolve conflicts — using the ordered rules below.
     6. Refresh the `## Hot` / `## Files` blocks of every touched index; refresh `state.md`.
     7. Sweep `todo.md`: drop completed `[x]` items (the record lives in git); firm up the
        `[[link]]`s on the open ones.
   - **Output:** file updates + `questions.md` items (cap: 5).
3. **Lint (script):** `python3 memory/tools/lint.py` — if red, the model gets exactly one repair
   attempt; if still red, abort (`git reset --hard pre-sleep`).
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
