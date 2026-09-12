"""verdicts: grade filled-in `inventory` verdict tables against the verdict disciplines.

The adoption guide lists the three mistakes verdicts most often make. Each has a
mechanical half, and on two real adoptions that half was checked by a script written on
the spot; this command is that script, made general:

1. ① "asserted by entry X" must name an entry that exists, matched as a whole ID (so
   `R-T-0011` is not `R-T-001`), and every wording it quotes — in straight or curly double
   quotes or CJK corner brackets, outside backtick code spans — must be findable verbatim
   in the ledger (whitespace-normalised). Whether the quote also covers every decision the
   line makes is a judgement, not checked here.
2. ② "belongs to another book" must name an existing entry ID, or a book the ledger places
   outside itself (declared with `--book`).
3. ③ "no business meaning" must not reason from "the ledger does not say so". This is a
   phrase screen, not a reading of the reason's logic.

It also refuses a row with no verdict, a verdict that is none of the four, a ②/③/④ with
no reason (④'s reason is the draft assertion), a row without exactly six cells, and a file
with no verdict table. Only rows under the `inventory` header row are graded; the totals
table, prose and fenced code blocks are skipped. Read-only; exit 0 when every row passes,
1 when any fails, 2 when a file cannot be read.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import ledger as L
from cmd_inventory import VERDICT_KINDS

HEADER = ["#", "Category", "Line", "Source", "Verdict", "Reason"]
SYMBOL_HEADING = re.compile(r"^## `([^`]+)`")
SEPARATOR = re.compile(r"^\|(\s*:?-+:?\s*\|)+$")
CIRCLED = "①②③④"
KIND_ORDER = ("asserted by entry", "belongs to another book", "no business meaning", "gap")
KIND = re.compile(r"^(" + "|".join(KIND_ORDER) + r")\b", re.I)
# Straight and curly double quotes, and the two CJK corner-bracket pairs.
QUOTE = re.compile('"([^"]+)"|“([^”]+)”|\u300c([^\u300d]+)\u300d|\u300e([^\u300f]+)\u300f')
CODE_SPAN = re.compile(r"`[^`]*`")
LEDGER_SAYS_NOTHING = re.compile(
    r"ledger\s+(?:does\s*n[o']?t|doesn't|never)\s+(?:say|mention|cover|assert)"
    r"|not\s+(?:in|covered\s+by)\s+the\s+ledger"
    r"|no\s+entry\s+(?:says|covers|asserts|mentions)"
    # the same in Chinese: "the ledger (has not / does not write / does not mention / does not cover)"
    r"|\u53f0\u8d26(?:\u91cc|\u4e2d|\u4e0a)?(?:\u6ca1\u6709|\u6ca1\u5199|\u672a\u5199|\u6ca1\u63d0|\u672a\u63d0|\u4e0d\u6d89\u53ca|\u6ca1\u8bf4|\u672a\u8986\u76d6|\u6ca1\u8986\u76d6)",
    re.I,
)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _kind(verdict: str) -> int | None:
    v = verdict.strip()
    if v[:1] in CIRCLED:
        return CIRCLED.index(v[0])
    m = KIND.match(v)
    return KIND_ORDER.index(m.group(1).lower()) if m else None


def _cells(line: str) -> list[str]:
    """Split one table row on unescaped pipes, keeping empty cells (`||` is an empty cell)."""
    body = line.strip().replace("\\|", "\x00")
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip().replace("\x00", "|") for c in body.split("|")]


def _rows(text: str):
    """Yield (symbol, cells) for every row of every verdict table; skip other tables, prose and fenced code."""
    symbol, in_fence, state = "?", False, None  # state: None, "header" (separator next), "rows"
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence, state = not in_fence, None
            continue
        if in_fence:
            continue
        heading = SYMBOL_HEADING.match(line)
        if heading:
            symbol, state = heading.group(1), None
            continue
        if not s.startswith("|"):
            state = None
            continue
        if state is None:
            state = "header" if _cells(s) == HEADER else "other"
            continue
        if state == "header":
            state = "rows" if SEPARATOR.match(s) else "other"
            continue
        if state == "rows":
            yield symbol, _cells(s)


def _grade(text: str, id_patterns, ledger_norm: str, books: list[str]):
    counts = [0, 0, 0, 0]
    problems: list[str] = []
    rows = unfilled = 0
    for symbol, cells in _rows(text):
        rows += 1
        if len(cells) != 6:
            problems.append(f"[malformed row] {symbol}: {len(cells)} cells, expected 6: {' | '.join(cells)[:70]!r}")
            continue
        num, _category, line_no, _source, verdict, reason = cells
        where = f"{symbol} row {num} (line {line_no})"
        if not verdict:
            unfilled += 1
            problems.append(f"[no verdict] {where}")
            continue
        kind = _kind(verdict)
        if kind is None:
            problems.append(f"[unknown verdict] {where}: {verdict[:60]!r} is none of the four")
            continue
        counts[kind] += 1
        named = {i for i, pattern in id_patterns if pattern.search(verdict) or pattern.search(reason)}
        if kind == 0:
            if not named:
                problems.append(f"[① no entry] {where}: names no entry ID that exists in the ledger")
            for groups in QUOTE.findall(CODE_SPAN.sub(" ", verdict + " " + reason)):
                quote = _norm(next(g for g in groups if g))
                if quote and quote not in ledger_norm:
                    problems.append(f"[① quote not in ledger] {where}: {quote[:80]!r}")
            continue
        if not reason:
            problems.append(f"[{CIRCLED[kind]} no reason] {where}")
            continue
        if kind == 1 and not named and not any(b in reason for b in books):
            problems.append(f"[② no book] {where}: names neither an existing entry ID nor a book given with --book")
        if kind == 2 and LEDGER_SAYS_NOTHING.search(reason):
            problems.append(f"[③ from silence] {where}: reasons from \"the ledger does not say so\"")
    if not rows:
        problems.append("[no table] no row under the inventory header row (# | Category | Line | Source | Verdict | Reason)")
    return rows, unfilled, counts, problems


def run(ctx, files: list[str], books: list[str] | None = None) -> int:
    text = ctx.ledger_path.read_text(encoding="utf-8")
    ids = L.parse_ledger(text, ctx.labels)
    id_patterns = [(i, re.compile(r"(?<![\w-])" + re.escape(i) + r"(?![\w-])")) for i in ids]
    ledger_norm = _norm(text)
    books = books or []
    failed = False
    for name in files:
        try:
            content = Path(name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"❌ cannot read verdict file {name}: {e}", file=sys.stderr)
            return 2
        rows, unfilled, counts, problems = _grade(content, id_patterns, ledger_norm, books)
        tally = " ".join(f"{CIRCLED[i]} {counts[i]}" for i in range(4))
        print(f"== {name}: {rows} rows, {unfilled} without a verdict · {tally}")
        for p in problems:
            print(f"  {p}")
        failed = failed or bool(problems)
    print(f"\nThe four verdicts are: {', '.join(repr(k) for k in VERDICT_KINDS)}.")
    return 1 if failed else 0
