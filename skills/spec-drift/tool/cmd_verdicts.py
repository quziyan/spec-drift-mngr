"""verdicts: grade filled-in `inventory` verdict tables against the three disciplines.

The adoption guide lists the three mistakes verdicts most often make. Each has a
mechanical half, and on two real adoptions that half was checked by a script written on
the spot; this command is that script, made general:

1. ① "asserted by entry X" must name an entry that exists, and every ledger wording it
   quotes must be findable verbatim in the ledger (whitespace-normalised). Whether the
   quote also covers every decision the line makes is a judgement, not checked here.
2. ② "belongs to another book" must name an existing entry ID, or a book the ledger has
   placed outside itself (declared with `--book`).
3. ③ "no business meaning" must not reason from "the ledger does not say so".

It also refuses a row with no verdict, a verdict that is none of the four, and a ②/③/④
with no reason (④'s reason is the draft assertion). Read-only; exit 0 when every row
passes, 1 when any row fails, 2 when a file cannot be read.
"""
from __future__ import annotations

import re
from pathlib import Path

import ledger as L
from cmd_inventory import VERDICT_KINDS

ROW = re.compile(r"^\|\s*(\d+)\s*\|")
SYMBOL_HEADING = re.compile(r"^## `([^`]+)`")
CIRCLED = "①②③④"
# Wording quoted from the ledger. Backticks are left out on purpose: in a reason they
# quote code far more often than ledger text.
# Straight and curly double quotes, and the two CJK corner-bracket pairs.
QUOTE = re.compile('"([^"]+)"|\u201c([^\u201d]+)\u201d|\u300c([^\u300d]+)\u300d|\u300e([^\u300f]+)\u300f')
MIN_QUOTE_CHARS = 6
LEDGER_SAYS_NOTHING = re.compile(
    r"ledger\s+(?:does\s*n[o']?t|doesn't|never)\s+(?:say|mention|cover|assert)"
    r"|not\s+(?:in|covered\s+by)\s+the\s+ledger"
    r"|no\s+entry\s+(?:says|covers|asserts|mentions)"
    # the same in Chinese: "the ledger (has not / does not write / does not mention / does not cover)"
    r"|\u53f0\u8d26(?:\u91cc|\u4e2d|\u4e0a)?(?:\u6ca1\u6709|\u6ca1\u5199|\u672a\u5199|\u6ca1\u63d0|\u672a\u63d0|\u4e0d\u6d89\u53ca|\u6ca1\u8bf4|\u672a\u8986\u76d6|\u6ca1\u8986\u76d6)",
    re.I,
)
KIND_PREFIXES = ("asserted by entry", "belongs to another book", "no business meaning", "gap")


def _norm(text: str) -> str:
    return " ".join(text.split())


def _kind(verdict: str) -> int | None:
    v = verdict.strip()
    if v[:1] in CIRCLED:
        return CIRCLED.index(v[0])
    low = v.lower()
    for i, prefix in enumerate(KIND_PREFIXES):
        if low.startswith(prefix):
            return i
    return None


def _cells(line: str) -> list[str]:
    # A pipe inside a cell is written `\|` in markdown; keep it out of the split.
    return [c.strip().replace("\x00", "|") for c in line.replace("\\|", "\x00").strip().strip("|").split("|")]


def _grade_file(path: Path, ids: set[str], ledger_norm: str, books: list[str]):
    counts = [0, 0, 0, 0]
    problems: list[str] = []
    rows = unfilled = 0
    symbol = "?"
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = SYMBOL_HEADING.match(line)
        if heading:
            symbol = heading.group(1)
            continue
        m = ROW.match(line)
        if not m:
            continue
        cells = _cells(line)
        if len(cells) < 6:
            continue
        rows += 1
        where = f"{symbol} row {m.group(1)} (line {cells[2]})"
        verdict, reason = cells[-2], cells[-1]
        if not verdict:
            unfilled += 1
            problems.append(f"[no verdict] {where}")
            continue
        kind = _kind(verdict)
        if kind is None:
            problems.append(f"[unknown verdict] {where}: {verdict[:60]!r} is none of the four")
            continue
        counts[kind] += 1
        named = {i for i in ids if i in verdict or i in reason}
        if kind == 0:
            if not named:
                problems.append(f"[① no entry] {where}: names no entry ID that exists in the ledger")
            for groups in QUOTE.findall(reason):
                quote = _norm(next(g for g in groups if g))
                if len(quote) >= MIN_QUOTE_CHARS and quote not in ledger_norm:
                    problems.append(f"[① quote not in ledger] {where}: {quote[:80]!r}")
            continue
        if not reason:
            problems.append(f"[{CIRCLED[kind]} no reason] {where}")
            continue
        if kind == 1 and not named and not any(b in reason for b in books):
            problems.append(
                f"[② no book] {where}: names neither an existing entry ID nor a book given with --book"
            )
        if kind == 2 and LEDGER_SAYS_NOTHING.search(reason):
            problems.append(f"[③ from silence] {where}: reasons from \"the ledger does not say so\"")
    return rows, unfilled, counts, problems


def run(ctx, files: list[str], books: list[str] | None = None) -> int:
    text = ctx.ledger_path.read_text(encoding="utf-8")
    ids = set(L.parse_ledger(text, ctx.labels))
    ledger_norm = _norm(text)
    books = books or []
    failed = False
    for name in files:
        path = Path(name)
        if not path.is_file():
            print(f"error: verdict file not found: {name}")
            return 2
        rows, unfilled, counts, problems = _grade_file(path, ids, ledger_norm, books)
        tally = " ".join(f"{CIRCLED[i]} {counts[i]}" for i in range(4))
        print(f"== {name}: {rows} rows, {unfilled} without a verdict · {tally}")
        for p in problems:
            print(f"  {p}")
        if not rows:
            print("  ⚠ no inventory table rows found in this file")
        failed = failed or bool(problems)
    print(f"\nThe four verdicts are: {', '.join(repr(k) for k in VERDICT_KINDS)}.")
    return 1 if failed else 0
