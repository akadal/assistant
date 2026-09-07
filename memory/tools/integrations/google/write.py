#!/usr/bin/env python3
"""write.py — creates a calendar event, a task, or a Gmail DRAFT. IT CANNOT SEND.

Design contract (docs/DESIGN.md §13.1): writing to an external system requires explicit
approval, without exception. So nothing is applied without --confirm; a run without it
prints what it would do and exits (a dry run).

THE SEND GUARANTEE: Google has no "write a draft but never send" scope — gmail.compose is
also allowed to send. The guarantee comes from this file: there is NO call to messages.send
or drafts.send anywhere in it, and none may be added. Sending is the human's job.

REMINDERS: an event gets a **popup** reminder 60 minutes ahead by default. Google offers two
reminder methods: `popup` (a phone or desktop notification — this is the one people mean by
"notify me") and `email`. --remind 0 turns the reminder off; --email does not replace the
popup, it adds an email reminder alongside it.

A popup is scheduled LOCALLY on the phone: if the reminder time passes before the event has
synced to the device, the notification is never set up, and Google does not fire the backlog
afterwards. Very short-notice reminders are therefore unreliable, and this tool warns under
ten minutes. Email reminders are server-side and unaffected by sync — use --email when it matters.

Time zone: pass --tz (an IANA name such as Europe/Berlin), or set ASSISTANT_TZ. With neither,
the machine's local time zone is used and Google falls back to the calendar's own default.

Usage:
  python3 write.py event --title "..." --start 2026-09-03T14:00 \
      [--end ...] [--description ...] [--remind 60] [--email] [--tz ...] --confirm
  python3 write.py task --title "..." [--due 2026-09-15] [--description ...] --confirm
  python3 write.py draft --to a@b.com --subject "..." --body "..." --confirm
"""
import argparse
import base64
import datetime as dt
import os
import sys
import urllib.error
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import access_token, api, error_message  # noqa: E402

TASKS = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"


def _zone(name):
    """Return (tzinfo, iana_name_or_None). Falls back to the machine's local zone."""
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name), name
        except Exception:
            sys.exit(f"ERROR: unknown time zone {name!r} (expected an IANA name, e.g. Europe/Berlin)")
    return dt.datetime.now().astimezone().tzinfo, None


def event(a, tok):
    tz, tz_name = _zone(a.tz or os.environ.get("ASSISTANT_TZ"))
    # The Calendar API wants full RFC3339: a secondless "2026-09-03T14:00" returns 400.
    # That is the shape the help text suggests, so it is normalised here.
    try:
        start_dt = dt.datetime.fromisoformat(a.start)
    except ValueError:
        sys.exit(f"ERROR: could not read --start: {a.start!r} (expected 2026-09-03T14:00)")
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz)
    end_dt = dt.datetime.fromisoformat(a.end) if a.end else start_dt + dt.timedelta(hours=1)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=tz)

    overrides = []
    if a.remind > 0:
        overrides.append({"method": "popup", "minutes": a.remind})
        if a.email:
            overrides.append({"method": "email", "minutes": a.remind})

    start_block = {"dateTime": start_dt.isoformat()}
    end_block = {"dateTime": end_dt.isoformat()}
    if tz_name:
        start_block["timeZone"] = tz_name
        end_block["timeZone"] = tz_name

    body = {"summary": a.title, "description": a.description or "",
            "start": start_block, "end": end_block,
            "reminders": {"useDefault": False, "overrides": overrides}}

    how = (f"{a.remind} min before, " + "+".join(o["method"] for o in overrides)) \
        if overrides else "NO reminder"
    print(f"CALENDAR: {start_dt.isoformat()} → {end_dt.isoformat()}  \"{a.title}\"  ({how})")

    if overrides:
        minutes_left = (start_dt - dt.timedelta(minutes=a.remind)
                        - dt.datetime.now(start_dt.tzinfo)).total_seconds() / 60
        if minutes_left < 10:
            print(f"  WARNING: {minutes_left:.0f} min until the reminder. If the phone has not "
                  "synced by then the notification never fires — allow more lead time, or add --email.")
    if not a.confirm:
        return print("dry run — add --confirm to apply")
    try:
        r = api("https://www.googleapis.com/calendar/v3/calendars/primary/events", tok,
                method="POST", body=body)
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR ({e.code}): {error_message(e) or 'could not write to the calendar'}")
    print("created:", r.get("htmlLink", r.get("id")))


def task(a, tok):
    """A Google Tasks item. It shows up in the calendar's "Tasks" layer.

    LIMIT: due dates in the Tasks API are DAY-level — Google discards the time part of `due`,
    and the time can be neither written nor read through the API. If you need a notification at
    a specific minute, use `event`; `task` is for something to be done during a day.
    """
    body = {"title": a.title}
    if a.description:
        body["notes"] = a.description
    if a.due:
        body["due"] = f"{a.due}T00:00:00.000Z"
    print(f"TASK: {a.due or '(no due date)'}  \"{a.title}\"  (due dates are day-level — no time kept)")
    if not a.confirm:
        return print("dry run — add --confirm to apply")
    try:
        r = api(TASKS, tok, method="POST", body=body)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            sys.exit(f"ERROR ({e.code}): {error_message(e) or 'permission error'}\n"
                     "  — if it says 'API has not been used': enable the Tasks API in Cloud Console.\n"
                     "  — if it complains about a scope: re-run auth.py.")
        raise
    print("created, id:", r.get("id"))


def draft(a, tok):
    m = EmailMessage()
    m["To"] = a.to
    m["Subject"] = a.subject
    m.set_content(a.body)
    print(f"DRAFT: → {a.to}  \"{a.subject}\"  ({len(a.body)} characters)")
    print("  NOTE: this only creates a draft; this tool has no send capability.")
    if not a.confirm:
        return print("dry run — add --confirm to apply")
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
    r = api("https://gmail.googleapis.com/gmail/v1/users/me/drafts", tok,
            method="POST", body={"message": {"raw": raw}})
    print("draft created, id:", r.get("id"), "— sending it is your job (the Gmail interface)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    e = sub.add_parser("event")
    e.add_argument("--title", required=True)
    e.add_argument("--start", required=True, help="2026-09-03T14:00")
    e.add_argument("--end")
    e.add_argument("--description")
    e.add_argument("--remind", type=int, default=60,
                   help="minutes before the event to notify (default 60; 0 = no reminder)")
    e.add_argument("--email", action="store_true",
                   help="add an email reminder alongside the popup (server-side; unaffected by phone sync)")
    e.add_argument("--tz", help="IANA time zone, e.g. Europe/Berlin (default: ASSISTANT_TZ, then local)")
    e.add_argument("--confirm", action="store_true")

    t = sub.add_parser("task")
    t.add_argument("--title", required=True)
    t.add_argument("--due", help="2026-09-15 (day-level; no time is kept)")
    t.add_argument("--description")
    t.add_argument("--confirm", action="store_true")

    d = sub.add_parser("draft")
    d.add_argument("--to", required=True)
    d.add_argument("--subject", required=True)
    d.add_argument("--body", required=True)
    d.add_argument("--confirm", action="store_true")

    a = ap.parse_args()
    tok = access_token()
    {"event": event, "task": task, "draft": draft}[a.command](a, tok)


if __name__ == "__main__":
    main()
