"""catalog: the ledger and its signatures, rendered as a catalog of approved definitions.

Read-only, and a view rather than a gate: the exit code is 0 whenever the catalog was
printed, whatever the entries' statuses are. Drift alarms have one outlet, `check`; this
command only shows, per book, what each entry says, who signed it, when, why, and whether
the code still matches.

The status logic re-implements the few comparisons `check` makes (on purpose, so that
`cmd_check.py` stays untouched): S1 is unsigned, S3 is anchors changed, and an S4 entry
is anchor missing, drifted or consistent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import ledger as L
import lockfile as LK
import repo

NO_BOOK = "(no book)"
STATUS_ORDER = ("consistent", "drifted", "anchor missing", "unsigned", "anchors changed")
COLUMNS = ("ID", "Title", "Status", "Signed by", "Signed at", "Note", "Rule", "Anchors")


def _rel(ctx: repo.Ctx, path: Path) -> str:
    """The path relative to the repository root, POSIX; an absolute path outside it is shown as is."""
    try:
        return path.relative_to(ctx.repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _status(ctx: repo.Ctx, entry: L.Entry, state: str, record: dict | None) -> str:
    """The first matching rule wins: unsigned, anchors changed, anchor missing, drifted, consistent."""
    if state == "S1":
        return "unsigned"
    if state == "S3":
        return "anchors changed"
    current = {anchor: repo.current_fingerprint(ctx, anchor) for anchor in entry.anchors}
    if any(fp is None for fp in current.values()):
        return "anchor missing"
    if L.assertion_sha(entry) != record.get("assertion_sha"):
        return "drifted"
    locked = record.get("anchors", {})
    if any(fp != locked.get(anchor) for anchor, fp in current.items()):
        return "drifted"
    return "consistent"


def _rows(ctx: repo.Ctx, md: str) -> tuple[list[dict], list[str]]:
    """-> (one row per ledger entry in ledger order, the sorted IDs present only in the lock)."""
    entries = L.parse_ledger(md, ctx.labels)
    books = L.entry_books(md)
    lock = LK.load_lock(ctx.lock_path)
    states = LK.classify(entries, lock)
    rows = []
    for entry_id, entry in entries.items():
        record = lock.get(entry_id)
        rows.append({
            "id": entry_id,
            "title": entry.title,
            "book": books.get(entry_id, ""),
            "status": _status(ctx, entry, states[entry_id], record),
            "state": states[entry_id],
            "signed_by": record.get("confirmed_by") if record is not None else None,
            "signed_at": record.get("confirmed_at") if record is not None else None,
            "note": record.get("note") if record is not None else None,
            "rule": entry.assertion,
            "boundary": entry.boundary,
            "anchors": list(entry.anchors),
            "last_confirmed": entry.confirmed_date,
        })
    lock_only = sorted(i for i, s in states.items() if s == "S2")
    return rows, lock_only


def _book_order(rows: list[dict]) -> list[str]:
    """Distinct book values, in the order of first appearance in the ledger."""
    seen: list[str] = []
    for row in rows:
        if row["book"] not in seen:
            seen.append(row["book"])
    return seen


def _cell(text) -> str:
    """One table cell: multi-line text joined with a single space, every `|` escaped."""
    if text is None:
        return ""
    joined = " ".join(line.strip() for line in str(text).splitlines() if line.strip())
    return joined.replace("|", "\\|")


def _render_md(ledger_rel: str, rows: list[dict], lock_only: list[str]) -> str:
    counts = {status: 0 for status in STATUS_ORDER}
    for row in rows:
        counts[row["status"]] += 1
    books = _book_order(rows)
    out = [
        f"# Catalog: {ledger_rel}",
        "",
        f"{len(rows)} entries in {len(books)} books: "
        + ", ".join(f"{counts[s]} {s}" for s in STATUS_ORDER),
    ]
    for book in books:
        out += [
            "",
            f"## {book or NO_BOOK}",
            "",
            "| " + " | ".join(COLUMNS) + " |",
            "|" + "---|" * len(COLUMNS),
        ]
        for row in rows:
            if row["book"] != book:
                continue
            anchors = "; ".join(f"`{a}`" for a in row["anchors"])
            cells = [row["id"], row["title"], row["status"], row["signed_by"],
                     row["signed_at"], row["note"], row["rule"], anchors]
            out.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    if lock_only:
        out += ["", "Lock-only entries (S2, removed from the ledger): " + ", ".join(lock_only)]
    return "\n".join(out)


def run(ctx: repo.Ctx, *, book: str | None = None, fmt: str = "md") -> int:
    """A missing ledger raises FileNotFoundError on purpose: the CLI wrapper turns it into exit 2."""
    md = ctx.ledger_path.read_text(encoding="utf-8")
    ledger_rel = _rel(ctx, ctx.ledger_path)
    rows, lock_only = _rows(ctx, md)

    if book is not None:
        all_books = _book_order(rows)
        kept = [b for b in all_books if book in b]
        if not kept:
            names = "; ".join(b or NO_BOOK for b in all_books)
            print(f"❌ no book title contains '{book}' (books: {names})", file=sys.stderr)
            return 2
        rows = [row for row in rows if row["book"] in kept]

    if fmt == "json":
        doc = {"ledger": ledger_rel, "entries": rows, "lock_only": lock_only}
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print(_render_md(ledger_rel, rows, lock_only))
    return 0
