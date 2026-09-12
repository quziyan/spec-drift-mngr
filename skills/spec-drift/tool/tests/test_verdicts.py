"""Tests for verdicts."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_verdicts
from tests.test_check import Fixture

MD = """# Pilot ledger

### R-T-001 Example rule

**Current rule**
f always returns 1.

**Boundary**
Nothing else is in scope.

**Anchors**
- `pkg/mod.py::f`

**Last confirmed**
2026-09-04
"""

CODE = "def f():\n    return 1\n"
HEAD = "## `pkg/mod.py::f` (lines 1-2, items: 1)\n\n| # | Category | Line | Source | Verdict | Reason |\n|---|---|---|---|---|---|\n"


def grade(verdict: str, reason: str, books=None, source: str = "`return 1`") -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        fx = Fixture(Path(d), md=MD, code=CODE)
        path = Path(d) / "verdicts.md"
        path.write_text(HEAD + f"| 1 | ② return | 2 | {source} | {verdict} | {reason} |\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmd_verdicts.run(fx.ctx, [str(path)], books)
        return code, buf.getvalue()


class TestVerdicts(unittest.TestCase):
    def test_verbatim_quote_with_existing_entry_passes(self):
        code, out = grade("① R-T-001", "the entry says “f always returns 1.”")
        self.assertEqual(code, 0, out)

    def test_entry_id_alone_passes(self):
        self.assertEqual(grade("asserted by entry R-T-001", "")[0], 0)

    def test_quote_not_in_ledger_fails(self):
        code, out = grade("① R-T-001", "“f returns one on Sundays”")
        self.assertEqual(code, 1)
        self.assertIn("[① quote not in ledger]", out)

    def test_cjk_quote_is_checked_too(self):
        code, out = grade("① R-T-001", "\u53f0\u8d26\u5199\u300cf \u5728\u5468\u65e5\u8fd4\u56de 1\u300d")
        self.assertEqual(code, 1)
        self.assertIn("[① quote not in ledger]", out)

    def test_nonexistent_entry_fails(self):
        code, out = grade("① R-T-999", "")
        self.assertEqual(code, 1)
        self.assertIn("[① no entry]", out)

    def test_other_book_needs_an_id_or_a_declared_book(self):
        code, out = grade("② belongs to another book, no entry this round", "the billing side owns it")
        self.assertEqual(code, 1)
        self.assertIn("[② no book]", out)
        self.assertEqual(grade("② belongs to another book, no entry this round",
                               "the billing book owns it", books=["billing book"])[0], 0)

    def test_no_business_meaning_from_silence_fails(self):
        for reason in ("the ledger does not say anything about it", "\u53f0\u8d26\u6ca1\u5199\u8fd9\u4e2a"):
            code, out = grade("③ no business meaning (purely technical)", reason)
            self.assertEqual(code, 1, reason)
            self.assertIn("[③ from silence]", out)

    def test_no_business_meaning_with_a_real_reason_passes(self):
        self.assertEqual(grade("③ no business meaning (purely technical)",
                               "a log line; changing it changes nothing stored or shown")[0], 0)

    def test_gap_without_draft_assertion_fails(self):
        code, out = grade("④ gap: no entry asserts this yet", "")
        self.assertEqual(code, 1)
        self.assertIn("[④ no reason]", out)

    def test_row_without_verdict_or_with_unknown_verdict_fails(self):
        self.assertIn("[no verdict]", grade("", "")[1])
        self.assertIn("[unknown verdict]", grade("maybe", "hmm")[1])

    def test_escaped_pipe_in_source_does_not_shift_columns(self):
        self.assertEqual(grade("① R-T-001", "", source="`a \\| b`")[0], 0)

    def test_missing_file_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=MD, code=CODE)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_verdicts.run(fx.ctx, [str(Path(d) / "nope.md")]), 2)


if __name__ == "__main__":
    unittest.main()
