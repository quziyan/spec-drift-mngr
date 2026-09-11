"""inventory: the rule-level stock-take scaffold for building a ledger over existing code.

Folded in from a one-off script; its generic core is: given a symbol, enumerate eight kinds
of element under an exhaustive AST criterion and print a markdown table skeleton for a
human (or a model) to fill the "verdict" and "reason" columns in, item by item.

This command **makes no judgement at all** — judging is a human job, the command only
guarantees that nothing is missed.

The eight kinds (the criteria are fixed; none may be added or removed):
  ① conditional branches: the test of an If counts one, an else that is not an elif counts
    one; an IfExp counts one; every case of a match counts one
  ② Return statements, plus every BoolOp operand and every Compare comparison inside the
    returned expression (each counting as one item)
  ③ raise
  ④ cross-module calls: the root name of the call appears in this module's import list
  ⑤ writes to object fields: counted per assignment target, an Attribute or a Subscript
    target counting one each (a chained assignment a.x = b.y = 1 counts 2, the same
    criterion the one-off script used)
  ⑥ member assignments in a class body (class symbols only; a class anchor covers the class
    body level and does not descend into method bodies — the contents of a method body are
    enumerated separately under `Class::method`, so nothing is counted twice across a class
    and its methods)
  ⑦ assignments to a Name target (tuple unpacking included)
  ⑧ ExceptHandler

For the known limits see `KNOWN_LIMITATIONS` below (copied verbatim from the one-off script
and from the rule-level inventory document it produced, after re-reading both to check them
— not paraphrased).
"""
from __future__ import annotations

import ast
from pathlib import Path

import ledger as L
import repo
import symbols as S

TOOL_DIR = Path(__file__).resolve().parent

CATS = [
    "① branch", "② return", "③ raise", "④ cross-module call",
    "⑤ field write", "⑥ class member", "⑦ name assignment", "⑧ except",
]

VERDICT_KINDS = (
    "asserted by entry X",
    "belongs to another book, no entry this round",
    "no business meaning (purely technical)",
    "gap: no entry asserts this yet",
)

KNOWN_LIMITATIONS = """\
## Known limits

This "exhaustive AST element criterion" guarantees that **nothing is missed within the
categories being enumerated**, but the categories themselves have a boundary. Each item
below was copied, not paraphrased, after re-reading the one-off script this command was
folded in from and the rule-level inventory document that script produced:

1. **Calls to functions in the same module do not count as "④ cross-module call"** (still a
   human job). The criterion is whether the root name of the call appears in this module's
   import list, so calls to helpers in the same file (`_helper_a(...)`, `_helper_b(...)`,
   `_helper_c(...)`) contribute nothing at all. They are exactly where anchor blind spots
   breed — among the blind spots the one-off script turned up, the true source of several
   was hiding behind a same-module call like these.
2. **Comparisons inside the arguments of a call do not count as "② return"** (still a human
   job). ② only covers the `BoolOp`/`Compare` inside a `return` expression, so a CAS guard
   written into the arguments of a call such as `and_(...)` (say
   `Order.revision < snap.revision`) is never enumerated — the whole call can only be
   recorded as one ④ or ⑤ item, with the reason column naming and checking each guard it
   contains one by one.
3. **"What the code deliberately does not do" cannot be taken stock of** (it cannot be
   mechanised). The core of some assertions is precisely that a call is *absent* from the
   code (such as "once the case is closed, no result card is sent"), and an absence has no
   AST element to correspond to; it can only be found by reading the entry text and working
   back into the code.
4. **Judgements assigned to local variables, and the whole `except` handler category** —
   the first version of the one-off script left these two out of its six categories (a
   judgement kept in a local variable, and which class of exception is being caught, were
   both real blind spots), and they were later added as categories of their own. This
   command has them built in as ⑦ and ⑧, so they are no longer blind spots; the note is
   here to state honestly that they once were.
"""


