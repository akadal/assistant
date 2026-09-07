# secret/ — humans only

This folder sits **outside** the memory core (docs/DESIGN.md §8, the binary model):

- Consolidation **never reads** it; it never enters a vector index.
- Lint skips it.
- Distilled files (L1) may link to it, but may not take content from it.
- It is **gitignored by default**. Only this README is tracked.

## What goes here

- Credentials, account notes, recovery codes — anything you would not want in a distilled summary.
- `sources.md` — the definitions and keys for external read taps (see below).
- `.env` copies from your projects.

## `sources.md` — external read taps

The source-pull step at the start of a consolidation is the only thing that reads this file.
Consolidation and embedding never do. A key only ever travels to its own service's API.

```markdown
# sources.md

## google
tap: memory/tools/integrations/google
last_fetch: 2026-03-14

## some-other-service
token: <token>
board_id: <id>
last_fetch: 2026-03-10
```

## Should this folder be in git?

By default, no — and that default is deliberate. Keeping secrets out of git means a leaked clone,
a mistaken push or a repository that later turns public cannot expose them.

If you decide you want them synced across your machines and you have verified your repository is
**private**, remove the `memory/secret/*` lines from `.gitignore`. Understand what you are
accepting: from that moment, every secret you write is in the history of every clone, forever,
unless you rewrite that history.

## Deleting a secret means deleting it from history

Removing a line from a file is **not** deletion — `git show <commit>:<path>` brings it straight
back. Rotation is not deletion either: writing a new key and dropping the old line leaves the old
key in history. If you want an old key to actually die, (a) revoke it at the service **and**
(b) run the cleanup below.

History gets rewritten and a `--force` push is required; clones on your other machines break and
have to be re-cloned. An agent never runs this on its own — you have to ask for it explicitly.

```bash
# 0) Revoke the key at the service first — that is the step that closes the irreversible part
# 1) Take a backup
git clone --mirror . ../memory-backup.git
# 2) Strip the file from all history (pip install git-filter-repo)
git filter-repo --path memory/secret/<file>.md --invert-paths --force
# 3) Re-add the remote (filter-repo drops it) and rewrite history
git remote add origin <your-repo-url>
git push --force origin main
# 4) On your other machines: delete the old clone and clone again
```

To scrub a single key while keeping the file, use `--replace-text <patterns.txt>` instead of `--path`.
