"""impact: reference sites plus sibling anchors.

Deliberately no AST call graph: at the scale of a repository like this, building and
maintaining one costs far more than the false positives it would remove. If the pilot
shows false positives seriously disturbing the predictions, upgrade then (it is already
on record as a known limit).
"""
from __future__ import annotations

import re
from pathlib import Path

import ledger as L
import repo
import symbols as S

FALSE_POSITIVE_NOTE = (
    "⚠ The reference sites above come from text matching and may contain false positives "
    "(a local variable of the same name, the name inside a string, a mention in a comment); "
    "they need filtering by hand, and every item filtered out needs a line of explanation in "
    "the prediction file for this cycle.\n"
    "⚠ References can be missed the same way: a call made through an alias after "
    "`import ... as alias`, or an indirect reference such as `getattr`, is not caught by "
    "text matching, and a reference missed here shows up as a blind spot in the closing "
    "reconciliation."
)


def _all_py(ctx):
    """Walk every .py file under ctx.code_roots, yielding (relpath, path).

    With a multi-value code_root, `repo.build_ctx` has already checked that no two code
    roots hold .py files sharing one relative path, so merging by relpath here is safe and
    unambiguous; with a single value it degenerates into the original single-directory
    walk, byte-for-byte equivalent (sorting by the relpath string gives the same order as
    sorting the full paths under one common prefix).
    """
    seen: dict[str, Path] = {}
    for root in ctx.code_roots:
        for path in root.rglob("*.py"):
            relpath = str(path.relative_to(root))
            seen[relpath] = path
    for relpath, path in sorted(seen.items()):
        yield relpath, path


def _innermost(spans_by_name: dict[str, list[tuple[int, int]]], lineno: int) -> str | None:
    """When spans overlap, the innermost one wins. Used only to map an impact hit onto a symbol."""
    best: tuple[int, str] | None = None
    for name, spans in spans_by_name.items():
        for start, end in spans:
            if start <= lineno <= end:
                width = end - start
                if best is None or width < best[0]:
                    best = (width, name)
    return best[1] if best else None


def _references(ctx, anchor: str) -> tuple[list[str], list[str]]:
    """→ (reference sites, files excluded wholesale because they failed to parse)."""
    _relpath, name = repo.split_anchor(anchor)
    needle = name.split("::")[-1]          # for a class method Foo::bar, search for bar
    pattern = re.compile(rf"\b{re.escape(needle)}\b")
    hits: set[str] = set()
    skipped: set[str] = set()
    for relpath, path in _all_py(ctx):
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped.add(relpath)
            continue
        if not pattern.search(src):
            continue
        try:
            _top, spans_by_name = S.parse_symbols(src)
        except SyntaxError:
            skipped.add(relpath)
            continue
        for idx, line in enumerate(S.split_lines(src), start=1):
            if not pattern.search(line):
                continue
            owner = _innermost(spans_by_name, idx) or S.MODULE_KEY
            key = f"{relpath}::{owner}"
            if key == anchor:              # the definition site itself is not a reference
                continue
            hits.add(key)
    return sorted(hits), sorted(skipped)


def run(ctx, target: str) -> int:
    entries = L.parse_ledger(ctx.ledger_path.read_text(encoding="utf-8"), ctx.labels)

    if target in entries:
        anchors = list(entries[target].anchors)
        siblings_of = {a: [x for x in anchors if x != a] for a in anchors}
    else:
        anchors = [target]
        # Sibling anchors are always read from the ledger markdown (entries), never from
        # drift-lock.json — the markdown is the sole authority and the lock is only its
        # machine projection; reading the lock strictly would return no siblings at all for
        # an entry that has not been synced yet (S1).
        siblings_of = {}
        for entry_id, entry in entries.items():
            if target in entry.anchors:
                siblings_of.setdefault(target, [])
                siblings_of[target] += [
                    f"{x} ({entry_id})" for x in entry.anchors if x != target
                ]
        _relpath, _name = repo.split_anchor(target)
        if _name != S.MODULE_KEY and repo.current_fingerprint(ctx, target) is None:
            # target is neither an entry ID nor a symbol that resolves: it must not silently
            # produce a result that is very likely empty — that would be read as "confirmed,
            # no references". The search still runs and the exit code is still 0.
            print(
                f"⚠ {target} is neither a ledger entry ID nor a symbol that resolves (it may "
                "be misspelled, or the symbol may have been renamed or deleted); the results "
                "below are indicative only."
            )

    for anchor in anchors:
        print(f"\n=== {anchor} ===")
        _relpath, name = repo.split_anchor(anchor)
        if name == S.MODULE_KEY:
            # <module> is a pseudo-symbol; a text search on its name is empty by
            # construction, which would be read as "confirmed, no references", so say
            # plainly that this kind of query does not apply to it.
            print("\n[reference sites] <module> is a pseudo-symbol; a text-matching reference query does not apply to it.")
        else:
            print("\n[reference sites] text match on the symbol name; the search domain is every .py under code_root (tests/ included)")
            refs, skipped = _references(ctx, anchor)
            for ref in refs:
                print(f"  - {ref}")
            if not refs:
                print("  (none)")
            if skipped:
                # Skipped files must be printed as a summary, never silently — otherwise
                # "this file was excluded wholesale" is impossible to notice, and it causes
                # missed references just the same.
                print("\n[excluded] the following files failed to parse and were excluded from the search domain entirely (the result may be incomplete):")
                for s in skipped:
                    print(f"  - {s}")
            print(f"\n{FALSE_POSITIVE_NOTE}")

        print("\n[sibling anchors] the other symbols anchored by the same ledger entry")
        for sib in siblings_of.get(anchor, []):
            print(f"  - {sib}")
        if not siblings_of.get(anchor):
            print("  (none)")
    return 0
