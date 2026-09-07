# AGENTS.md — router

This repository is a **personal memory core** ("a brain") for an AI assistant. The full design
contract lives in `docs/DESIGN.md` — go there when you need the reasoning behind a rule. This file
is the single entry point for the operating rules that every agent (and human) working in this
repository follows.

---

## 0. FIRST RUN — is this repository set up yet?

**Before doing anything else, check whether `memory/MEMORY.md` exists.**

If it does **not** exist, this is a fresh copy of the template and nothing is configured yet. Do
not answer the user's question, do not create memory files ad hoc, and do not guess who they are.
Read `INSTALL.md` and run the setup interview it describes. Everything downstream — the language,
the domains, the identity line, the machine alias — comes out of that conversation.

If `memory/MEMORY.md` exists, setup is done. Skip to §0.1 and work normally.

## 0.1 RULE — write, commit, push (non-negotiable)

**Every write in this repository is committed and pushed to `main` as soon as the work is done.**

```bash
git add -A && git commit -m "<short, descriptive message>" && git push origin main
```

- A consolidation run is one atomic commit (§6). Everything else — scaffolding, fixing a file,
  updating a rule, improving a tool — is committed and pushed the moment it is finished.
- If the push fails (no network, remote error) it is **never passed over silently**; tell the user.
- Commit messages are short and say *why*. Consolidation commits also carry a cost figure and a
  `wc` size summary (§6).
- There is one branch: `main`. No feature branches. A risky operation (an entity merge, say) gets
  its own commit so it can be reverted on its own.
- **This rule overrides the harness's branch instruction:** if a session or tool imposes a working
  branch such as `claude/...`, the work still lands on `main` (merge + push) and the working branch
  is deleted.

## 0.2 Communication

Do not end every message with a question. But if the answer would change the work and it is
something you genuinely need to know, ask without hesitation — a good question beats a guess.
Do not ask for routine approval; on low-risk work, just proceed.

Keep it short. Unless the user explicitly asks for detail, answer in a few precise sentences, like
a real assistant would. Evidence dumps, repeated command output, step-by-step narration and long
tables are **on request**; they are not volunteered. Say the result, give the reason in one
sentence, stop. Open it up if asked.

**Drip questions, do not batch them.** Even when `questions.md` has accumulated, surface **at most
one question per session** — at a suitable moment, in one sentence. The rest waits in the file and
is never read back as a reminder list. When you do show the user a list, keep the assistant's own
internal chores (the golden set, evals, lint) visually separate from their actual work; otherwise
they read your housekeeping as something they owe you.

## 0.3 Session start (multi-machine sync)

**On every new user request, the first thing you run is:**

```bash
git pull origin main && sh memory/tools/sleep-check.sh
```

Pull, because the user may have pushed from another machine; the local copy stays current. If the
script prints `SLEEP DUE`, run a consolidation (§6) before starting the actual work.

## 0.4 Consistency is a standing duty

When a decision is made, **every trace of it is aligned in the same piece of work.** Reporting that
"the old version is still over there" is not enough: noticing an inconsistency and fixing it are the
same task.

Direction: the **source** is the user's statement or decision; a **derivative** is everything that
follows from it — a README, a tracking table, an index, a script, a rule file, a slide. The
derivative is brought in line with the source, never the other way round.

Limits:

- What propagates automatically is the *decision*. Rewriting content the user wrote in your own
  voice is not covered by this rule (§12 scope guard still applies).
