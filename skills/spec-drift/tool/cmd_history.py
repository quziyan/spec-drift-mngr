"""history: every wording and signature one entry has had, from git history (read-only).

Walks the commits that touched the ledger or the lock, oldest first, then the working
tree, and prints a new version each time the entry's snapshot differs from the previous
version printed. The walk uses `--full-history`: git's default history simplification
follows only one parent of a merge whose result equals that parent, so a branch whose
wording (or signature) a merge discarded would never be seen, and "every wording" would
quietly become "every wording on the surviving side". `--date-order` keeps parents
before children; commits from parallel branches interleave by commit date. A snapshot is the entry's rule text, boundary text and anchor set, plus
the lock record's assertion_sha, confirmed_by, confirmed_at and note. The title and the
"last confirmed" date are carried for display but do not make a version on their own:
neither is part of what a signature covers.

Known limits: every revision is parsed with today's labels, so a revision written with
other label wording does not parse and is skipped with a note; and a renamed ledger or
lock path is not followed (git log is limited to the current paths).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import gitutil
import ledger as L
import repo

WORKING_TREE = "working tree"
UNCOMMITTED = "uncommitted"
TEXT_EVENTS = {"entry added", "text changed", "anchors changed"}


class Snapshot(NamedTuple):
    present: bool
    title: str = ""
    assertion: str = ""
    boundary: str = ""
    anchors: tuple[str, ...] = ()
    text_sha: str = ""            # assertion_sha of this snapshot's own text
    sig: tuple | None = None      # the lock record: (assertion_sha, confirmed_by, confirmed_at, note)

    def key(self) -> tuple:
        """Two snapshots with the same key are the same version. An absent entry is just absent."""
        if not self.present:
            return (False,)
        return (True, self.assertion, self.boundary, frozenset(self.anchors), self.sig)


ABSENT = Snapshot(False)


def _rel(ctx: repo.Ctx, path: Path) -> str:
    """The path relative to the repository root, POSIX; an absolute path outside it is shown as is."""
    try:
        return path.relative_to(ctx.repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _one_line(exc: Exception) -> str:
    return " ".join(str(exc).splitlines())


def _lock_from_text(text: str | None) -> dict:
    """A lock that is absent, or is not valid JSON, counts as {}."""
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _snapshot(entry_id: str, md: str | None, lock: dict, labels: L.Labels) -> Snapshot:
    """md None means the ledger does not exist there: the entry is absent. Raises LedgerError."""
    if md is None:
        return ABSENT
    entry = L.parse_ledger(md, labels).get(entry_id)
    if entry is None:
        return ABSENT
    record = lock.get(entry_id)
    sig = None
    if isinstance(record, dict):
        sig = (record.get("assertion_sha"), record.get("confirmed_by"),
               record.get("confirmed_at"), record.get("note"))
    return Snapshot(True, entry.title, entry.assertion, entry.boundary,
                    tuple(entry.anchors), L.assertion_sha(entry), sig)


def _changes(prev: Snapshot, cur: Snapshot) -> list[str]:
    if prev.present and not cur.present:
        return ["entry removed"]
    out = []
    if not prev.present:
        out.append("entry added")
    else:
        if (prev.assertion, prev.boundary) != (cur.assertion, cur.boundary):
            out.append("text changed")
        if set(prev.anchors) != set(cur.anchors):
            out.append("anchors changed")
    if prev.sig != cur.sig:
        out.append("signature changed")
    return out


def _signature(snap: Snapshot) -> str:
    if snap.sig is None:
        return "unsigned"
    sha, by, at, note = snap.sig
    if sha == snap.text_sha:
        return f"signed by {by} at {at}: {note}"
    return "signature is for an earlier text (edited after signing)"


def _quote(text: str) -> list[str]:
    return [("> " + line).rstrip() for line in text.split("\n")]


def _committed_steps(ctx: repo.Ctx, entry_id: str, ledger_rel: str, lock_rel: str,
                     notes: list[str]) -> list[tuple[str, str, Snapshot]]:
    """One (date, short sha, snapshot) per commit that touched the ledger or the lock, oldest first.

    Paths are read as `./<rel>`, relative to the repository root (the directory holding
    .spec-drift.json), so a config that lives in a subdirectory of the git repository
    still reads the right files. Raises gitutil.SelfCheckError when git fails.
    """
    log = gitutil.git(ctx.repo_root, "log", "--full-history", "--date-order",
                      "--format=%H%x09%cI", "--reverse",
                      "--", ledger_rel, lock_rel)
    steps = []
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, _tab, when = line.partition("\t")
        short = sha[:9]
        try:
            lock_text = gitutil.file_at(ctx.repo_root, sha, "./" + lock_rel)
        except UnicodeDecodeError:
            lock_text = None
        try:
            md = gitutil.file_at(ctx.repo_root, sha, "./" + ledger_rel)
            snap = _snapshot(entry_id, md, _lock_from_text(lock_text), ctx.labels)
        except (L.LedgerError, UnicodeDecodeError) as exc:
            notes.append(f"ledger did not parse at {short}: {_one_line(exc)}")
            continue
        steps.append((when[:10], short, snap))
    return steps


def _working_tree_step(ctx: repo.Ctx, entry_id: str, notes: list[str]) -> list[tuple[str, str, Snapshot]]:
    try:
        lock_text = ctx.lock_path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        lock_text = None
    try:
        try:
            md = ctx.ledger_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            md = None
        snap = _snapshot(entry_id, md, _lock_from_text(lock_text), ctx.labels)
    except (L.LedgerError, UnicodeDecodeError) as exc:
        notes.append(f"ledger did not parse at {WORKING_TREE}: {_one_line(exc)}")
        return []
    return [(WORKING_TREE, UNCOMMITTED, snap)]


def run(ctx: repo.Ctx, entry_id: str) -> int:
    ledger_rel = _rel(ctx, ctx.ledger_path)
    lock_rel = _rel(ctx, ctx.lock_path)
    notes: list[str] = []
    try:
        steps = _committed_steps(ctx, entry_id, ledger_rel, lock_rel, notes)
    except gitutil.SelfCheckError as exc:
        print(f"❌ {_one_line(exc)}")
        return 1
    steps += _working_tree_step(ctx, entry_id, notes)

    versions = []
    prev = ABSENT
    for when, short, snap in steps:
        if snap.key() == prev.key():
            continue
        versions.append((when, short, snap, _changes(prev, snap)))
        prev = snap

    if not versions:
        for note in notes:
            print(note)
        print(f"❌ {entry_id} was not found in any committed version of {ledger_rel} nor in the working tree")
        return 1

    title = next(snap.title for _w, _s, snap in reversed(steps) if snap.present)
    out = [
        f"# History: {entry_id} {title}",
        "",
        f"Ledger {ledger_rel} · lock {lock_rel} · {len(versions)} versions",
    ]
    if notes:
        out += [""] + notes
    for k, (when, short, snap, changes) in enumerate(versions, 1):
        out += ["", f"## {k} · {when} · {short} · {', '.join(changes)}"]
        if not snap.present:
            continue
        out += ["", f"Signature: {_signature(snap)}"]
        if k == 1 or TEXT_EVENTS & set(changes):
            out += ["", "Rule:", *_quote(snap.assertion),
                    "", "Boundary:", *_quote(snap.boundary),
                    "", "Anchors: " + "; ".join(f"`{a}`" for a in snap.anchors)]
    print("\n".join(out))
    return 0
