#!/usr/bin/env python3
"""auth.py — Google OAuth authorisation (ONCE; a human approves it in a browser).

Why not an MCP server: this repository is multi-machine and multi-AI (AGENTS.md §11).
An MCP server is bound to one harness; this script runs on every machine with every AI.

Dependencies: stdlib only. Output: memory/secret/google-token.json (a refresh_token).

Two modes:
  (default) local — a browser opens and the script catches the response on localhost.
      python3 auth.py
  --manual — when the browser is on ANOTHER device (a phone) or the agent runs in a
      container. The redirect goes to localhost and that device shows "page not found";
      the URL in the ADDRESS BAR carries the code, and you paste it back. Two steps:
      python3 auth.py --manual-start
      python3 auth.py --manual-finish "<pasted-url-or-code>"
      The interim state (the PKCE verifier) is kept in a temp directory and deleted in
      step 2; it never enters the repository.

Scopes:
  calendar         → read + write the calendar
  tasks            → read + write Google Tasks (the "Tasks" layer in the calendar)
  gmail.readonly   → read mail
  gmail.compose    → create DRAFTS
    WARNING: Google has no "write a draft but never send" scope; gmail.compose is also
    allowed to send. The guarantee comes from the code in this directory: write.py
    contains NO call to messages.send or drafts.send, and none may be added.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# Some Windows consoles default to a legacy codepage and mangle the dashes and arrows in the
# authorisation instructions, which makes them unreadable (same pattern as _api.py).
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SECRET = Path(__file__).resolve().parents[3] / "secret"
CLIENT = SECRET / "google-oauth-client.json"
TOKEN = SECRET / "google-token.json"
INTERIM = Path(tempfile.gettempdir()) / "assistant-google-auth.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def client():
    if not CLIENT.exists():
        sys.exit(f"ERROR: {CLIENT} not found. "
                 "Cloud Console → Credentials → OAuth client ID (Desktop app).")
    c = json.loads(CLIENT.read_text(encoding="utf-8"))
    c = c.get("installed") or c.get("web")
    return c["client_id"], c["client_secret"]


def pkce():
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    return v, c


def auth_url(cid, redirect, challenge, state):
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
    })


def exchange_and_store(cid, csec, redirect, code, verifier):
    data = urllib.parse.urlencode({
        "code": code, "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=data)) as r:
        tok = json.loads(r.read())
    if "refresh_token" not in tok:
        sys.exit("ERROR: no refresh_token came back. Remove this app's access in your Google "
                 "account settings and try again.")
    existing = json.loads(TOKEN.read_text(encoding="utf-8")) if TOKEN.exists() else {}
    existing.update({"refresh_token": tok["refresh_token"], "scopes": SCOPES})
    TOKEN.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    try:
        os.chmod(TOKEN, 0o600)
    except OSError:
        pass  # Windows filesystems may not support this; the file is gitignored regardless
    print(f"DONE. refresh_token written to {TOKEN}")


def manual_start(cid):
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    redirect = f"http://localhost:{free_port()}"
    INTERIM.write_text(json.dumps({"verifier": verifier, "state": state, "redirect": redirect}),
                       encoding="utf-8")
    try:
        os.chmod(INTERIM, 0o600)
    except OSError:
        pass
    print("1) Open this address IN A BROWSER and approve it:\n")
    print(auth_url(cid, redirect, challenge, state))
    print("\n2) After approving, the browser will say 'page not found' — THAT IS NORMAL.")
    print("   Copy the full URL from the ADDRESS BAR (it contains ?code=...).")
    print("\n3) Then run:  python3 auth.py --manual-finish \"<that URL>\"")


def manual_finish(cid, csec, given):
    if not INTERIM.exists():
        sys.exit("ERROR: no interim state. Run --manual-start first (same machine, same session).")
    interim = json.loads(INTERIM.read_text(encoding="utf-8"))
    q = urllib.parse.parse_qs(urllib.parse.urlparse(given.strip()).query)
    if q.get("error"):
        sys.exit(f"ERROR: Google refused — {q['error'][0]}")
    code = q.get("code", [None])[0] or (given.strip() if "?" not in given else None)
    if not code:
        sys.exit("ERROR: no code in that URL. Pass the FULL address-bar URL in quotes.")
    if q.get("state") and q["state"][0] != interim["state"]:
        sys.exit("ERROR: state mismatch — this URL does not belong to this request. Start over.")
    try:
        exchange_and_store(cid, csec, interim["redirect"], code, interim["verifier"])
    finally:
        INTERIM.unlink(missing_ok=True)


def local(cid, csec):
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    port = free_port()
    redirect = f"http://localhost:{port}"
    url = auth_url(cid, redirect, challenge, state)

    box = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            box.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = "code" in box and box.get("state") == state
            self.wfile.write(("<h2>%s</h2><p>You can go back to the terminal.</p>" %
                              ("Authorisation received." if ok else "Failed.")).encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    print("Open this address in a browser and approve it:\n\n" + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print("Waiting for approval...")
    srv.socket.settimeout(300)
    for _ in range(300):
        if box:
            break
        time.sleep(1)
    if box.get("state") != state or "code" not in box:
        sys.exit("ERROR: authorisation not received (%s). If the browser is on another device, "
                 "use --manual-start." % box.get("error", "timed out"))
    exchange_and_store(cid, csec, redirect, box["code"], verifier)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual-start", action="store_true",
                    help="manual mode step 1: print the authorisation link")
    ap.add_argument("--manual-finish", metavar="URL",
                    help="manual mode step 2: hand back the returned URL or code")
    a = ap.parse_args()
    cid, csec = client()
    if a.manual_start:
        manual_start(cid)
    elif a.manual_finish:
        manual_finish(cid, csec, a.manual_finish)
    else:
        local(cid, csec)


if __name__ == "__main__":
    main()
