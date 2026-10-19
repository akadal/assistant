# delegation.md — handing bulk work to another model

Read this before delegating work to a model other than the one running the session.
Tool: `memory/tools/delegate.py`. Configuration: `memory/delegate.ini` (copy the `.example`).

## What this is for

Some work is large and dull: screening a hundred search results, reading a mailbox, scanning a
codebase for one pattern, summarising a pile of documents. Doing it in the main session spends the
context window on material you will never refer to again. An external agent CLI reads it in **its**
context and hands back the short answer, and it is billed to whatever subscription you already pay
for rather than to the session you are in.

What it is not for: anything needing this repository's rules, the owner's voice, or a memory write.
Those stay in the main session.

**Leave a one-line trace of every delegation**: what was handed over, to which engine, and
whether it helped. The tool writes its output under `memory/tools/.state/`, which is gitignored
and therefore invisible from your other machines. Without a trace in the memory itself, the
question "is this capability actually being used?" has no answer later, and a capability nobody
can see is one nobody maintains.

## Why a CLI and not MCP

MCP would bind this repository to a single harness. The design is explicitly multi-harness and
multi-AI (`AGENTS.md` section 7), so the bridge is a plain subprocess call: `sh` plus the standard
library, identical on every machine, usable from any agent that can run a command.

## Roles are configuration, not code

Two roles, both strings you set:

| Role | Meaning |
|---|---|
| `chain` | external engines to try, in order; the first that answers wins |
| `backup` | who takes the work when the chain is exhausted |

Resolution order: `ASSISTANT_DELEGATE_CHAIN` / `ASSISTANT_DELEGATE_BACKUP` in the environment, then
`memory/delegate.ini`, then the built-in defaults. Engines themselves are defined the same way, as
`[engine:<name>]` sections giving a command, an argument template, and a model per tier.

**No rule anywhere names a vendor**, and that is deliberate. Today your main session might be one
model with another doing the bulk work; tomorrow you may invert them, or run a local model for the
bulk and a hosted one for the session. Change the two strings and nothing else moves.

`backup` is a **harness-side** actor, usually a sub-agent on a model your harness can start. The
tool therefore cannot call it: it exits 3 and names it, and the agent reading that message is
expected to hand the work over.

## Two tiers, and why not the cheap model

`grunt` for scanning, listing and summarising; `advice` for reasoning. Set a capable model for
`grunt` as well. On a flat subscription the cheapest model is a false economy: a half-good answer
costs the main session a verification pass, which is exactly the saving you were chasing.

## Do not stall

The tool walks the chain itself. Exit codes carry the contract:

| Exit | Meaning | What to do |
|---|---|---|
| 0 | an engine answered | use it, after verifying |
| 3 | every engine failed on quota, sign-in or install | hand the same work to `backup` |
| 1 | the **work** failed, not the engine | the chain is not tried; fix the request |
| 124 | timed out | another engine would time out too; split the work |

The difference between 3 and 1 is the whole point. An engine that is out of quota should cost you
nothing but a retry elsewhere; a badly framed request should not be fired at three engines in turn,
burning all of them on the same failure.

## Limits

- **The repository root is never opened to an external agent** (invariant 9). The tool refuses it.
  Use `--path` for a separate clone, or `--give` to stage only the files the task needs.
- **`secret/` never leaves**, by either route, and this is enforced in code rather than trusted.
- **Whatever comes back is a hypothesis.** It was produced by a model that cannot see your rules
  and has no stake in being right here. Verify before acting; a confident wrong answer and a
  correct one arrive in the same format.
- **Anything you send goes to that engine's vendor.** Paths that look like third-party data raise a
  warning, but the decision is the owner's, not the tool's. If your memory holds other people's
  data, decide this before you delegate, not after.

## Setup

```sh
cp memory/delegate.ini.example memory/delegate.ini
# edit [roles] and the [engine:*] sections, then:
python memory/tools/delegate.py --give memory/domains/work "which items are still open?"
```

`memory/delegate.ini` is gitignored, so your choice of models stays yours and template updates
never conflict with it.