- The memory constitution is not overridden (invariant #10): during a conversation you do not fix
  `domains/`, `people/`, the root or `state.md`. The inconsistency goes to the inbox and is aligned
  at consolidation.
- Irreversible or outward-facing alignment (rewriting history, bulk deletion, publishing) is still
  asked about first.
- Report what you aligned in **one line**. Never silently.

---

## 1. What this is

A markdown-based, two-layer personal memory: **L1** (distilled, small, budgeted) plus **L2** (raw,
append-only, immutable). Writes go through one gate (`memory/inbox/`), distillation happens in one
process (sleep consolidation). North star: `golden-set accuracy / median effective cost per query`,
where cost is measured in **tool-call turns** (~2–2.5k effective tokens per turn).

## 2. Directory map

```
memory/
├── MEMORY.md            # root entry — loaded every session (static, NO facts)
├── state.md             # volatile "right now" context (≤200 tokens)
├── questions.md         # consolidation's questions for the human (cap: 5 items)
├── todo.md              # task list — deliberately minimal; items carry [[id]] links, no due dates (cap: 20 open)
├── rules/
│   ├── format.md        # THE SINGLE SCHEMA AUTHORITY (schemas, enums, budgets, grammar + lint-config)
│   └── consolidation.md # the consolidation task definition
├── inbox/               # append-only logs — THE ONLY WRITE GATE
├── domains/<d>/         # your domains, each with an _index.md
├── people/              # person/organisation entity files + _index.md (alias table)
├── archive/             # L2 raw layer: archive/inbox/ + archive/<domain>/YYYY/
├── secret/              # never enters consolidation or embeddings; humans only
└── tools/               # lint.py, eval.py, sleep-check.sh, golden-set.md
```

## 3. Constitution — 10 invariants (docs/DESIGN.md §9)

1. L2 is append-only and immutable; L1 can always be re-derived from it.
2. Every consolidation is one atomic commit; risky operations get their own commit.
3. The single source of truth for "processed" is file location (`inbox/` → `archive/inbox/`); there is no separate state file.
4. Lint is mechanical, is the only gate, and is identical for humans and models; `rules/format.md` is the single schema authority.
5. There is no deletion; forgetting = moving to `## History` / `archive/` + dropping from the index.
6. The root file holds no facts; volatile context lives in `state.md`.
7. Single-home: a fact has exactly one home, everything else links to it. Ambiguous bare names are a lint error.
8. Budgets are numbers (in characters) and they live in lint.
9. Data leaving the machine is default-deny: local embeddings only, `secret/` excluded, remote allowlist.
10. Only consolidation (and the human) writes to `domains/`, `people/`, the root and `state.md`; interactive work writes only to `inbox/` and `archive/`.

## 4. Read protocol (summary — full version in docs/DESIGN.md §6)

1. If this is a memory task, read `memory/state.md` first (the root is already loaded).
2. Pick a domain from the root table → read that domain's `_index.md` (≤500 tokens) → if the answer
   is in `## Hot` or on an index line, **stop**.
3. Read at most 2 files, using the **full path from the index** (never burn a Glob turn resolving a `[[wiki-link]]`).
4. Miss → domain-scoped `rg -m 20 "<term>"`, trying synonyms and other languages your memory uses.
   A repo-wide search happens only with explicit cross-domain intent.
5. Still a miss → say **"that isn't in my memory"**. Never invent one; abstention beats hallucination.
   Offer the nearest partial match.

## 5. Write protocol (summary — full version in docs/DESIGN.md §5)

- Something worth remembering came up → append it as a `## HH:MM` block to
  `memory/inbox/<YYYY-MM-DD>--<machine>.md`, and **only** there. No classification field; sorting
  is consolidation's job. Read the machine alias from `memory/.machine`.
- Long raw content (a transcript, a document) goes straight into `memory/archive/<domain>/YYYY/`;
  the inbox gets a one- or two-sentence summary plus the path.
- **Never** write to `domains/`, `people/`, `MEMORY.md` or `state.md` during interaction (invariant #10).
- **Being told something is not being given a task.** When the user mentions a piece of work, the
  default is to **capture it, not start it**: append to the inbox, and ask in one sentence if you
  need to. "We'll do X at some point" is information; turning it into a plan or touching code
  requires an explicit request.

## 6. Consolidation (opportunistic trigger; task definition in `rules/consolidation.md`)

**Trigger:** there is no cron job and no scheduled task — the system has to stay portable across
machines and across AI harnesses. Two triggers: (a) the user asks for it; (b) the opportunistic
rule — at session start, if `inbox/` is non-empty and the last consolidation (newest file in
`archive/inbox/`) was more than 24 hours ago, a consolidation happens before the real work.

Flow: pre-flight (clean tree → `pre-sleep` checkpoint commit) → LLM pass (triage → sort → merge →
compress → resolve conflicts → refresh indexes and `state.md`) → `python3 memory/tools/lint.py`
**no commit without green** → processed logs move to `archive/inbox/` → one atomic commit → human
diff review. If it breaks: `git reset --hard pre-sleep`.

Approval gates (proposals land in `questions.md`, they are not applied automatically): merging
entities, adding an alias, any change that drops content without a source, opening or closing a
domain (threshold: ≥5 records on the same theme; at most one proposal per month).

## 7. Tools

- `python3 memory/tools/lint.py` — three rule classes: frontmatter/enum/required fields, link
  targets + alias uniqueness, character budgets. Configured from the `lint-config` block in
  `rules/format.md`.
- `python3 memory/tools/eval.py` — golden-set runner; logs question, answer, turns and tokens to
  `tools/eval-log.csv`.
- `memory/tools/golden-set.md` — the versioned question set; an old question is never removed.
- `sh memory/tools/sleep-check.sh` — the opportunistic consolidation trigger; exit 0 means it is
  due. It reads state from file names and never trusts mtime.

## 8. Naming and formatting (short)

- File and folder names are **ASCII kebab-case**; transliterate non-ASCII characters. ID = the file
  name without its extension, unique across the repo, immutable.
- Time-bound files are `YYYY-MM-DD-slug.md`. Frontmatter keys and controlled values are fixed
  English; body text is in the user's language.
- Fact grammar: `- [YYYY-MM-DD]` point, `- [YYYY-MM-DD→]` ongoing, `- [t1→t2]` only inside
  `## History`, `- [void: YYYY-MM-DD]` for something that was wrong from the start. An update is
  not a correction.
- Index lines carry **full paths**; `[[...]]` is only for human-readable cross-references in file bodies.

## 9. Security

- `secret/` never enters consolidation, is never embedded, and only a human touches it. It is
  **gitignored by default** — see `memory/secret/README.md` before you change that.
- **Remote hygiene.** This repository holds someone's private life. Before every push, check that
  `origin` is the user's own private repository. If `origin` still points at the upstream template,
  or at any repository the user did not set up in `INSTALL.md`, **stop and ask** — never push
  personal memory to a repository the user does not own.
- If the repository is public, personal memory does not go in it. Say so plainly and stop.
- Deleting a secret means deleting it **from the whole git history** — removing a line from a file
  is not enough. The procedure is in `memory/secret/README.md`. A human triggers it; an agent never
  runs it alone (it rewrites history and force-pushes).
- Third-party data (other people's records, students' grades and the like) does not enter the
  corpus; where it must, it is de-identified.

## 10. External sources — read taps

- Definitions and keys live in `memory/secret/sources.md` (gitignored). Special rule: only the
  source-pull step reads that file; consolidation and embedding never do. A key only ever travels
  to its own service's API.
- Flow: at step 0 of a consolidation, whatever changed since the last fetch is pulled and appended
  to the inbox as a summary with a provenance trace (for example "(from calendar)"). No raw dumps.
  **Writing to an external system is never automatic.**
- An optional, self-contained Google (Calendar + Tasks + Gmail) tap ships in
  `memory/tools/integrations/google/`; see its README. It is off unless configured, and it has no
  send capability by construction.

## 11. Capability pool — working in other repositories

- When asked to "do X in repository Y": clone it under `temp/<repo>`, work there, and push the
  change to **that repository's own remote**.
- `temp/` is gitignored, can be deleted at any moment, and is never committed here.
- Before starting, read the target repository's own rules (AGENTS.md / CLAUDE.md / README) and follow them.

## 12. Working practices for larger tasks

For big coding or research tasks, to keep agent autonomy safe and to avoid *overengineering*:

- **Acceptance criteria and scope guard.** When planning a task, write down the file scope you will
  touch and what "done" means. Do not wander outside it. Fix the stated thing; do not invent a new
  architecture along the way.
- **Pragmatism.** Be plain, finish the job. A reviewer pass may improve presentation, safety and
  quality, but it never redesigns the core methodology or the main architecture from scratch.
- **Memory records *why*.** In logs and commit messages, write down why a decision was made rather
  than what was done. The code or text already holds the "what"; memory should hold the reasoning.
- **Loop breaker.** If you hit the same error or blocker twice in a row, stop struggling: break the
  loop and hand it to the user (`questions.md` or a message).
- **Adversarial review.** For genuinely risky changes, brief a sub-agent whose only job is to find
  weak points, security holes and logic errors, and touch the main files only after that pass.
