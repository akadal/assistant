# Capability index — `memory/tools/`

The single answer to "what do I have?". `AGENTS.md` points here; **tool detail is not repeated
there** (invariant #7, one home per fact). Each tool's rationale and usage live in its own
docstring — this file carries only *what it does* and its **trigger** (when to run it).

Lint checks both directions: every `.py`/`.sh` under `memory/tools/` must appear here, and every
path here must exist. A tool without a trigger dies silently — that is why this file exists.

## Memory core

- `memory/tools/lint.py` — schema, link targets, alias uniqueness, character budgets; also checks
  the rule files themselves (router/rule) and catches orphan rules and orphan tools.
  **Trigger:** before every consolidation commit; whenever a memory file is edited by hand.
- `memory/tools/sleep-audit.py` — mechanical quality audit of the consolidation diff: fabrication,
  loss, bloat, ratchet, L2 integrity. **Trigger:** during consolidation, after lint and before the
  commit (the second gate); `--last` to audit a past sleep commit.
- `memory/tools/sleep-check.sh` — sleep trigger; exit 0 means a run is due. Says "NO SLEEP" while
  a fresh lock exists. `--nightly`: skips the once-a-day test, so the scheduled run is
  unconditional (AGENTS.md §6c). **Trigger:** at the start of every session; `--nightly` from
  `sleep-run.sh`.
- `memory/tools/sleep-run.sh` — scheduled, unattended sleep runner: pull → due? → lock → harness →
  release. It does no distilling itself. **Trigger:** a scheduler on **one** machine only.
- `memory/tools/question-pick.py` — picks the question of the day by effective due date;
  `--asked` bumps the counter. **Trigger:** session start; immediately after asking (`--asked`).
- `memory/tools/eval.py` — golden-set runner; logs accuracy, turns and tokens to `eval-log.csv`.
  `kayit`/`record` subcommand logs non-interactively. **Trigger:** whenever the north-star metric
  is measured — after a schema change or a change in distillation behaviour.
- `memory/tools/golden-set.md` — the versioned question set; an old question is never removed.

## Integrations

- `memory/tools/secret-put.py` — the owner types a key into their own terminal; it lands in
  `secret/<name>.json`. **Trigger:** every time a token or key is needed from the owner.

- `memory/tools/integrations/google/` — optional, read-first Google connectors (calendar, tasks,
  mail, drive). **Trigger:** only when the owner has configured credentials; see the directory's
  own README. Writing outward is never automatic.
