# Upgrading — pulling mechanism improvements

Your repository has two kinds of content, and they never overlap:

| | Owned by | Examples |
|---|---|---|
| **Mechanism** | this project | `AGENTS.md`, `INSTALL.md`, `README.md`, `docs/`, `setup/`, `memory/rules/`, `memory/tools/` |
| **Memory** | you | `memory/MEMORY.md`, `memory/state.md`, `memory/domains/`, `memory/people/`, `memory/inbox/`, `memory/archive/`, `memory/todo.md`, `memory/questions.md`, `memory/secret/` |

Because the split is clean, upgrading is a path-scoped checkout. Nothing you have written is touched.

## One-time setup

```bash
git remote add upstream https://github.com/<owner>/assistant.git
```

## Pulling an update

```bash
git fetch upstream
git diff HEAD upstream/main -- AGENTS.md INSTALL.md docs setup memory/rules memory/tools   # look first
git checkout upstream/main -- AGENTS.md INSTALL.md docs setup memory/rules memory/tools
python3 memory/tools/lint.py
git add -A && git commit -m "chore: pull mechanism updates from upstream" && git push origin main
```

Read the diff before you take it. `memory/rules/format.md` is the schema authority: if a budget or
an enum changed there, your existing files are judged by the new rule the moment you pull it. That
is the intent — but run the linter before you commit, and expect to spend a few minutes compressing
a file or two.

Note that this deliberately does **not** overwrite `README.md`. Once the repository is yours, the
front page is yours as well; pull it by hand if you want the newer text.

## Where a change of yours belongs

If you improved the mechanism — a lint rule, a protocol step, a clearer instruction in `AGENTS.md` —
it belongs upstream, where everyone gets it. See [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

If you changed how *your* memory is organised — your domains, your budgets, your golden set — that
is yours and stays local. Expect a small conflict on the files you have customised whenever you
pull; resolve it in favour of the reasoning, not the diff.

---

## Breaking changes

### 2026-09-15 — `questions.md` lost its item cap and gained a grammar

**What changed.** The five-item cap on `memory/questions.md` is gone, and lint now checks each
item against a grammar instead of counting items. A cap does not shrink a question queue — it
freezes it, and an unasked question that gets dropped never comes back. Trimming compresses in
L1's distilled facts; in a human-facing queue it destroys.

**Why you have to act.** `questions.md` is yours, so an upgrade does not rewrite it — but the new
lint rule will flag every existing line. Rewrite each item as:

```
- [YYYY-MM-DD] <kind> · due YYYY-MM-DD · asked N — **Question?** Status quo: <what happens if unanswered> → memory/<path>
```

`<kind>` is `approval`, `conflict`, or `fact`; `due` and `asked` are optional. While you are at it,
move anything that is a *decision or a task* into `todo.md` — that queue is waiting to be done, not
answered. In the reference deployment three of five queued "questions" turned out to be decisions,
and they had sat in the wrong queue for eleven days.

**What you gain.** `memory/tools/question-pick.py` surfaces one question per session by effective
due date, and consolidation closes overdue ones with an explicit status quo. The queue drains by
itself instead of silently rotting.

### 2026-09-15 — a second commit gate

`memory/tools/sleep-audit.py` now runs alongside `lint.py` before every consolidation commit, and
`sleep-run.sh` invokes it. If you have customised `rules/consolidation.md` or the runner prompt,
add the second gate yourself — an unattended run with no audit is exactly the configuration this
tool exists to prevent.

New lint budgets also apply to the mechanism itself (`router`, `rule`, `tool_index`). If your
`AGENTS.md` is larger than the ceiling, lint will say so; that is the inflation brake working, not
a bug. Move a rule under `memory/rules/` and name it in the routing table.