def module_imports(tree: ast.Module) -> set[str]:
    """The root names introduced by module-level imports (as-aliases included). Used to judge "cross-module call"."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def root_name(node: ast.AST) -> str | None:
    """The leftmost Name of a call target (a.b.c() → 'a'; f() → 'f')."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def src_of(lines: list[str], node: ast.AST, limit: int = 88) -> str:
    """The source of the node's first line (whitespace stripped, pipes escaped so the table does not eat them)."""
    text = lines[node.lineno - 1].strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text.replace("|", "\\|")


def expr_src(lines: list[str], node: ast.AST, limit: int = 88) -> str:
    """The source of an expression fragment; a multi-line one degrades to its first line."""
    try:
        text = ast.get_source_segment("\n".join(lines), node) or ""
    except Exception:  # noqa: BLE001  no fragment available, fall back to the first line
        text = ""
    text = " ".join(text.split()) or lines[node.lineno - 1].strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text.replace("|", "\\|")


def find_symbol(tree: ast.Module, name: str) -> ast.AST | None:
    """Locate the symbol node at module top level, under the naming convention of symbols.py (Class::method locates that method)."""
    if "::" in name:
        cls_name, _, method_name = name.partition("::")
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == cls_name:
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == method_name:
                        return sub
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return node
    return None


def _class_body_nodes(node: ast.ClassDef):
    """Walk the class body but **do not descend into method bodies** — a method is already enumerated on its own as `Class::method`,

    so following `ast.walk(node)` down into method bodies would count everything inside them
    twice, once in the class-level anchor's total and once in the method-level one. A class
    anchor therefore covers the class body level only (nested non-function structures
    included, such as an `if` inside the class body), skipping method definitions whole.
    """
    stack = list(node.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def collect(node: ast.AST, lines: list[str], imports: set[str]) -> list[tuple[str, int, str]]:
    """→ [(category, line, code)], sorted by line (ties in the order of CATS). All eight kinds in one pass."""
    items: list[tuple[str, int, str]] = []
    skip_ids: set[int] = set()

    # ⑥ member assignments in the class body (enumerated only when the anchor itself is a
    # class, over its immediate class body, so as not to double-count with ⑦)
    if isinstance(node, ast.ClassDef):
        for sub in node.body:
            if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                items.append(("⑥ class member", sub.lineno, src_of(lines, sub)))
                skip_ids.add(id(sub))

    walk_iter = _class_body_nodes(node) if isinstance(node, ast.ClassDef) else ast.walk(node)
    for n in walk_iter:
        # ① conditional branches
        if isinstance(n, ast.If):
            items.append(("① branch", n.test.lineno, "if " + expr_src(lines, n.test)))
            if n.orelse and not (len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If)):
                items.append(("① branch", n.orelse[0].lineno, "else → " + src_of(lines, n.orelse[0])))
        elif isinstance(n, ast.IfExp):
            items.append(("① branch", n.lineno, "ternary " + expr_src(lines, n)))
        elif isinstance(n, ast.Match):
            for case in n.cases:
                items.append(("① branch", case.pattern.lineno, "case " + expr_src(lines, case.pattern)))

        # ② Return, plus the BoolOp operands / Compare comparisons in the returned expression
        elif isinstance(n, ast.Return):
            items.append(("② return", n.lineno, src_of(lines, n)))
            if n.value is not None:
                for sub in ast.walk(n.value):
                    if isinstance(sub, ast.BoolOp):
                        for operand in sub.values:
                            items.append(
                                ("② return", operand.lineno, "  operand " + expr_src(lines, operand))
                            )
                    elif isinstance(sub, ast.Compare):
                        for i, op in enumerate(sub.ops):
                            left = sub.left if i == 0 else sub.comparators[i - 1]
                            items.append((
                                "② return",
                                left.lineno,
                                "  comparison "
                                + expr_src(lines, left)
                                + f" {type(op).__name__} "
                                + expr_src(lines, sub.comparators[i]),
                            ))

        # ③ raise
        elif isinstance(n, ast.Raise):
            items.append(("③ raise", n.lineno, src_of(lines, n)))

        # ④ cross-module calls
        elif isinstance(n, ast.Call):
            root = root_name(n.func)
            if root is not None and root in imports:
                items.append(("④ cross-module call", n.lineno, expr_src(lines, n.func) + "(…)"))
            # ⑤-b .values(kw=…): the field writes of a SQLAlchemy update/insert
            if isinstance(n.func, ast.Attribute) and n.func.attr == "values":
                for kw in n.keywords:
                    if kw.arg:
                        items.append((
                            "⑤ field write",
                            kw.value.lineno,
                            f".values {kw.arg}={expr_src(lines, kw.value, 40)}",
                        ))
            # ⑤-d model-construction keywords (a class that came from an import and starts with a capital)
            if isinstance(n.func, ast.Name) and n.func.id in imports and n.func.id[:1].isupper():
                for kw in n.keywords:
                    if kw.arg:
                        items.append((
                            "⑤ field write",
                            kw.value.lineno,
                            f"{n.func.id}(… {kw.arg}={expr_src(lines, kw.value, 40)})",
                        ))

        # ⑤-a attribute assignment / ⑤-c dictionary-subscript assignment: loop over the
        # targets, and each Attribute/Subscript target in one statement counts as one item
        # (the same criterion as the one-off script — a chained assignment a.x = b.y = 1
        # counts 2; that is a quirk of the script itself, but it is its real behaviour, and
        # the criterion is aligned to it rather than changed).
        # ⑦ assignment to a Name target (tuple unpacking included): one statement counts as
        # 1 item, criterion unchanged.
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, (ast.Attribute, ast.Subscript)):
                    items.append(("⑤ field write", n.lineno, src_of(lines, n)))
            if id(n) not in skip_ids and any(isinstance(t, (ast.Name, ast.Tuple)) for t in targets):
                items.append(("⑦ name assignment", n.lineno, expr_src(lines, n)))

        # ⑧ except handlers
        elif isinstance(n, ast.ExceptHandler):
            kind = expr_src(lines, n.type, 60) if n.type is not None else "(bare except)"
            items.append(("⑧ except", n.lineno, f"except {kind}"))

    items.sort(key=lambda it: (it[1], CATS.index(it[0])))
    return items


