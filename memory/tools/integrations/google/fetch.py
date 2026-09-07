#!/usr/bin/env python3
"""fetch.py — READ Calendar + Tasks + Gmail; a summary lands in the inbox (AGENTS.md §10).

Runs at step 0 of a consolidation. There are no raw dumps: an event line for the calendar,
due date plus title for tasks, sender plus subject for mail. There is no writing to any
external system here (that lives in write.py, and it asks for approval).

Usage: python3 fetch.py [--days 14] [--stdout]

  --stdout  print instead of appending to the inbox. Use this for a look at the start of a
            session: without it, every session would pile another block into the inbox.
"""
import argparse
import datetime as dt
import socket
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import access_token, api, error_message, state_get, state_set  # noqa: E402

MEMORY = Path(__file__).resolve().parents[3]
TASKS = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"


def calendar(tok, days):
    now = dt.datetime.now(dt.timezone.utc)
    r = api("https://www.googleapis.com/calendar/v3/calendars/primary/events", tok, params={
        "timeMin": now.isoformat().replace("+00:00", "Z"),
        "timeMax": (now + dt.timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": 50,
    })
    out = []
    for e in r.get("items", []):
        s = e.get("start", {})
        when = s.get("dateTime", s.get("date", "?"))[:16].replace("T", " ")
        out.append(f"  - {when} — {e.get('summary', '(untitled)')}")
    return out


def tasks(tok, limit=30):
    """Open Google Tasks. If access is missing the tool does not break; Google's own error
    sentence comes back as a line (the cause may be a scope, or a disabled API)."""
    try:
        r = api(TASKS, tok, params={"showCompleted": "false", "maxResults": limit})
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return [f"  - (could not read Tasks — {error_message(e) or 'permission error'})"]
        raise
    out = []
    for t in r.get("items", []):
        title = (t.get("title") or "").strip()
        if not title:
            continue  # Tasks lists can hold blank rows; noise, keep it out of the summary
        out.append(f"  - {(t.get('due') or '')[:10] or '(no due date)'} — {title}")
    return sorted(out)


def mail(tok, limit=20):
    q = "label:unread category:primary"  # promotions and social tabs are filtered out
    since = state_get("gmail_last_fetch")
    if since:
        q += f" after:{since}"
    listing = api("https://gmail.googleapis.com/gmail/v1/users/me/messages", tok,
                  params={"q": q, "maxResults": limit})
    out = []
    for m in listing.get("messages", []) or []:
        d = api(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}", tok,
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]})
        h = {x["name"]: x["value"] for x in d.get("payload", {}).get("headers", [])}
        frm = h.get("From", "?").split("<")[0].strip().strip('"')[:40]
        out.append(f"  - {frm} — {h.get('Subject', '(no subject)')[:70]}")
    return out


def machine_alias():
    """memory/.machine is local and gitignored. The machine identity cannot live in
    google-token.json, because that file syncs with git."""
    f = MEMORY / ".machine"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return socket.gethostname().split(".")[0].split("-")[0].lower()[:12] or "machine"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--stdout", action="store_true", help="print instead of writing to the inbox")
    a = ap.parse_args()

    tok = access_token()
    events, open_tasks, unread = calendar(tok, a.days), tasks(tok), mail(tok)

    now = dt.datetime.now()
    block = [f"## {now:%H:%M}"]
    block.append(f"Google fetch (from calendar/from tasks/from mail). Next {a.days} days: "
                 f"{len(events)} event(s), {len(open_tasks)} open task(s), {len(unread)} unread mail.")
    if events:
        block += ["", "Calendar (from calendar):"] + events
    if open_tasks:
        block += ["", "Open tasks (from tasks):"] + open_tasks
    if unread:
        block += ["", "Unread mail (from mail):"] + unread
    text = "\n".join(block) + "\n"

    if a.stdout:
        print(text)
        return

    alias = machine_alias()
    p = MEMORY / "inbox" / f"{now:%Y-%m-%d}--{alias}.md"
    if p.exists():
        p.write_text(p.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + text, encoding="utf-8")
    else:
        p.write_text(f"---\ntype: log\ndate: {now:%Y-%m-%d}\nmachine: {alias}\n---\n"
                     f"# {now:%Y-%m-%d} ({alias})\n\n" + text, encoding="utf-8")
    state_set("gmail_last_fetch", f"{now:%Y/%m/%d}")
    print(f"written to inbox: {p}  ({len(events)} event(s), {len(unread)} mail)")


if __name__ == "__main__":
    main()
