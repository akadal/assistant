# Contributing

This project is the *mechanism* — the rules, the schema, the scripts, the design contract. Nobody's
memory content lives here, and none should ever arrive in a pull request.

## Before you open a PR

**Check your diff for your own life.** The most likely mistake in this repository is a real name, a
real project, a real email address or a real URL leaking in through an example. Examples must be
obviously fictional. Run:

```bash
git diff origin/main | grep -nEi '^\+.*([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}|https?://)'
```

and read every line that comes back — an address or a link you did not mean to publish is the one
thing a reviewer cannot catch for you. If your memory repository and this one are on the same
machine, double-check you are in the right directory before you commit.

## The bar for a change

`docs/DESIGN.md` §11 has a YAGNI list — things this project has deliberately said no to: knowledge
graphs, observer daemons, importance-decay functions, automatic NER, due-date tracking, embedding-based
link suggestion, multi-phase consolidation. A proposal on that list is not automatically rejected, but
it has to explain **what changed** since the decision, not just why the feature would be nice.

Good contributions usually look like one of these:

- A lint rule that catches a real failure mode mechanically, where the failure was previously only
  caught by a human noticing.
- A protocol step that removes a tool-call turn without losing accuracy. Cost is measured in turns
  (`docs/DESIGN.md` §6.1); "it reads fewer characters" is not the same thing.
- A clearer instruction in `AGENTS.md` or `INSTALL.md` where an agent reliably does the wrong thing.
  Say which agent and what it did.
- A new integration under `memory/tools/integrations/`, self-contained, stdlib-only, read-only by
  default, with no send capability unless the user asks for it explicitly.

## Constraints that are not up for negotiation

- **Standard library only.** No packages, no lockfile, no build step. Someone has to be able to
  clone this on a machine with nothing but Python and start using it.
- **Harness-agnostic.** No dependency on one vendor's memory feature, MCP server or plugin format.
  The same repository has to work tomorrow from a different machine with a different assistant.
- **The schema authority is one file.** If you change a schema, an enum or a budget, change
  `memory/rules/format.md` — and let `lint.py` read it from there. A rule that is written in two
  places is a rule that will disagree with itself.
- **The ten invariants** at the top of `memory/rules/format.md` are the constitution. A PR that
  breaks one needs to argue against the invariant itself, in `docs/DESIGN.md`, first.

## Testing a change

There is no test suite; the linter *is* the test, and the memory it lints has to be real enough to
be interesting. Set up a scratch memory core in a temporary directory, run setup against it, and
check that `python3 memory/tools/lint.py` is green — then deliberately break the thing your change
is supposed to catch and check that it goes red.

If your change touches the setup interview, run it end to end at least once from an empty
repository. Reading it and believing it works is not the same thing.

## Commit style

Short, imperative subject; the body says **why**, not what. The diff already holds the what.
