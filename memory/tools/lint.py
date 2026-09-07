#!/usr/bin/env python3
"""lint.py — mechanical checks for the memory core (docs/DESIGN.md §9.1, §10.3).

Three rule classes:
  1. frontmatter parse + enums + required fields
  2. [[link]] / full-path target existence + alias uniqueness
  3. character budgets

Configuration is read from the `lint-config` yaml block inside memory/rules/format.md —
schema and enforcement cannot drift apart (invariant #4). Dependencies: stdlib only.

Exit code: 0 = green, 1 = red (a consolidation may only commit on green).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MEMORY = Path(__file__).resolve().parent.parent  # memory/
FORMAT_MD = MEMORY / "rules" / "format.md"

# Some Windows consoles default to a legacy codepage and mangle non-ASCII output.
# This repository is multi-machine; tool output is UTF-8 everywhere.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


# --- minimal yaml-block parser (only for the lint-config block and frontmatter) ---

def _scalar(v: str):
    v = v.strip()
    if v in ("null", "~", ""):
        return None
    if v.startswith("["):
        inner = v[1:v.index("]")].strip() if "]" in v else v[1:].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _parse_block(lines: list[str], i: int, indent: int):
    out: dict = {}
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        cur = len(line) - len(line.lstrip())
        if cur < indent:
            break
        key, sep, val = line.strip().partition(":")
        if not sep:
            break
        val = val.strip()
        if val and not val.startswith("#"):  # trailing comments are not values
            out[key] = _scalar(val)
            i += 1
        else:
            # child block: indentation of the next non-empty line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                child_indent = len(lines[j]) - len(lines[j].lstrip())
                if child_indent > cur:
                    out[key], i = _parse_block(lines, j, child_indent)
                    continue
            out[key] = {}
            i += 1
    return out, i


def load_config() -> dict:
    if not FORMAT_MD.exists():
        err(f"schema authority not found: {FORMAT_MD}")
        return {}
    text = FORMAT_MD.read_text(encoding="utf-8")
    m = re.search(r"```yaml\s*\nlint-config:\s*\n(.*?)```", text, re.S)
    if not m:
        err("the lint-config block was not found in rules/format.md")
        return {}
    cfg, _ = _parse_block(m.group(1).splitlines(), 0, 0)
    return cfg


# --- frontmatter ---

FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def parse_frontmatter(path: Path):
    """Returns (dict | None, body). If there is no frontmatter: (None, full text)."""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return None, text
    fm, _ = _parse_block(m.group(1).splitlines(), 0, 0)
    return fm, text[m.end():]


def rel(path: Path) -> str:
    # POSIX separators are mandatory: index and table lines are written as "memory/...",
    # and a raw str() on Windows yields backslashes that silently miss every path match.
    return path.relative_to(MEMORY.parent).as_posix()


def classify(path: Path) -> str | None:
    """File kind from its path: root | state | questions | todo | index | topic |
    entity | log | archive | None (not checked)."""
    r = rel(path)
    if r == "memory/MEMORY.md":
        return "root"
    if r == "memory/state.md":
        return "state"
    if r == "memory/questions.md":
        return "questions"
    if r == "memory/todo.md":
        return "todo"
    parts = path.relative_to(MEMORY).parts
    if parts[0] == "domains":
        return "index" if path.name == "_index.md" else "topic"
    if parts[0] == "people":
        return "index" if path.name == "_index.md" else "entity"
    if parts[0] == "inbox":
        return "log"
    if parts[0] == "archive":
        return "archive"
    return None  # rules/, tools/, setup/ → not checked


def expected_id(path: Path) -> str:
    """Expected ID. In sub-foldered files ID = <folder>-<file name> (rules/format.md):
    domains/learning/databases/week03.md -> databases-week03. Reason: names such as
    'week03' or 'overview' repeat across subjects; a bare file name breaks uniqueness."""
    parts = path.relative_to(MEMORY).parts
    if parts[0] == "domains" and len(parts) == 4:
        return f"{parts[2]}-{path.stem}"
    return path.stem


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WIKILINK_RE = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]")
FULLPATH_RE = re.compile(r"memory/[\w\-./]+\.md")

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def linkable_text(text: str) -> str:
    """Strip HTML comments and code spans before link checking.

    A [[link]] or a path inside a code span, a fenced block or an HTML comment is
    documentation *about* the syntax, not a pointer to be resolved. Without this, a file
    that explains the link grammar -- every template ships one -- fails lint on day one,
    and the only way to make it pass is to stop documenting the grammar."""
    text = HTML_COMMENT_RE.sub("", text)
    text = CODE_FENCE_RE.sub("", text)
    return INLINE_CODE_RE.sub("", text)


def main() -> int:
    cfg = load_config()
    if not cfg:
        report()
        return 1

    enums = cfg.get("enums", {}) or {}
    budgets = cfg.get("budgets_chars", {}) or {}
    required = cfg.get("required", {}) or {}
    questions_cap = budgets.get("questions_item_cap", 5)
    todo_cap = budgets.get("todo_open_item_cap", 20)

    md_files = sorted(MEMORY.rglob("*.md"))
    md_files = [p for p in md_files if ".index" not in p.parts and "secret" not in p.parts]

    # id → file map (for link targets and the id == file-name check)
    all_ids = {expected_id(p) for p in md_files}
    aliases_seen: dict[str, str] = {}

    for path in md_files:
        kind = classify(path)
        if kind is None:
            continue
        r = rel(path)
        text = path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(path)

        # --- Rule 1: frontmatter / enums / required fields ---
        if kind in ("index", "topic", "entity", "log"):
            if fm is None:
                err(f"{r}: no frontmatter (required for type: {kind})")
            else:
                req = list(required.get(kind, []) or [])
                if kind == "index" and path.parent.parent.name == "domains":
                    req += list(required.get("index_domain_extra", []) or [])
                for field in req:
                    if field not in fm or fm[field] in (None, ""):
                        err(f"{r}: missing required field: {field}")
                for field, allowed in enums.items():
                    if field in fm and isinstance(fm[field], str) and fm[field] not in (allowed or []):
                        err(f"{r}: enum violation: {field}={fm[field]!r} (allowed: {allowed})")
                if "type" in fm and fm["type"] != kind and kind != "index":
                    err(f"{r}: type={fm.get('type')!r} but the location says {kind}")
                if "updated" in fm and not DATE_RE.match(str(fm["updated"])):
                    err(f"{r}: 'updated' is not YYYY-MM-DD: {fm['updated']!r}")
                if kind == "log" and "date" in fm and not DATE_RE.match(str(fm["date"])):
                    err(f"{r}: log 'date' is not YYYY-MM-DD: {fm['date']!r}")
                eid = expected_id(path)
                if kind in ("topic", "entity") and fm.get("id") and fm["id"] != eid:
                    err(f"{r}: id={fm['id']!r} does not match the expected ID ({eid})")

        # root/state/questions/todo must not carry frontmatter
        if kind in ("root", "state", "questions", "todo") and fm is not None:
            warn(f"{r}: a {kind} file has frontmatter (not part of its contract)")

        # questions.md item cap
        if kind == "questions":
            items = [ln for ln in body.splitlines() if ln.startswith("- ")]
            if len(items) > questions_cap:
                err(f"{r}: question cap exceeded ({len(items)}/{questions_cap})")

        # todo.md open-item cap
        if kind == "todo":
            open_items = [ln for ln in body.splitlines() if ln.startswith("- [ ]")]
            if len(open_items) > todo_cap:
                warn(f"{r}: open-item cap exceeded ({len(open_items)}/{todo_cap}) — time to prune")

        # --- Rule 2: link targets + alias uniqueness ---
        # archive/ (L2) is exempt: it is immutable (invariant #1) and records the paths that
        # were correct at the time of writing. If a file is legitimately moved, the archive's
        # reference breaks but cannot be repaired -- repairing it would mean writing to L2.
        # Path checking belongs to the L1 routing surface; in the archive a path is history.
        if kind == "archive":
            continue
        routing = linkable_text(text)
        for m in WIKILINK_RE.finditer(routing):
            target = m.group(1).strip()
            if target not in all_ids:
                err(f"{r}: [[{target}]] has no target (no such id/file)")
        for m in FULLPATH_RE.finditer(routing):
            if not (MEMORY.parent / m.group(0)).exists():
                err(f"{r}: full-path target does not exist: {m.group(0)}")

        if kind == "entity" and fm:
            for a in fm.get("aliases", []) or []:
                a = str(a)
                if a in aliases_seen:
                    err(f"{r}: alias collision: {a!r} also appears in {aliases_seen[a]}")
                else:
                    aliases_seen[a] = r

        # --- Rule 3: character budgets ---
        bkey = {"root": "root", "state": "state", "index": "index",
                "topic": "topic", "entity": "entity"}.get(kind)
        if bkey and bkey in budgets and budgets[bkey]:
            target_n, ceiling = budgets[bkey]
            n = len(text)
            if ceiling and n > ceiling:
                err(f"{r}: over budget ceiling ({n} chars > {ceiling})")
            elif target_n and n > target_n:
                warn(f"{r}: over target budget ({n} chars > {target_n}) — compress at consolidation")

    report()
    return 1 if errors else 0


def report() -> None:
    for w in warnings:
        print(f"WARN   {w}")
    for e in errors:
        print(f"ERROR  {e}")
    if not errors and not warnings:
        print("lint: green — no errors, no warnings")
    elif not errors:
        print(f"lint: green — {len(warnings)} warning(s)")
    else:
        print(f"lint: red — {len(errors)} error(s), {len(warnings)} warning(s)")


if __name__ == "__main__":
    sys.exit(main())
