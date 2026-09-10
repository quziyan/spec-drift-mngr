"""Symbol location and fingerprinting.

This module is pure functions: source text in, symbol spans and sha256 fingerprints out.
It never touches git, never touches the ledger, and reads no file other than
.spec-drift.json.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

PLACEHOLDER = "«symbol»"
MODULE_KEY = "<module>"

CONFIG_FILENAME = ".spec-drift.json"
REQUIRED_CONFIG_KEYS = ("code_root", "ledger", "lock", "owner", "assistant")


def load_config(repo_root: Path) -> dict:
    """Read .spec-drift.json at the repository root. All five fields are required and
    none of them gets a default.

    Silently falling back to a default is exactly the disease this tool exists to treat:
    project-specific values must be written explicitly in the config.
    """
    path = repo_root / CONFIG_FILENAME
    cfg = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in cfg]
    if missing:
        raise ValueError(f"{CONFIG_FILENAME} is missing required field(s): {', '.join(missing)}")
    return cfg


def load_code_root(repo_root: Path) -> Path:
    return repo_root / load_config(repo_root)["code_root"]


def split_lines(src: str) -> list[str]:
    """Unify line endings, then split on \\n. Trailing whitespace is not stripped here —
    normalization happens in _normalize."""
    return src.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _normalize(lines: list[str]) -> str:
    """Strip trailing whitespace from every line, then join with \\n."""
    return "\n".join(line.rstrip() for line in lines)


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _first_lineno(node: ast.AST) -> int:
    """With decorators present, take the first decorator line."""
    decorators = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decorators])


def _comment_start(lines: list[str], first_lineno: int) -> int:
    """Walk up from first_lineno absorbing a contiguous run of # comment lines.

    - Stop at the first blank line or non-comment line.
    - File-header exception: if the walk reaches line 1 of the file without ever meeting
      a blank or non-comment line, the block counts as a file-header comment and none of
      it is absorbed.
    - Priority: the "stop at a blank line" scan runs first, so when a file opens with a
      blank line the scan stops at that blank line, j is not 0, and the exception does
      not fire.
    """
    idx = first_lineno - 1          # 0-based
    j = idx
    while j - 1 >= 0 and lines[j - 1].strip().startswith("#"):
        j -= 1
    if j == 0 and idx > 0:
        return first_lineno         # file-header exception
    return j + 1


def _span(lines: list[str], node: ast.AST) -> tuple[int, int]:
    return (_comment_start(lines, _first_lineno(node)), node.end_lineno)


def _assign_names(node: ast.AST) -> list[str]:
    """Module-level constants. Tuple unpacking creates no symbol; its lines fall into ::<module>."""
    if isinstance(node, ast.AnnAssign):
        return [node.target.id] if isinstance(node.target, ast.Name) else []
    if isinstance(node, ast.Assign):
        names = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            else:
                return []           # tuple/attribute/subscript unpacking: the whole statement creates no symbol
        return names
    return []


_DEF = (ast.FunctionDef, ast.AsyncFunctionDef)


def parse_symbols(src: str, filename: str = "<unknown>"):
    """-> (top_level, symbols)

    top_level: [(name, start, end)] top-level symbols in source order, used only for the ::<module> projection.
    symbols:   {symbol name: [(start, end), ...]} the five kinds of symbol; when a name is defined
               more than once, every candidate is kept, in order of appearance.

    filename: passed through to ast.parse; it only affects the file name shown in a SyntaxError.
    """
    lines = split_lines(src)
    tree = ast.parse(src, filename=filename)
    top_level: list[tuple[str, int, int]] = []
    symbols: dict[str, list[tuple[int, int]]] = {}

    def add(name: str, span: tuple[int, int]) -> None:
        symbols.setdefault(name, []).append(span)

    for node in tree.body:
        if isinstance(node, _DEF + (ast.ClassDef,)):
            span = _span(lines, node)
            top_level.append((node.name, span[0], span[1]))
            add(node.name, span)
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, _DEF):
                        add(f"{node.name}::{sub.name}", _span(lines, sub))
        else:
            for name in _assign_names(node):
                span = _span(lines, node)
                top_level.append((name, span[0], span[1]))
                add(name, span)

    top_level.sort(key=lambda t: t[1])
    return top_level, symbols


def fingerprint(lines: list[str], spans: list[tuple[int, int]]) -> str:
    """Slice whole lines, concatenate every candidate in order of appearance, normalize, sha256."""
    picked: list[str] = []
    for start, end in spans:
        picked.extend(lines[start - 1:end])
    return _sha(_normalize(picked))


def module_fingerprint(lines: list[str], top_level: list[tuple[str, int, int]]) -> str:
    """The ::<module> pseudo-symbol: each top-level symbol's span is replaced wholesale by
    a single anonymous placeholder line, every other line is kept as is.

    Anonymity (the placeholder carries no symbol name) is an empirical conclusion: with
    the name included, renaming a symbol or swapping two top-level functions pulled
    ::<module> into the changed set as well; anonymous, both kinds of noise disappear
    while an import moved across functions is still caught. When a name has several
    candidate spans, each span gets its own placeholder (each has its own start line).
    """
    starts = {start: end for (_name, start, end) in top_level}
    out: list[str] = []
    i = 1
    while i <= len(lines):
        if i in starts:
            out.append(PLACEHOLDER)
            i = starts[i] + 1
        else:
            out.append(lines[i - 1])
            i += 1
    return _sha(_normalize(out))


def file_symbol_map(src: str, filename: str = "<unknown>") -> dict[str, str]:
    """Parse the file once and produce the fingerprints of all its symbols, including ::<module>.
    This is the main entry point for `changed`.

    A SyntaxError / UnicodeDecodeError from parsing is re-raised unchanged, so the caller
    can fail closed.
    filename: passed through to parse_symbols; it only affects the file name shown in a SyntaxError.
    """
    lines = split_lines(src)
    top_level, symbols = parse_symbols(src, filename=filename)
    result = {name: fingerprint(lines, spans) for name, spans in symbols.items()}
    result[MODULE_KEY] = module_fingerprint(lines, top_level)
    return result


def file_symbol_order(src: str) -> list[str]:
    """The keys of this file's **top-level symbols plus class methods**, in order of
    appearance. Used for the position-by-position comparison."""
    _top, symbols = parse_symbols(src)
    flat = [(spans[0][0], name) for name, spans in symbols.items()]
    flat.sort()
    return [name for (_line, name) in flat]
