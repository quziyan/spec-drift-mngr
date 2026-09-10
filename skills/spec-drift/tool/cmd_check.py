"""check: the single outlet for drift alarms.

Exit code: any of ①–④ non-empty → non-zero; ⑤ (duplicate symbol names) is a warning only.

A missing ledger file, or a ledger that parses to 0 entries, must both fail loudly with a
non-zero exit. Falling back to "all five categories 0, exit 0" would be indistinguishable
from a genuinely clean ledger. 0 entries usually means the entry headings do not match
`### <ID> <title>` (that is the only format error the parser skips silently; missing
labels, malformed anchor lines and the like raise LedgerError instead), or that a new
project simply has no assertions yet. Either way a human must look.
"""
from __future__ import annotations

import ledger as L
import lockfile as LK
import repo


def run(ctx: repo.Ctx) -> int:
    try:
        md = ctx.ledger_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"\n== ledger missing == 1")
        print(
            f"  - the ledger file does not exist: {ctx.ledger_path}"
            " (no ledger yet: write a minimal ledger following reference/ledger-format.md,"
            " then run check again)"
        )
        return 1

    entries = L.parse_ledger(md, ctx.labels)
    if not entries:
        print(f"\n== ledger empty == 1")
        print(
            f"  - {ctx.ledger_path} parsed 0 entries: either the ledger has no assertions "
            "yet, or no heading matches `### <ID> <title>` (that is the only format error "
            "that is skipped silently; anything else raises). Check against "
            "reference/ledger-format.md."
        )
        return 1

    lock = LK.load_lock(ctx.lock_path)
    states = LK.classify(entries, lock)

    bad_state: list[str] = []
    unresolvable: list[str] = []
    vanished: list[str] = []
    drifted: list[str] = []
    warnings: list[str] = []

    # ① judge each entry's state; anything other than S4 is an alarm
    for entry_id in sorted(states):
        if states[entry_id] != "S4":
            state = states[entry_id]
            bad_state.append(f"{entry_id}: {state} → run `{LK.LEGAL_COMMAND[state]}`")

    # ② anchors in the markdown that do not resolve
    for entry_id, entry in sorted(entries.items()):
        for anchor in entry.anchors:
            if repo.current_fingerprint(ctx, anchor) is None:
                unresolvable.append(f"{entry_id}: {anchor}")

    # ③ anchors that vanished from the code but are still in the lock (shown apart from ②:
    #    once a symbol is renamed, deleted or moved away there is no fingerprint left to
    #    compare, and it usually means the rule was refactored out — the highest-risk case,
    #    which would be drowned if mixed into ②)
    for entry_id, record in sorted(lock.items()):
        for anchor in sorted(record.get("anchors", {})):
            if repo.current_fingerprint(ctx, anchor) is None:
                vanished.append(f"{entry_id}: {anchor}")

    # ④ for S4 entries, compare assertion_sha and every anchor fingerprint
    for entry_id, entry in sorted(entries.items()):
        if states.get(entry_id) != "S4":
            continue
        record = lock[entry_id]
        if L.assertion_sha(entry) != record.get("assertion_sha"):
            drifted.append(f"{entry_id}: assertion text changed (assertion_sha mismatch)")
        for anchor in entry.anchors:
            now = repo.current_fingerprint(ctx, anchor)
            if now is None:
                continue                      # already reported by ②/③
            if now != record.get("anchors", {}).get(anchor):
                drifted.append(f"{entry_id}: fingerprint drift {anchor}")

    # ⑤ symbol defined more than once (a warning; does not affect the exit code)
    all_anchors = [a for e in entries.values() for a in e.anchors]
    warnings = repo.duplicate_names(ctx, all_anchors)

    def dump(title: str, rows: list[str]) -> None:
        print(f"\n== {title} == {len(rows)}")
        for row in rows:
            print(f"  - {row}")

    dump("① entries not in S4", bad_state)
    dump("② ledger anchors that do not resolve", unresolvable)
    dump("③ lock anchors that vanished", vanished)
    dump("④ drifted (assertion text or code changed)", drifted)
    dump("⑤ warning: symbol defined more than once (does not affect exit code)", warnings)

    return 1 if (bad_state or unresolvable or vanished or drifted) else 0
