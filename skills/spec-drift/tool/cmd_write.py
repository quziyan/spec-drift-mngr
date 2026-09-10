"""sync / confirm / relink: the three write commands, one per state that needs one."""
from __future__ import annotations

from datetime import datetime

import ledger as L
import lockfile as LK
import repo

REQUIRED_STATE = {"sync": "S1", "confirm": "S4", "relink": "S3", "relink --delete": "S2"}


def _fail(message: str) -> int:
    print(f"Refused: {message}")
    return 1


def run(ctx, command: str, entry_id: str, by: str, note: str, delete: bool, today: str) -> int:
    key = "relink --delete" if (command == "relink" and delete) else command
    required_by = {
        "sync": {ctx.owner},
        "relink": {ctx.owner},
        "confirm": {ctx.owner, ctx.assistant},
    }
    if not by or not note:
        return _fail("--by and --note are both required")
    if by not in required_by[command]:
        return _fail(f"{command} only accepts --by {'/'.join(sorted(required_by[command]))}, got {by}")

    md = ctx.ledger_path.read_text(encoding="utf-8")
    entries = L.parse_ledger(md, ctx.labels)
    lock = LK.load_lock(ctx.lock_path)
    states = LK.classify(entries, lock)

    state = states.get(entry_id)
    if state is None:
        return _fail(f"neither the ledger nor the lock has an entry {entry_id}")
    if state != REQUIRED_STATE[key]:
        return _fail(f"{entry_id} is currently {state}; the legal command in that state is `{LK.LEGAL_COMMAND[state]}`")

    if key == "relink --delete":
        del lock[entry_id]
        LK.save_lock(ctx.lock_path, lock)
        print(f"deleted lock entry {entry_id}")
        return 0

    entry = entries[entry_id]
    # Precondition shared by every write command: all anchors in the markdown must resolve.
    fingerprints: dict[str, str] = {}
    for anchor in entry.anchors:
        fingerprint = repo.current_fingerprint(ctx, anchor)
        if fingerprint is None:
            return _fail(f"an anchor of {entry_id} does not resolve to a symbol: {anchor}")
        fingerprints[anchor] = fingerprint

    lock[entry_id] = {
        "assertion_sha": L.assertion_sha(entry),
        "anchors": fingerprints,
        "confirmed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "confirmed_by": by,
        "note": note,
    }
    LK.save_lock(ctx.lock_path, lock)
    ctx.ledger_path.write_text(L.bump_confirmed_date(md, entry_id, today, ctx.labels), encoding="utf-8")
    print(f"{command} done: {entry_id} ({len(fingerprints)} anchors, last confirmed {today})")
    return 0
