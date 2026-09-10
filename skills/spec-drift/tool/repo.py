"""Context and anchor resolution. Multi-root support added the multi-value `code_root`.

The `code_root` field of `.spec-drift.json` accepts two shapes:
- a string (the original shape): `Ctx.code_root` is that single Path, and behaviour is
  byte-for-byte what it was before multi-root support was added.
- a non-empty list of strings (new): `Ctx.code_root` is a tuple of Paths, and each
  command scans the union of them.
Both shapes are read uniformly through the `Ctx.code_roots` property (always a tuple),
for callers that need to walk every code root; callers that do not need multi-root
awareness can keep reading `Ctx.code_root` directly (in the single-value case it is
still the original type).
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import ledger as L
import symbols as S


class Ctx(NamedTuple):
    repo_root: Path
    code_root: Path | tuple[Path, ...]
    ledger_path: Path
    lock_path: Path
    owner: str
    assistant: str
    labels: L.Labels = L.DEFAULT_LABELS

    @property
    def code_roots(self) -> tuple[Path, ...]:
        """Uniform view: a single-value code_root is wrapped in a one-element tuple, a multi-value one is returned as is."""
        return self.code_root if isinstance(self.code_root, tuple) else (self.code_root,)


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start (cwd by default) looking for .spec-drift.json; that level is the repository root.

    The default must be cwd rather than the directory holding this file — the tool is
    global and lives somewhere other than the repository being checked, so anchoring on
    the wrong place would mistake the tool's own directory for the repository root.

    The upward walk **must not cross a git repository boundary**: it stops as soon as it
    meets `.git` (a directory, or the `.git` file of a worktree) and never climbs into
    the parent directory. Otherwise, in a nested-repository layout (a subdirectory with
    no `.spec-drift.json` of its own, where some outer directory happens to be another
    repository that does carry one), it would silently bind to that outer repository's
    config and reconcile against it — using the wrong owner/ledger/lock without any
    error, which is more dangerous than the error itself.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in [here] + list(here.parents):
        if (candidate / S.CONFIG_FILENAME).exists():
            return candidate
        if (candidate / ".git").exists():
            break
    raise RuntimeError(
        f"repository root not found ({S.CONFIG_FILENAME} not found walking up within "
        "this git repository; parent repositories are never consulted). "
        f"The repository root needs a {S.CONFIG_FILENAME} with fields: "
        f"{', '.join(S.REQUIRED_CONFIG_KEYS)}"
    )


def _validate_multi_code_roots(raw_values: list[str], roots: list[Path]) -> None:
    """The two structural checks on a multi-value code_root: reject on sight, never pick one silently.

    (1) No code_root may be identical to, or an ancestor directory of, another one —
    otherwise the same physical file falls under two pathspec prefixes at once, and both
    git and the relative-path split become ambiguous; which one wins is purely an
    implementation detail and should not be decided for the user behind their back.
    (2) No two code_roots may contain real .py files sharing the same relative path —
    otherwise the symbol name `relpath::name` has no unique owner (anchor resolution,
    the full scan performed by `impact`, and the symbol naming used by `changed` all
    depend on that path being unique).
    """
    resolved = [r.resolve() for r in roots]
    for i, a in enumerate(resolved):
        for j, b in enumerate(resolved):
            if i == j:
                continue
            if a == b or b in a.parents:
                raise ValueError(
                    f"{S.CONFIG_FILENAME} code_root entries overlap: "
                    f"{raw_values[j]!r} is the same as or an ancestor of {raw_values[i]!r}; "
                    "code roots must not nest or repeat"
                )

    seen: dict[str, Path] = {}
    for root in resolved:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            rel = str(path.relative_to(root))
            owner = seen.get(rel)
            if owner is not None and owner != root:
                raise ValueError(
                    f"{S.CONFIG_FILENAME} code_root is ambiguous: {rel} exists under "
                    f"both {owner} and {root}; symbol names relpath::name need a unique "
                    "owner, restructure so relative paths do not collide"
                )
            seen.setdefault(rel, root)


def _normalize_code_root(repo_root: Path, value) -> Path | tuple[Path, ...]:
    """The code_root field of .spec-drift.json: a string (the original shape) or a non-empty list of strings (new)."""
    if isinstance(value, str):
        return repo_root / value
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        if len(set(value)) != len(value):
            raise ValueError(f"{S.CONFIG_FILENAME} code_root list contains duplicates: {value}")
        roots = [repo_root / v for v in value]
        if len(roots) > 1:
            _validate_multi_code_roots(value, roots)
        return tuple(roots)
    raise ValueError(
        f"{S.CONFIG_FILENAME} code_root must be a string or a non-empty list of strings, got {value!r}"
    )


def build_ctx(repo_root: Path | None = None) -> Ctx:
    root = repo_root or find_repo_root()
    cfg = S.load_config(root)
    return Ctx(
        root,
        _normalize_code_root(root, cfg["code_root"]),
        root / cfg["ledger"],
        root / cfg["lock"],
        cfg["owner"],
        cfg["assistant"],
        L.labels_from_config(cfg),
    )


def split_anchor(anchor: str) -> tuple[str, str]:
    """Split on the first ::; everything after it is the symbol name (a class method is Foo::bar)."""
    if "::" not in anchor:
        raise ValueError(f"malformed anchor (no ::): {anchor}")
    path, _sep, name = anchor.partition("::")
    return path, name


def _resolve_relpath(ctx: Ctx, relpath: str) -> Path | None:
    """Find the real file for relpath among ctx.code_roots.

    0 matches -> None (the same "file does not exist" meaning as before multi-root
    support was added); 1 match -> that Path; 2 or more matches -> a loud error, never
    a silent pick. The multi-value validation in `build_ctx` already makes this
    impossible under a normal config; this is the second line of defence, guarding the
    case where a Ctx is hand-built bypassing build_ctx (a test assembling a code_root
    tuple directly, say). In the single-value case ctx.code_roots holds one item and
    this function is byte-for-byte equivalent to the plain existence check used before.
    """
    matches = [root / relpath for root in ctx.code_roots if (root / relpath).exists()]
    if len(matches) > 1:
        raise ValueError(
            f"anchor path {relpath!r} exists under more than one code_root "
            f"({', '.join(str(m) for m in matches)}); its owner cannot be determined"
        )
    return matches[0] if matches else None


def read_source(ctx: Ctx, relpath: str) -> str | None:
    path = _resolve_relpath(ctx, relpath)
    if path is None:
        return None
    return path.read_text(encoding="utf-8")


def current_spans(ctx: Ctx, anchor: str) -> list[tuple[int, int]] | None:
    relpath, name = split_anchor(anchor)
    src = read_source(ctx, relpath)
    if src is None:
        return None
    _top, syms = S.parse_symbols(src, filename=relpath)
    return syms.get(name)


def current_fingerprint(ctx: Ctx, anchor: str) -> str | None:
    relpath, name = split_anchor(anchor)
    src = read_source(ctx, relpath)
    if src is None:
        return None
    _top, syms = S.parse_symbols(src, filename=relpath)
    if name not in syms:
        return None
    return S.fingerprint(S.split_lines(src), syms[name])


def duplicate_names(ctx: Ctx, anchors: list[str]) -> list[str]:
    """Self-check 5: for ledger anchors whose name is defined more than once, return the anchor strings."""
    out = []
    for anchor in anchors:
        spans = current_spans(ctx, anchor)
        if spans and len(spans) > 1:
            out.append(f"{anchor} ({len(spans)} definitions)")
    return out
