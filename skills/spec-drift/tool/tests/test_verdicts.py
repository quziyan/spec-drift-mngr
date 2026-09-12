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


def grade_text(text: str, books=None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        fx = Fixture(Path(d), md=MD, code=CODE)
        path = Path(d) / "verdicts.md"
        path.write_text(text, encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cmd_verdicts.run(fx.ctx, [str(path)], books)
        return code, buf.getvalue()


class TestVerdictsAfterReview(unittest.TestCase):
    def test_whole_inventory_output_filled_correctly_passes(self):
        import cmd_inventory
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=MD, code=CODE)
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_inventory.run(fx.ctx, symbol=None, file=None)
            filled = "\n".join(
                line[: -len("| | |")] + "| ① R-T-001 | |" if line.endswith("| | |") else line
                for line in buf.getvalue().splitlines()
            )
            filled += "\n\n```\n| 9 | ① branch | 1 | `x` | maybe | example in a fence |\n```\n"
            path = Path(d) / "v.md"
            path.write_text(filled, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cmd_verdicts.run(fx.ctx, [str(path)]), 0, out.getvalue())

    def test_entry_id_is_matched_whole(self):
        code, out = grade("① R-T-0011", "")
        self.assertEqual(code, 1)
        self.assertIn("[① no entry]", out)

    def test_short_fabricated_quote_fails(self):
        self.assertIn("[① quote not in ledger]", grade("① R-T-001", "“fake”")[1])

    def test_quotes_inside_code_spans_are_not_ledger_quotes(self):
        self.assertEqual(grade("① R-T-001", 'see `raise ValueError("bad input")`')[0], 0)

    def test_quote_in_the_verdict_cell_is_checked(self):
        self.assertIn("[① quote not in ledger]", grade("① R-T-001 “f returns 2”", "")[1])

    def test_verdict_prefix_needs_a_word_boundary(self):
        self.assertIn("[unknown verdict]", grade("gapless", "x")[1])

    def test_row_with_wrong_cell_count_is_reported(self):
        code, out = grade_text(HEAD + "| 1 | ② return | 2 | ① R-T-001 |\n")
        self.assertEqual(code, 1)
        self.assertIn("[malformed row]", out)

    def test_compact_empty_cells_are_kept(self):
        code, out = grade_text(HEAD + "| 1 | ② return | 2 | `return 1` |||\n")
        self.assertIn("[no verdict]", out)
        self.assertNotIn("[malformed row]", out)

    def test_file_without_a_verdict_table_fails(self):
        code, out = grade_text("just prose\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertEqual(code, 1)
        self.assertIn("[no table]", out)

    def test_unreadable_file_exits_2(self):
        import os
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read any file")
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=MD, code=CODE)
            path = Path(d) / "locked.md"
            path.write_text(HEAD, encoding="utf-8")
            os.chmod(path, 0)
            try:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_verdicts.run(fx.ctx, [str(path)]), 2)
            finally:
                os.chmod(path, 0o600)


VALID = "| 1 | ② return | 2 | `return 1` | ① R-T-001 | |\n"
EMPTY = "| 1 | ② return | 2 | `return 1` |  |  |\n"


class TestVerdictsSecondReview(unittest.TestCase):
    def test_tilde_fence_is_skipped_too(self):
        code, out = grade_text("~~~markdown\n" + HEAD + VALID + "~~~\n")
        self.assertEqual(code, 1)
        self.assertIn("[no table]", out)

    def test_fence_closes_only_on_its_own_marker(self):
        code, out = grade_text(HEAD + VALID + "\n````markdown\n```\n````\n\n" + HEAD + EMPTY)
        self.assertEqual(code, 1)
        self.assertIn("[no verdict]", out)

    def test_separator_without_trailing_pipe_still_opens_the_table(self):
        second = "| # | Category | Line | Source | Verdict | Reason |\n|---|---|---|---|---|---\n"
        code, out = grade_text(HEAD + VALID + "\n" + second + EMPTY)
        self.assertEqual(code, 1)
        self.assertIn("[no verdict]", out)

    def test_bad_separator_under_the_header_is_reported(self):
        code, out = grade_text("| # | Category | Line | Source | Verdict | Reason |\n|---|\n" + VALID)
        self.assertEqual(code, 1)
        self.assertIn("[malformed table]", out)

    def test_row_not_starting_with_a_pipe_is_reported(self):
        code, out = grade_text(HEAD + VALID + "2 | ② return | 3 | `x` |  |  |\n")
        self.assertEqual(code, 1)
        self.assertIn("[malformed row]", out)

    def test_double_backtick_code_span_is_not_a_quote(self):
        self.assertEqual(grade("① R-T-001", '``raise ValueError("bad input")``')[0], 0)

    def test_code_spans_do_not_pair_across_cells(self):
        self.assertIn("[① quote not in ledger]", grade("① R-T-001 `", "“fake” `")[1])

    def test_cjk_text_may_touch_the_entry_id(self):
        self.assertEqual(grade("① \u6761\u76eeR-T-001", "")[0], 0)
        self.assertEqual(grade("② belongs to another book, no entry this round", "\u7531R-T-001\u89c4\u5b9a")[0], 0)
        self.assertIn("[① no entry]", grade("① XR-T-001", "")[1])

    def test_quote_is_compared_with_whitespace_collapsed(self):
        self.assertEqual(grade("① R-T-001", "“f  always returns 1.”")[0], 0)
