"""Tests for catalog and for ledger.entry_books.

Every status is produced by a real state: entries are signed with the sync command, then
the ledger text or the code is edited to drift them. No lock JSON is written by hand.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import cmd_catalog
import cmd_write
import ledger as L
from tests.test_check import Fixture
from tests.test_cli import _run_in

TODAY = "2026-12-25"

MOD = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"
CALC = "def h():\n    return 3\n"
GONE = "def k():\n    return 4\n"


def entry(entry_id: str, title: str, rule: str, anchors: list[str]) -> str:
    anchor_lines = "\n".join(f"- `{a}`" for a in anchors)
    return (
        f"### {entry_id} {title}\n\n"
        f"**Current rule**\n{rule}\n\n"
        f"**Boundary**\nNothing else is in scope.\n\n"
        f"**Anchors**\n{anchor_lines}\n\n"
        f"**Last confirmed**\n2026-09-01\n"
    )


def ledger(*, after: bool) -> str:
    """The ledger before signing (after=False) and after the edits that drift it (after=True)."""
    parts = [
        entry("R-C-000", "Before any book", "f returns 1.", ["pkg/mod.py::f"]),
        "## Book A: metrics\n",
        entry("R-C-001", "Stays consistent", "g returns 2.", ["pkg/mod.py::g"]),
        entry("R-C-002", "Text edited after signing",
              "h returns three, rounded." if after else "h returns 3.", ["pkg/calc.py::h"]),
        entry("R-C-003", "Code edited after signing", "h is the metric.", ["pkg/calc.py::h"]),
        "## Book B: flows\n",
        entry("R-C-004", "Anchor file deleted", "k returns 4.", ["pkg/gone.py::k"]),
        entry("R-C-005", "Never signed", "f is never signed.", ["pkg/mod.py::f"]),
        entry("R-C-006", "Anchor added after signing", "f and g agree.",
              ["pkg/mod.py::f", "pkg/mod.py::g"] if after else ["pkg/mod.py::f"]),
        entry("R-C-007", "Pipe | title", "a | b\nsecond line", ["pkg/mod.py::f"]),
    ]
    if not after:
        parts.append(entry("R-C-008", "Removed later", "f is removed later.", ["pkg/mod.py::f"]))
    return "\n".join(parts)


SIGNED = ["R-C-000", "R-C-001", "R-C-002", "R-C-003", "R-C-004", "R-C-006", "R-C-007", "R-C-008"]


def build(tmp: Path) -> Fixture:
    fx = Fixture(tmp, md=ledger(after=False), code=MOD)
    pkg = tmp / "backend" / "pkg"
    (pkg / "calc.py").write_text(CALC, encoding="utf-8")
    (pkg / "gone.py").write_text(GONE, encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        for entry_id in SIGNED:
            assert cmd_write.run(fx.ctx, "sync", entry_id, "Alice", f"why {entry_id}", False, TODAY) == 0
    fx.md_path.write_text(ledger(after=True), encoding="utf-8")
    (pkg / "calc.py").write_text("def h():\n    return 30\n", encoding="utf-8")
    (pkg / "gone.py").unlink()
    return fx


def run_catalog(fx, **kwargs) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cmd_catalog.run(fx.ctx, **kwargs)
    return code, out.getvalue(), err.getvalue()


def table_rows(out: str) -> dict[str, list[str]]:
    """ID -> its cells, splitting on unescaped pipes only."""
    rows = {}
    for line in out.splitlines():
        if line.startswith("| R-"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
            rows[cells[0]] = cells
    return rows


class TestCatalogMarkdown(unittest.TestCase):
    def test_header_books_and_columns(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out, err = run_catalog(fx)
            self.assertEqual(code, 0, err)
            self.assertTrue(out.startswith(
                "# Catalog: docs/ledger.md\n\n"
                "8 entries in 3 books: 3 consistent, 2 drifted, 1 anchor missing, "
                "1 unsigned, 1 anchors changed\n\n"
                "## (no book)\n\n"
                "| ID | Title | Status | Signed by | Signed at | Note | Rule | Anchors |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| R-C-000 | Before any book | consistent | Alice | "
            ), out)
            a, b = out.index("\n## Book A: metrics\n"), out.index("\n## Book B: flows\n")
            self.assertLess(out.index("## (no book)"), a)
            self.assertLess(a, b)
            ids = list(table_rows(out))
            self.assertEqual(ids, ["R-C-000", "R-C-001", "R-C-002", "R-C-003",
                                   "R-C-004", "R-C-005", "R-C-006", "R-C-007"])
            self.assertLess(out.index("| R-C-003 |"), b)
            self.assertGreater(out.index("| R-C-004 |"), b)

    def test_each_status_from_a_real_state(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out, _err = run_catalog(fx)
            status = {i: cells[2] for i, cells in table_rows(out).items()}
            self.assertEqual(status, {
                "R-C-000": "consistent",
                "R-C-001": "consistent",
                "R-C-002": "drifted",
                "R-C-003": "drifted",
                "R-C-004": "anchor missing",
                "R-C-005": "unsigned",
                "R-C-006": "anchors changed",
                "R-C-007": "consistent",
            })

    def test_signature_cells(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out, _err = run_catalog(fx)
            rows = table_rows(out)
            _id, _t, _s, by, at, note, rule, anchors = rows["R-C-001"]
            self.assertEqual((by, note, rule), ("Alice", "why R-C-001", "g returns 2."))
            self.assertRegex(at, r"^\d{4}-\d{2}-\d{2}T")
            self.assertEqual(anchors, "`pkg/mod.py::g`")
            self.assertEqual(rows["R-C-005"][3:6], ["", "", ""])
            self.assertEqual(rows["R-C-006"][7], "`pkg/mod.py::f`; `pkg/mod.py::g`")
            self.assertEqual(rows["R-C-006"][3], "Alice")   # S3 still has its lock record

    def test_pipes_escaped_and_lines_joined(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out, _err = run_catalog(fx)
            line = next(l for l in out.splitlines() if l.startswith("| R-C-007 |"))
            self.assertIn("| Pipe \\| title |", line)
            self.assertIn("| a \\| b second line |", line)
            self.assertEqual(len(re.split(r"(?<!\\)\|", line)), 10)

    def test_lock_only_line(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out, _err = run_catalog(fx)
            self.assertTrue(out.rstrip("\n").endswith(
                "\n\nLock-only entries (S2, removed from the ledger): R-C-008"), out)
            self.assertNotIn("| R-C-008 |", out)

    def test_lock_only_line_omitted_when_none(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            with redirect_stdout(io.StringIO()):
                cmd_write.run(fx.ctx, "sync", "R-T-001", "Alice", "n", False, TODAY)
            code, out, _err = run_catalog(fx)
            self.assertEqual(code, 0)
            self.assertNotIn("Lock-only", out)
            self.assertIn("1 entries in 1 books: 1 consistent, 0 drifted", out)
            self.assertIn("## Pilot ledger", out)

    def test_zero_entries_prints_header_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md="# Empty ledger\n\nNothing here yet.\n")
            code, out, _err = run_catalog(fx)
            self.assertEqual(code, 0)
            self.assertEqual(out, "# Catalog: docs/ledger.md\n\n0 entries in 0 books: 0 consistent, "
                                  "0 drifted, 0 anchor missing, 0 unsigned, 0 anchors changed\n")


class TestCatalogBookFilter(unittest.TestCase):
    def test_substring_keeps_matching_books_only(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out, _err = run_catalog(fx, book="metrics")
            self.assertEqual(code, 0)
            self.assertEqual(list(table_rows(out)), ["R-C-001", "R-C-002", "R-C-003"])
            self.assertIn("3 entries in 1 books: 1 consistent, 2 drifted, 0 anchor missing, "
                          "0 unsigned, 0 anchors changed", out)
            self.assertNotIn("## (no book)", out)
            self.assertNotIn("Book B", out)

    def test_filter_is_case_sensitive_and_skips_no_book(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out, _err = run_catalog(fx, book="Book")
            self.assertIn("## Book A: metrics", out)
            self.assertIn("## Book B: flows", out)
            self.assertNotIn("## (no book)", out)
            code, _out, err = run_catalog(fx, book="book a")
            self.assertEqual(code, 2)

    def test_no_match_exits_2_through_cli(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out, err = _run_in(fx.root, ["catalog", "--book", "nope"])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertEqual(err, "❌ no book title contains 'nope' "
                                  "(books: (no book); Book A: metrics; Book B: flows)\n")
            self.assertNotIn("Traceback", err)


class TestCatalogJson(unittest.TestCase):
    def test_shape_order_and_nulls(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out, _err = run_catalog(fx, fmt="json")
            self.assertEqual(code, 0)
            doc = json.loads(out)
            self.assertEqual(list(doc), ["ledger", "entries", "lock_only"])
            self.assertEqual(doc["ledger"], "docs/ledger.md")
            self.assertEqual(doc["lock_only"], ["R-C-008"])
            entries = {e["id"]: e for e in doc["entries"]}
            self.assertEqual([e["id"] for e in doc["entries"]], list(table_rows(run_catalog(fx)[1])))
            self.assertEqual(list(doc["entries"][0]), [
                "id", "title", "book", "status", "state", "signed_by", "signed_at",
                "note", "rule", "boundary", "anchors", "last_confirmed",
            ])
            unsigned = entries["R-C-005"]
            self.assertEqual((unsigned["status"], unsigned["state"]), ("unsigned", "S1"))
            self.assertIsNone(unsigned["signed_by"])
            self.assertIsNone(unsigned["signed_at"])
            self.assertIsNone(unsigned["note"])
            self.assertEqual(entries["R-C-000"]["book"], "")
            self.assertEqual(entries["R-C-006"]["state"], "S3")
            self.assertEqual(entries["R-C-006"]["anchors"], ["pkg/mod.py::f", "pkg/mod.py::g"])
            self.assertEqual(entries["R-C-007"]["rule"], "a | b\nsecond line")
            self.assertEqual(entries["R-C-007"]["title"], "Pipe | title")
            self.assertEqual(entries["R-C-001"]["last_confirmed"], "2026-09-01")  # the ledger was rewritten after signing
            self.assertEqual(entries["R-C-001"]["boundary"], "Nothing else is in scope.")

    def test_json_through_cli(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out, err = _run_in(fx.root, ["catalog", "--format", "json", "--book", "flows"])
            self.assertEqual(code, 0, err)
            self.assertEqual([e["id"] for e in json.loads(out)["entries"]],
                             ["R-C-004", "R-C-005", "R-C-006", "R-C-007"])


class TestCatalogCliErrors(unittest.TestCase):
    def test_missing_ledger_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.md_path.unlink()
            code, out, err = _run_in(fx.root, ["catalog"])
            self.assertEqual(code, 2)
            self.assertTrue(err.startswith("❌ "), err)
            self.assertNotIn("Traceback", err)
            self.assertEqual(len(err.splitlines()), 1)


FENCED = """### R-B-001 Before any heading

