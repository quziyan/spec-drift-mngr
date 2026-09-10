"""Reading and writing drift-lock.json, plus the S1-S4 state decision.

The lock file is the machine projection of the markdown; entries must never be added to
or removed from it on their own.
"""
from __future__ import annotations

import json
from pathlib import Path

from ledger import Entry

LEGAL_COMMAND = {
    "S1": "sync",
    "S2": "relink --delete",
    "S3": "relink",
    "S4": "confirm",
}


def load_lock(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_lock(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def classify(entries: dict[str, Entry], lock: dict) -> dict[str, str]:
    """The four states: mutually exclusive and exhaustive, each with exactly one legal command."""
    states: dict[str, str] = {}
    for entry_id in set(entries) | set(lock):
        in_md = entry_id in entries
        in_lock = entry_id in lock
        if in_md and not in_lock:
            states[entry_id] = "S1"
        elif in_lock and not in_md:
            states[entry_id] = "S2"
        elif set(entries[entry_id].anchors) != set(lock[entry_id].get("anchors", {})):
            states[entry_id] = "S3"
        else:
            states[entry_id] = "S4"
    return states