def _render_symbol(
    relpath: str, name: str, node: ast.AST, items: list[tuple[str, int, str]]
) -> tuple[list[str], dict[str, int]]:
    out: list[str] = []
    counts = dict.fromkeys(CATS, 0)
    for cat, _ln, _code in items:
        counts[cat] += 1
    out.append(f"## `{relpath}::{name}` (lines {node.lineno}-{node.end_lineno}, items: {len(items)})\n")
    if isinstance(node, ast.ClassDef):
        methods = [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if methods:
            out.append(
                "> The methods of this class are enumerated on their own; this table does not cover method bodies: " +
                ", ".join(f"`{relpath}::{name}::{m}`" for m in methods) + "\n"
            )
    out.append("Subtotal: " + ", ".join(f"{c} {counts[c]}" for c in CATS) + "\n")
    if not items:
        out.append("(no items)\n")
        return out, counts
    out.append("| # | Category | Line | Source | Verdict | Reason |")
    out.append("|---|---|---|---|---|---|")
    for i, (cat, ln, code) in enumerate(items, 1):
        out.append(f"| {i} | {cat} | {ln} | `{code}` | | |")
    out.append("")
    return out, counts


def _inventory_one(ctx, relpath: str, name: str) -> tuple[list[str], dict[str, int]] | None:
    """Take stock of a single symbol. On a parse or lookup failure, print a diagnostic and return None (do not abort the whole command)."""
    if name == S.MODULE_KEY:
        print(f"⚠ `{relpath}::{S.MODULE_KEY}` is a pseudo-symbol, per-symbol stock-taking does not apply, skipped")
        return None
    src = repo.read_source(ctx, relpath)
    if src is None:
        print(f"⚠ `{relpath}::{name}`: the file does not exist, skipped")
        return None
    lines = S.split_lines(src)
    try:
        tree = ast.parse(src, filename=relpath)
    except SyntaxError as e:
        print(f"⚠ `{relpath}`: parsing failed ({e}), skipped")
        return None
    node = find_symbol(tree, name)
    if node is None:
        print(f"⚠ `{relpath}::{name}`: no such symbol in the code, skipped")
        return None
    items = collect(node, lines, module_imports(tree))
    return _render_symbol(relpath, name, node, items)


def _ledger_anchors(ctx) -> list[str]:
    """Every production symbol the ledger currently anchors (those under any `tests` directory excluded), deduplicated and sorted by anchor string."""
    entries = L.parse_ledger(ctx.ledger_path.read_text(encoding="utf-8"), ctx.labels)
    anchors: set[str] = set()
    for entry in entries.values():
        for anchor in entry.anchors:
            relpath, _name = repo.split_anchor(anchor)
            if repo.is_test_path(relpath):
                continue
            anchors.add(anchor)
    return sorted(anchors)


def _print_footer(grand: dict[str, int]) -> None:
    print("## Totals\n")
    print("| " + " | ".join(CATS) + " | Total |")
    print("|" + "---|" * (len(CATS) + 1))
    print("| " + " | ".join(str(grand[c]) for c in CATS) + f" | **{sum(grand.values())}** |\n")

    print("## How to fill in the verdict\n")
    print(
        "There are four verdicts: ① `" + VERDICT_KINDS[0] + "` — the meaning of this item "
        "matches a sentence in the assertion text of that entry, and the quoted wording must "
        "be findable verbatim in the ledger **and must cover every decision this item makes** "
        "(an item that decides two things is ① only if the entry asserts both); ② `"
        + VERDICT_KINDS[1] + "` — the item does carry business meaning, but it belongs to "
        "another book, one the head of this ledger has already placed outside it; ③ `"
        + VERDICT_KINDS[2] + "` — changing it changes no state transition and nothing shown "
        "to the outside, and \"the ledger does not say so\" is never a reason for ③; ④ `"
        + VERDICT_KINDS[3] + "` — the item decides something stored, returned, refused or "
        "shown, and no entry covers it: the reason is a one-sentence draft assertion for the "
        "owner to rule on. **Verdicts ②, ③ and ④ must state a reason**, and ① can simply "
        "cite the entry ID.\n"
    )
    print(KNOWN_LIMITATIONS)


def _run_targets(ctx, targets: list[tuple[str, str]]) -> None:
    grand = dict.fromkeys(CATS, 0)
    print("# Rule-level inventory\n")
    print(
        f'> This table is generated by `python3 "{TOOL_DIR}" inventory`: '
        "the eight kinds of AST element are enumerated exhaustively by the command, "
        "**the verdict and the reason have to be filled in by a human or a model, item by "
        "item** — the command itself makes no judgement.\n"
    )
    any_rendered = False
    for relpath, name in targets:
        result = _inventory_one(ctx, relpath, name)
        if result is None:
            continue
        md_lines, counts = result
        for c in CATS:
            grand[c] += counts[c]
        for line in md_lines:
            print(line)
        any_rendered = True
    if not any_rendered:
        print("(no symbols to take stock of)\n")
    _print_footer(grand)


def run(ctx, *, symbol: str | None = None, file: str | None = None) -> int:
    """The single entry point of the inventory command. A query command: the exit code is always 0."""
    if symbol is not None:
        relpath, name = repo.split_anchor(symbol)
        _run_targets(ctx, [(relpath, name)])
    elif file is not None:
        src = repo.read_source(ctx, file)
        if src is None:
            print(f"⚠ `{file}`: the file does not exist")
            _run_targets(ctx, [])
            return 0
        names = S.file_symbol_order(src)
        _run_targets(ctx, [(file, name) for name in names])
    else:
        anchors = _ledger_anchors(ctx)
        targets = [repo.split_anchor(a) for a in anchors]
        _run_targets(ctx, targets)
    return 0
