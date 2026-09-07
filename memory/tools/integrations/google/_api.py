"""_api.py — shared Google API helper (stdlib only).

Refreshes a refresh_token into an access_token and makes plain JSON calls.
Credentials live under memory/secret/ and are never written back out of it.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Some Windows consoles default to a legacy codepage and blow up with
# UnicodeEncodeError on non-ASCII output. This repository is multi-machine;
# output is UTF-8 everywhere.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

MEMORY = Path(__file__).resolve().parents[3]     # memory/
SECRET = MEMORY / "secret"
CLIENT = SECRET / "google-oauth-client.json"
TOKEN = SECRET / "google-token.json"


def _creds():
    if not TOKEN.exists():
        sys.exit(f"ERROR: {TOKEN} not found. Run auth.py first.")
    c = json.loads(CLIENT.read_text(encoding="utf-8"))
    c = c.get("installed") or c.get("web")
    t = json.loads(TOKEN.read_text(encoding="utf-8"))
    return c["client_id"], c["client_secret"], t


def access_token():
    cid, csec, t = _creds()
    data = urllib.parse.urlencode({
        "client_id": cid, "client_secret": csec,
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=data)) as r:
        return json.loads(r.read())["access_token"]


def api(url, token, method="GET", body=None, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def error_message(e):
    """Pull Google's own message out of an HTTPError body. A 403 can mean two very
    different things — a missing scope, or an API that is not enabled on the project —
    and the fixes differ, so show Google's sentence instead of guessing the cause."""
    try:
        return json.loads(e.read()).get("error", {}).get("message", "")[:300]
    except Exception:
        return ""


def state_get(key, default=None):
    return json.loads(TOKEN.read_text(encoding="utf-8")).get(key, default)


def state_set(key, value):
    t = json.loads(TOKEN.read_text(encoding="utf-8"))
    t[key] = value
    TOKEN.write_text(json.dumps(t, indent=2), encoding="utf-8")
