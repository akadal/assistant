# format.md — THE SINGLE SCHEMA AUTHORITY

This file is the single source of truth for every file schema, enum, budget and fact-grammar rule
in the memory core. `tools/lint.py` reads its configuration from the `lint-config` block at the
bottom of this file — schema and enforcement cannot drift apart (invariant #4). If the schema is
to change, this file changes first.

## Constitution (10 invariants)

1. L2 is append-only and immutable; L1 can always be re-derived from it.
2. Every consolidation is one atomic commit; risky operations get their own commit.
3. The single source of truth for "processed" is file location; there is no separate state file.
4. Lint is mechanical, is the only gate, and is identical for humans and models.
5. There is no deletion; forgetting = moving to `## History` / `archive/` + dropping from the index.
6. The root file holds no facts; volatile context lives in `state.md`.
7. Single-home: a fact has exactly one home, everything else links to it. Ambiguous bare names are a lint error.
8. Budgets are numbers (in characters) and they live in lint.
9. Data leaving the machine is default-deny: local embeddings only, `secret/` excluded, remote allowlist.
10. Only consolidation (and the human) writes to `domains/`, `people/`, the root and `state.md`.

## Language policy

**Structure is English; content is yours.** Directory names, file names, frontmatter keys, enum
values and section headings (`## Hot`, `## Files`, `## History`, `## Decisions`,
`## Context: <domain>`) are fixed English identifiers — they are schema, and lint checks them.
Everything else — prose, facts, summaries, titles, the assistant's replies — is written in the
language chosen during setup and recorded in `MEMORY.md`.

## File types and frontmatter schemas

Frontmatter is YAML. Keys are fixed English; controlled values are fixed English; body text is free.

### Root entry — `memory/MEMORY.md`

No frontmatter. A static contract: identity (2–3 lines) + domain routing table + protocol.
**It may not contain facts, personal names, or dated status.**

### `state.md` / `questions.md`

No frontmatter. `state.md` is capped at ~200 tokens; `questions.md` caps at 5 items.

### `todo.md` — a deliberately minimal task list

No frontmatter. Line grammar: `- [ ] open item` / `- [x] done`; related records are linked at the
end of the line as `[[id]]` (lint checks the targets). No due dates, no reminders, no priority
score — this is not a task manager (`docs/DESIGN.md` §1.3, a deliberately closed scope gate).
Anyone may append (human and assistant); consolidation drops completed `[x]` items from the list
(the record lives in git). Cap: 20 open items (lint warns).

### Index — `type: index` (`domains/*/_index.md`, `people/_index.md`)

```yaml
type: index
domain: <domain-name>     # required only for domains/*/_index.md
updated: YYYY-MM-DD
```

Body: `## Hot` (≤5 items, curated by consolidation) + `## Files` (mechanically reproducible; only
`status: active` files, each with its full path; closed ones collapse to a single count line).
Index lines carry **full paths**, never `[[wiki-links]]`.

### Topic — `type: topic` (`domains/<d>/*.md`)

```yaml
id: <file-name>            # identical to the file name without extension; immutable
type: topic
domain: <exactly-one>      # multiple domains are forbidden
title: "..."
summary: "..."             # lets a grep hit be discarded without opening the file — critical
status: active             # active | paused | closed
updated: YYYY-MM-DD
access: normal             # normal | rare (optional; rare drops to the index summary line)
```

Body sections: free-form, plus `## Decisions` (one line each, with `←[[archive-id]]` where it
applies) and `## History` (closed intervals; consolidation summarises it once it exceeds about a
third of the file budget) as needed.

### Person / Organisation — `type: entity` (`people/*.md`)

```yaml
id: <file-name>
type: entity
entity: person             # person | org
name: "Canonical Spelling"
aliases: ["..."]           # UNIQUE across the repo; the same alias in two files is a lint error
domains: [family, work]    # multiple allowed — this is the entity layer's reason to exist
updated: YYYY-MM-DD
```

Body: one identity line + `## Context: <domain>` per domain (≤5 lines of context + full-path
links). Entities carry no detail of their own.

### Log — `type: log` (`inbox/<YYYY-MM-DD>--<machine>.md`)

```yaml
type: log
date: YYYY-MM-DD
machine: <machine-alias>   # identical to the suffix in the file name
```

Body: `## HH:MM` blocks, append-only. There is no classification field — sorting is
consolidation's job, not capture's.

### Archive — everything under `archive/`

Raw, immutable, free-form; frontmatter optional (`type: archive` recommended). The path
`archive/<domain>/YYYY/` carries a domain segment — this is required for the bleed filter.

## Fact grammar (temporality)

```
- [YYYY-MM-DD]         Point fact (it happened that day).
- [YYYY-MM-DD→]        Ongoing state (still true).
- [t1→t2]              Closed interval — ONLY inside a ## History section.
- [void: YYYY-MM-DD]   Correction — the fact was WRONG FROM THE START; never used in temporal reasoning.
- (?)                  Disputed fact (a question is pending) — presented as "disputed" on retrieval.
- ←[[archive-id]]      Provenance: end-of-line link on a fact distilled from an archive document.
```

**An update is not a correction.** A state transition moves the old line down into `## History`
with a closing date. A mis-recorded fact gets `[void:]` instead — it never earns a place in history
as "once true". Invalidated lines are **never deleted**.

## Naming

- File and folder names are **ASCII kebab-case**. Transliterate non-ASCII characters rather than
  using them: filesystem normalisation differs between macOS (NFD) and Linux (NFC), which produces
  phantom git changes and breaks grep patterns.
- **ID = file name without extension**, unique across the repo, immutable. Renaming is a last
  resort; if you must, do `git mv` + link updates + adding the old name to `aliases`, in one commit.
- **In sub-foldered files, ID = `<folder>-<file-name>`.** For example
  `domains/learning/databases/week03.md` has the ID `databases-week03`. Reason: sub-folders repeat
  the same file names (`week03`, `overview`) across different subjects, and a bare file name would
  break uniqueness. `[[wikilinks]]` use this full ID; lint computes it from the path.
- Sub-folders are allowed under `domains/<d>/`, but only to group parts of the same thing; the
  cover file of such a group is named `overview.md`.
- Time-bound files: `YYYY-MM-DD-slug.md`. Timeless ones: `slug.md`.
- Namesake rule: add a distinguishing suffix to the file name (`alex-rivera-neighbour` vs
  `alex-rivera-colleague`); the real spelling lives in `name`/`aliases`.

## Budgets (enforced by lint)

Conversion: ~4 characters ≈ 1 token (English). Target / ceiling, in characters:

| File | Target | Ceiling |
|---|---|---|
| `MEMORY.md` | 2,000 | 3,200 |
| `state.md` | — | 800 |
| index | 1,600 | 2,000 |
| topic | 1,600 | 2,800 |
| entity | 1,000 | 1,600 |
| log / archive | free | free |

An L1 file over its ceiling is compressed or split during consolidation. If your language packs
noticeably fewer characters per token than English, lower `char_per_token` and scale the budgets
down proportionally — budgets exist to bound *tokens*; characters are only the mechanical proxy.

## Scope of link checking

Path and `[[link]]` target checks apply **only to the L1 routing surface** (root, `state.md`,
`questions.md`, `todo.md`, index, topic, entity). `archive/` is exempt.

Within a checked file, links inside **code spans, fenced blocks and HTML comments are ignored**.
A `[[link]]` written between backticks is documentation *about* the grammar, not a pointer to
resolve. Without this rule, any file that explains the link syntax — every template ships one —
would fail lint on day one, and the only way to go green would be to stop documenting the syntax.

Reason: L2 is immutable (invariant #1) and records the paths that were correct when it was written.
If a file is legitimately moved or removed, the archive's reference "breaks" but cannot be fixed —
fixing it would mean writing to L2. Without this exemption invariants #1 and #4 conflict with no
resolution: the repo goes permanently red and consolidation can never commit again. In the archive
a path is *history*, not routing; a broken pointer is only a real fault in L1.

## lint-config (mechanical — tools/lint.py reads this block)

```yaml
lint-config:
  char_per_token: 4.0
  budgets_chars:        # [target, ceiling]; null = not checked
    root:   [2000, 3200]
    state:  [null, 800]
    questions_item_cap: 5
    todo_open_item_cap: 20
    index:  [1600, 2000]
    topic:  [1600, 2800]
    entity: [1000, 1600]
  enums:
    type:   [index, topic, entity, log, archive]
    status: [active, paused, closed]
    entity: [person, org]
    access: [normal, rare]
  required:
    index:  [type, updated]
    index_domain_extra: [domain]        # only for domains/*/_index.md
    topic:  [id, type, domain, title, summary, status, updated]
    entity: [id, type, entity, name, aliases, domains, updated]
    log:    [type, date, machine]
  date_format: "YYYY-MM-DD"
```
