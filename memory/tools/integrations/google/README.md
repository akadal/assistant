# Google integration — optional

A read tap for Calendar, Tasks and Gmail, plus a write path that **cannot send mail**. It is off
until you configure it, and nothing in the memory core depends on it.

Standard library only, like everything else here. It talks to Google's REST APIs directly rather
than going through an MCP server, because this repository has to work from any machine with any
assistant — an MCP server binds you to one harness.

## What it does

| Script | Direction | Notes |
|---|---|---|
| `auth.py` | — | One-time OAuth. A human approves it in a browser. |
| `fetch.py` | read | Upcoming events, open tasks, unread mail → an inbox summary. Runs at step 0 of a consolidation. |
| `write.py` | write | Calendar event, Google Task, or a Gmail **draft**. Nothing happens without `--confirm`. |

`fetch.py` writes summaries, never raw dumps: an event line for the calendar, due date plus title
for tasks, sender plus subject for mail. Everything it captures goes through the inbox gate like
any other input, carrying a provenance trace ("from calendar", "from mail").

## The send guarantee

Google does not offer a "write a draft but never send" scope — `gmail.compose` is allowed to send
too. So the guarantee is not a scope, it is the code: **`write.py` contains no call to
`messages.send` or `drafts.send`**, and none may be added. Sending is left to you, in Gmail.

If you review one file in this directory before trusting it, review that one.

## Setup

1. **Google Cloud Console** → create a project → enable the Calendar API, the Tasks API and the
   Gmail API.
2. **Credentials → OAuth client ID → Desktop app** → download the JSON and save it as
   `memory/secret/google-oauth-client.json`.
3. Authorise once:

   ```bash
   python3 memory/tools/integrations/google/auth.py
   ```

   A browser opens; approve it. The refresh token lands in `memory/secret/google-token.json`.

   If the browser is on another device, or the agent runs in a container, use the two-step
   manual mode: `--manual-start`, then `--manual-finish "<the URL from the address bar>"`.

4. Record the tap in `memory/secret/sources.md` so consolidation knows to run it (the format is in
   `memory/secret/README.md`).

Both credential files live under `memory/secret/`, which is gitignored by default.

## Using it

```bash
# a look at the start of a session — prints, writes nothing
python3 memory/tools/integrations/google/fetch.py --stdout

# step 0 of a consolidation — appends a summary to today's inbox log
python3 memory/tools/integrations/google/fetch.py --days 14

# dry run: shows exactly what it would create
python3 memory/tools/integrations/google/write.py event \
  --title "Dentist" --start 2026-09-20T10:00

# and for real
python3 memory/tools/integrations/google/write.py event \
  --title "Dentist" --start 2026-09-20T10:00 --confirm
```

`--stdout` matters more than it looks: without it, a look at the start of every session would pile
another block into the inbox, and consolidation would keep re-distilling the same calendar.

## Reminders, and why a phone sometimes stays quiet

An event gets a popup reminder 60 minutes ahead by default (`--remind N`, `0` to turn it off).
Popups are scheduled *locally on the device*: if the reminder time passes before the event has
synced to your phone, the notification is never created, and Google will not fire the backlog
afterwards. The tool warns you under ten minutes. When it genuinely matters, add `--email` — email
reminders are server-side and do not care about sync.

Tasks are day-level by design: the Tasks API discards the time component of a due date, and there
is no reminder field at all. If you need to be nudged at a specific minute, create an event.

## Time zones

Pass `--tz Europe/Berlin`, or set `ASSISTANT_TZ`. With neither, the machine's local zone is used
and Google falls back to your calendar's own default.

## Writing your own tap

Copy the shape, not the code. A tap is a stdlib script that reads an external source, writes a
short summary into today's inbox log with a provenance trace, and records where it left off. It
never writes to `domains/` or `people/` — the write gate applies to integrations exactly as it
applies to conversations.
