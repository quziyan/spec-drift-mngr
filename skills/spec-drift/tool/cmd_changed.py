"""changed: the set of symbols actually changed, over the non-merge branch and the merge branch.

`merge_symbols_for` is the core of the two-parent rule for merges and deliberately
carries no underscore prefix — validation 3 in gitutil.py's `validate_base` reuses it
to decide whether a given merge commit "changed a .py". gitutil reaches it through a
deferred import inside the function body, so the two modules do not block each other
against this module's top-level `import gitutil`.
"""
from __future__ import annotations

import gitutil
import symbols as S


class ParseFailed(Exception):
    """ast.parse or decoding failed on one of the two revisions. Fail closed, naming the commit and the file."""


def _split_full_path(full_path: str, roots_rel: list[str]) -> tuple[str, str]:
    """Split on the code_root_rel prefix into (the owning code_root_rel, the relpath relative to that root).

    The multi-value validation in `repo.build_ctx` already guarantees that the
    configured code_roots do not nest, so full_path matches at most one prefix and
    there is no ambiguity. In the single-value case roots_rel holds one item and the
    result is byte-for-byte what `full_path[len(code_root_rel) + 1:]` gave before
    multi-root support was added.
    """
    for root_rel in roots_rel:
        prefix = root_rel + "/"
        if full_path.startswith(prefix):
            return root_rel, full_path[len(prefix):]
    raise ValueError(f"{full_path!r} does not belong to any configured code_root ({roots_rel})")


def _symbol_map_at(repo_root, commit, relpath, code_root_rel):
    """-> the symbol fingerprint table of this file at revision commit; None if the file does not exist there.

    A missing file is not a parse failure; a syntax or decoding failure raises
    ParseFailed (naming the commit and the relpath). The merge branch reuses this
    function directly to read the symbol tables of a merge's parents and of the merge
    result.
    """
    try:
        src = gitutil.file_at(repo_root, commit, f"{code_root_rel}/{relpath}")
    except UnicodeDecodeError as exc:
        raise ParseFailed(f"{commit} {relpath}: {exc}") from exc
    if src is None:
        return None
    try:
        return S.file_symbol_map(src, filename=relpath)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ParseFailed(f"{commit} {relpath}: {exc}") from exc


def _diff_one_file(repo_root, parent, commit, relpath, code_root_rel):
    """-> the set of symbol names from this file that enter the set at this step (without the path prefix)."""
    fp_before = _symbol_map_at(repo_root, parent, relpath, code_root_rel)
    fp_after = _symbol_map_at(repo_root, commit, relpath, code_root_rel)
    if fp_before is None and fp_after is None:
        return set()

    keys_before = set(fp_before or {})
    keys_after = set(fp_after or {})
    hit = keys_before ^ keys_after                       # present in only one of the two revisions
    for key in keys_before & keys_after:
        if fp_before[key] != fp_after[key]:              # different fingerprint
            hit.add(key)

    # Positional comparison of the shared symbols: everything whose position differs
    # enters the set (over-report rather than miss)
    if fp_before is not None and fp_after is not None:
        src_before = gitutil.file_at(repo_root, parent, f"{code_root_rel}/{relpath}")
        src_after = gitutil.file_at(repo_root, commit, f"{code_root_rel}/{relpath}")
        common = (keys_before & keys_after) - {S.MODULE_KEY}
        seq_before = [n for n in S.file_symbol_order(src_before) if n in common]
        seq_after = [n for n in S.file_symbol_order(src_after) if n in common]
        for i, name in enumerate(seq_before):
            if i >= len(seq_after) or seq_after[i] != name:
                hit.add(name)
        for i, name in enumerate(seq_after):
            if i >= len(seq_before) or seq_before[i] != name:
                hit.add(name)
    return hit


def nonmerge_symbols(repo_root, base, code_root_rel) -> set[str]:
    """The non-merge branch: every non-merge commit on the first-parent chain, comparing the symbols of its two revisions commit by commit, and taking the union.

    code_root_rel accepts a single string or a list of strings (a multi-value
    code_root); with several values every changed file is located in the code_root it
    actually belongs to, while symbol names still use the relpath relative to that
    root (no root prefix), the same naming as in the single-value case.
    """
    roots_rel = gitutil.pathspecs(code_root_rel)
    actual: set[str] = set()
    for commit in gitutil.commits_no_merges(repo_root, base):
        parent = f"{commit}^"
        for full_path in gitutil.changed_py_files(repo_root, parent, commit, code_root_rel):
            root_rel, relpath = _split_full_path(full_path, roots_rel)
            for name in _diff_one_file(repo_root, parent, commit, relpath, root_rel):
                actual.add(f"{relpath}::{name}")
    return actual


