"""uncovered: symbols in the hot zone that no ledger entry covers. The hot zone is configurable.

Known boundary: it only answers "is this symbol anchored by some entry", and cannot answer
"among the symbols that are anchored, is there a rule that no entry asserts yet". The
latter is closed once, when the ledger is first built, by the rule-level inventory (the
`inventory` command), and kept closed at run time by the D class of the finishing ritual
("a new rule has appeared in the code").

By default the hot zone is derived from the ledger anchors (nothing else about the
behaviour changed when configured inclusion became possible); `.spec-drift.json` may carry
an optional `hot_zone` field (a list of paths, each relative to the code_root it belongs
to, files or directories alike, a directory contributing every .py below it), which is
unioned with the anchor-derived set — with the field unset the behaviour is byte-for-byte
what it was before the hot zone became configurable.
"""
from __future__ import annotations

import ledger as L
import repo
import symbols as S


def _anchor_derived_files(ctx) -> set[str]:
    """Derive the hot-zone files from the current ledger anchors, excluding files under any `tests` directory."""
    entries = L.parse_ledger(ctx.ledger_path.read_text(encoding="utf-8"), ctx.labels)
    files: set[str] = set()
    for entry in entries.values():
        for anchor in entry.anchors:
            relpath, _name = repo.split_anchor(anchor)
            if repo.is_test_path(relpath):
                continue
            files.add(relpath)
    return files


def _configured_hot_zone_files(ctx) -> set[str]:
    """Resolve the optional hot_zone field of .spec-drift.json into a set of relative file paths (any `tests` directory already excluded).

    Every item is relative to one code_root (with a multi-value code_root each item is
    looked up under all of them to find its owner):
    - present under 0 code roots → the config is wrong; print a warning and skip it (do not
      abort the whole command).
    - present under 1 code root → resolve it there (a file is taken as is, a directory
      contributes every .py below it).
    - present under 2 or more → the owner cannot be determined; fail loudly (never pick one
      silently).
    With the field unset it returns an empty set, which is what keeps the default behaviour
    of hot_zone() unchanged.
    """
    cfg = S.load_config(ctx.repo_root)
    raw = cfg.get("hot_zone")
    if not raw:
        return set()
    if not isinstance(raw, list) or not all(isinstance(e, str) for e in raw):
        raise ValueError(f"{S.CONFIG_FILENAME} hot_zone must be a list of strings, got {raw!r}")

    files: set[str] = set()
    for entry in raw:
        matches = [root for root in ctx.code_roots if (root / entry).exists()]
        if len(matches) > 1:
            raise ValueError(
                f"hot_zone entry {entry!r} exists under more than one code_root "
                f"({', '.join(str(m) for m in matches)}); its owner cannot be determined, "
                "restructure the directories or split that entry up"
            )
        if not matches:
            print(f"⚠ hot_zone entry does not exist, skipped: {entry}")
            continue
        root = matches[0]
        target = root / entry
        if target.is_file():
            if target.suffix != ".py":
                print(f"⚠ hot_zone entry is not a .py file, skipped: {entry}")
                continue
            candidates = [target.relative_to(root).as_posix()]
        else:
            candidates = [path.relative_to(root).as_posix() for path in target.rglob("*.py")]
        kept = [f for f in candidates if not repo.is_test_path(f) and not repo.is_vendor_path(f)]
        if not kept:
            # Say so: an entry that only holds test or vendor files silently adds nothing,
            # and the reader cannot tell "configured but empty" from "configured and used".
            print(f"⚠ hot_zone entry adds no file once tests/ and node_modules/ are excluded: {entry}")
        files.update(kept)
    return files


def hot_zone(ctx) -> list[str]:
    """The hot-zone file list: anchor-derived ∪ configured (the latter optional), any `tests` directory excluded.

    With no hot_zone field in `.spec-drift.json` this is the same as deriving from the
    anchors alone — byte-for-byte what it was before the hot zone became configurable.
    """
    return sorted(_anchor_derived_files(ctx) | _configured_hot_zone_files(ctx))


def run(ctx) -> int:
    anchor_files = _anchor_derived_files(ctx)
    configured_files = _configured_hot_zone_files(ctx)
    show_origin = bool(configured_files)

    entries = L.parse_ledger(ctx.ledger_path.read_text(encoding="utf-8"), ctx.labels)
    anchored = {a for e in entries.values() for a in e.anchors}

    if show_origin:
        print("Hot zone (derived from the ledger anchors, plus the hot_zone field of .spec-drift.json; any `tests/` directory excluded):")
    else:
        print("Hot zone (derived from the ledger anchors; any `tests/` directory excluded):")

    total = 0
    for relpath in sorted(anchor_files | configured_files):
        if show_origin:
            from_anchor = relpath in anchor_files
            from_config = relpath in configured_files
            if from_anchor and from_config:
                origin = "anchor-derived+configured"
            elif from_config:
                origin = "configured"
            else:
                origin = "anchor-derived"
            print(f"  {relpath} (origin: {origin})")
        else:
            print(f"  {relpath}")
        src = repo.read_source(ctx, relpath)
        if src is None:
            print("    ⚠ file does not exist")
            continue
        _top, syms = S.parse_symbols(src, filename=relpath)
        rows = [f"{relpath}::{name}" for name in syms if f"{relpath}::{name}" not in anchored]
        total += len(rows)
        for row in sorted(rows):
            print(f"    - {row}")
    print(f"\n{total} symbols are not anchored by any entry.")
    print('Each must be given one of three verdicts: "anchor added" (an entry now anchors it), '
          '"knowingly not anchored (state the price)" (it carries a rule and is left out on purpose), '
          'or "no business meaning" (changing it changes no state transition and nothing shown outside).')
    return 0
