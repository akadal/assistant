#!/usr/bin/env python3
"""secret-put.py — the owner types a key into their own terminal; it lands in secret/.

Why: an agent does not write a key that was pasted into chat. With this tool the owner
enters the value, the agent only hands over the command and then uses the file; the
value never enters the chat or the transcript. `getpass` is not used: Windows terminals
swallow pasted text in hidden input (values collapsed to a single character).

  python memory/tools/secret-put.py binance api_key api_secret
  python memory/tools/secret-put.py <name> <field> [<field> ...]

Writes memory/secret/<name>.json. If the file exists, new fields are merged in. Output
shows only field names and lengths — never a value.
"""
import json, sys
from pathlib import Path

SECRET = Path(__file__).resolve().parent.parent / "secret"


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    name, fields = sys.argv[1], sys.argv[2:]
    path = SECRET / f"{name}.json"
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    for f in fields:
        d[f] = input(f"{f}: ").strip()
    path.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(path, "→", ", ".join(f"{f}={len(d[f])} chars" for f in fields))


if __name__ == "__main__":
    main()