**Current rule**
x.

**Boundary**
An embedded example:

```markdown
## Not a book
# Not a title either
```

**Anchors**
- `pkg/mod.py::f`

**Last confirmed**
2026-09-01

### R-B-002 Still before any heading

**Current rule**
y.

**Boundary**
z.

**Anchors**
- `pkg/mod.py::f`

**Last confirmed**
2026-09-01

#   Ledger title

### R-B-003 Under the title

**Current rule**
y.

**Boundary**
z.

**Anchors**
- `pkg/mod.py::f`

**Last confirmed**
2026-09-01

## Book two ##

```
## Fenced, between entries
```

### R-B-004 In book two

**Current rule**
y.

**Boundary**
z.

**Anchors**
- `pkg/mod.py::f`

**Last confirmed**
2026-09-01
"""


class TestEntryBooks(unittest.TestCase):
    def test_fenced_headings_ignored_and_no_book_is_empty(self):
        books = L.entry_books(FENCED)
        self.assertEqual(books, {
            "R-B-001": "",
            "R-B-002": "",
            "R-B-003": "Ledger title",
            "R-B-004": "Book two ##",
        })

    def test_same_ids_as_parse_ledger(self):
        self.assertEqual(list(L.entry_books(FENCED)), list(L.parse_ledger(FENCED)))


if __name__ == "__main__":
    unittest.main()