def merge_symbols_for(repo_root, merge, code_root_rel) -> set[str]:
    """The result of the two-parent rule for the single merge commit `merge` (symbol names, with the relpath prefix).

    Scan domain: only the union of the diffs between each parent and the merge, never
    a full scan of code_root — if a file is identical between the merge and one of its
    parents, every symbol in it necessarily has the same fingerprint as in that parent,
    neither branch of the rule can hit, and scanning it in full is lossless waste.

    code_root_rel accepts a single string or a list of strings (a multi-value
    code_root), with the same meaning as in `nonmerge_symbols`: every changed file is
    read from the code_root it actually belongs to.
    """
    roots_rel = gitutil.pathspecs(code_root_rel)
    result: set[str] = set()
    parents = gitutil.parents(repo_root, merge)
    files: set[tuple[str, str]] = set()          # (the owning code_root_rel, relpath)
    for parent in parents:
        for full_path in gitutil.changed_py_files(repo_root, parent, merge, code_root_rel):
            files.add(_split_full_path(full_path, roots_rel))

    for root_rel, relpath in sorted(files):
        in_merge = _symbol_map_at(repo_root, merge, relpath, root_rel)
        per_parent = [
            _symbol_map_at(repo_root, p, relpath, root_rel) for p in parents
        ]

        # First branch (introduced on M's side): M has it, and there is no parent that
        # both has it and has the same fingerprint as M.
        for key, fp in (in_merge or {}).items():
            if not any(pm is not None and pm.get(key) == fp for pm in per_parent):
                result.add(f"{relpath}::{key}")

        # Second branch (deleted on M's side): every parent has it and M does not.
        if per_parent and all(pm is not None for pm in per_parent):
            common = set.intersection(*(set(pm) for pm in per_parent))
            for key in common - set(in_merge or {}):
                result.add(f"{relpath}::{key}")
    return result


def merge_symbols(repo_root, base, code_root_rel) -> set[str]:
    """The enumeration domain is limited to the merges on the first-parent chain
    (`gitutil.merge_commits`); the two-parent rule is applied to each merge and the
    results are unioned."""
    result: set[str] = set()
    for merge in gitutil.merge_commits(repo_root, base):
        result |= merge_symbols_for(repo_root, merge, code_root_rel)
    return result


def run(ctx, predict_relpath: str) -> int:
    """Entry point of `changed`: find base, run the five self-checks, then collect the non-merge and merge symbol sets."""
    repo_root = ctx.repo_root
    code_roots_rel = [str(root.relative_to(repo_root)) for root in ctx.code_roots]
    try:
        m = gitutil.mainline(repo_root)
        gitutil.fetch_origin(repo_root, m)
        base, find_warnings = gitutil.find_base(repo_root, predict_relpath)
        for w in find_warnings:
            print(w)
        # The whole reconciliation stands on "base was chosen correctly" and "the mainline
        # is the right branch"; both were the only invisible links in the chain, so they
        # are printed before the self-checks (a failing self-check then still shows them).
        mainline_sha = gitutil.git(repo_root, "rev-parse", m.full_ref).strip()
        print(f"base: {base} (the commit that added {predict_relpath})")
        print(f"mainline: origin/{m.name} @ {mainline_sha}")
        gitutil.run_self_checks(repo_root, base, code_roots_rel, m)
        for w in gitutil.validate_base(repo_root, base, code_roots_rel, m):
            print(w)
        actual = nonmerge_symbols(repo_root, base, code_roots_rel)
        actual |= merge_symbols(repo_root, base, code_roots_rel)
    except (gitutil.SelfCheckError, ParseFailed) as exc:
        print(f"❌ {exc}")
        return 1

    print(f"\nActual changed symbol set ({len(actual)} symbols):")
    for name in sorted(actual):
        print(f"  - {name}")
    return 0
