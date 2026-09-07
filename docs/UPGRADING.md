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
