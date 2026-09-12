#!/usr/bin/env python3
"""drive.py — READ Drive: search, list, download (AGENTS.md §10).

Why the API rather than the synced folder: documents live in Drive, and a local Drive
folder is not always readable — on macOS the TCC prompt is per-process, so one session
reads it and the next gets "Operation not permitted". A path through the API works the
same on every machine and under every harness.

Read-only: the `drive.readonly` scope cannot write, and there is no write call here. If
writing to Drive is ever needed, both the scope and the code are opened deliberately.

Paths are given from the "My Drive" root, separated by "/", and names match exactly.

  python3 drive.py --search "week01"
  python3 drive.py --list "Teaching/Courses"
  python3 drive.py --download "Teaching/Courses/X/week01.html" --dest ./week01.html
  python3 drive.py --download <file-id> --dest ./week01.html
"""
import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _api import access_token, api, error_message  # noqa: E402

API = "https://www.googleapis.com/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
FIELDS = "files(id,name,mimeType,modifiedTime,size)"


def _escape(name):
    """Single quotes and backslashes are escaped in the Drive query language."""
    return name.replace("\\", "\\\\").replace("'", "\\'")


def children(token, parent, name=None):
    q = f"'{parent}' in parents and trashed=false"
    if name:
        q += f" and name='{_escape(name)}'"
    return api(API, token, params={"q": q, "fields": FIELDS, "pageSize": 200,
                                   "orderBy": "folder,name"})["files"]


def resolve(token, path):
    """Resolve a path given from the "My Drive" root to a single file or folder record."""
    record, parent = {"id": "root", "name": "My Drive", "mimeType": FOLDER}, "root"
    for part in [p for p in path.strip("/").split("/") if p]:
        found = children(token, parent, part)
        if not found:
            sys.exit(f"ERROR: '{part}' not found (inside: {record['name']}).")
        if len(found) > 1:
            sys.exit(f"ERROR: {len(found)} entries named '{part}'; pick an id with --search.")
        record, parent = found[0], found[0]["id"]
    return record


def print_row(f):
    mark = "/" if f["mimeType"] == FOLDER else " "
    print(f"{f['id']}  {f.get('modifiedTime', '')[:10]}  {f.get('size', ''):>9}  {f['name']}{mark}")


def download(token, dest, record):
    if record["mimeType"].startswith("application/vnd.google-apps"):
        sys.exit(f"ERROR: '{record['name']}' is a native Drive format ({record['mimeType']}); "
                 "this tool only downloads uploaded files.")
    req = urllib.request.Request(f"{API}/{record['id']}?alt=media")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as r:
        data = r.read()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"OK: {dest}  ({len(data)} bytes, Drive: {record['name']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", metavar="TEXT", help="search by a substring of the name")
    ap.add_argument("--list", metavar="PATH", help="list the contents of a folder")
    ap.add_argument("--download", metavar="PATH|ID", help="download a file")
    ap.add_argument("--dest", metavar="PATH", help="local destination for --download")
    a = ap.parse_args()
    if a.search is None and a.list is None and a.download is None:
        ap.error("give one of --search, --list or --download.")
    if a.download is not None and not a.dest:
        ap.error("--download needs --dest.")

    try:
        token = access_token()
        if a.search is not None:
            r = api(API, token, params={
                "q": f"name contains '{_escape(a.search)}' and trashed=false",
                "fields": FIELDS, "pageSize": 50, "orderBy": "modifiedTime desc"})
            for f in r["files"]:
                print_row(f)
            if not r["files"]:
                print("(no match)")
        if a.list is not None:
            record = resolve(token, a.list)
            if record["mimeType"] != FOLDER:
                sys.exit(f"ERROR: '{a.list}' is not a folder.")
            for f in children(token, record["id"]):
                print_row(f)
        if a.download is not None:
            # An argument containing "/" is a path; one without it is a Drive file id.
            record = (resolve(token, a.download) if "/" in a.download
                      else api(f"{API}/{a.download}", token, params={"fields": "id,name,mimeType"}))
            download(token, a.dest, record)
    except urllib.error.HTTPError as e:
        message = error_message(e)
        if e.code in (401, 403) and ("insufficient" in message.lower() or "scope" in message.lower()):
            sys.exit(f"ERROR: no Drive scope ({message}). Fix: python3 auth.py")
        sys.exit(f"ERROR: Drive API {e.code} — {message}")


if __name__ == "__main__":
    main()
