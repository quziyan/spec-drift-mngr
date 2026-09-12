"""Tests for impact."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_impact
from tests.test_check import MD, Fixture

CODE = "def f():\n    return 1\n\n\ndef caller():\n    return f()\n"


def build(tmp: Path) -> Fixture:
    fx = Fixture(tmp, md=MD, code=CODE)
    (tmp / "backend" / "tests").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "tests" / "test_mod.py").write_text(
        "from pkg.mod import f\n\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8"
    )
    fx.seed_lock()
    return fx


def run(fx, target) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert cmd_impact.run(fx.ctx, target) == 0
    return buf.getvalue()


class TestImpact(unittest.TestCase):
    def test_reports_caller_as_symbol_not_line(self):
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIn("pkg/mod.py::caller", out)

    def test_searches_tests_directory_too(self):
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIn("tests/test_mod.py::test_f", out)

    def test_hit_outside_any_symbol_maps_to_module(self):
        """`from pkg.mod import f` lies outside every symbol span → ::<module>."""
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIn("tests/test_mod.py::<module>", out)

    def test_never_prints_file_colon_line(self):
        """file:line must never be printed: it is not the same unit as the prediction set."""
        import re
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIsNone(re.search(r"\.py:\d+", out), out)

    def test_false_positive_warning_always_printed(self):
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIn("may contain false positives", out)

    def test_entry_id_reports_sibling_anchors(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            md = MD.replace("- `pkg/mod.py::f`\n", "- `pkg/mod.py::f`\n- `pkg/mod.py::caller`\n")
            fx = Fixture(tmp, md=md, code=CODE)
            fx.seed_lock(anchors=("pkg/mod.py::f", "pkg/mod.py::caller"))
            out = run(fx, "R-T-001")
            self.assertIn("sibling anchors", out)
            self.assertIn("pkg/mod.py::caller", out)

    def test_word_boundary_avoids_substring_match(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = Fixture(tmp, md=MD, code="def f():\n    return 1\n\n\ndef g():\n    return fx_helper\n")
            fx.seed_lock()
            out = run(fx, "pkg/mod.py::f")
            self.assertNotIn("pkg/mod.py::g", out)

    def test_sibling_anchors_read_from_md_not_lock(self):
        """While an entry is not synced yet (S1, absent from the lock), the sibling anchors of a symbol must still be readable from the markdown.

        `caller` deliberately does not reference `f` — so if "pkg/mod.py::caller" shows up in
        the output it can only come from the sibling-anchor section, not from the
        text-matching reference search (which keeps the evidence for the two paths apart).
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            md = MD.replace("- `pkg/mod.py::f`\n", "- `pkg/mod.py::f`\n- `pkg/mod.py::caller`\n")
            code = "def f():\n    return 1\n\n\ndef caller():\n    return 2\n"
            fx = Fixture(tmp, md=md, code=code)
            # fx.seed_lock() is deliberately not called — no lock file, so the entry is in S1.
            out = run(fx, "pkg/mod.py::f")
            self.assertIn("sibling anchors", out)
            self.assertIn("pkg/mod.py::caller", out)

    def test_reports_files_skipped_due_to_parse_errors(self):
        """Files skipped because they failed to parse must be printed as a summary, never silently."""
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            (fx.root / "backend" / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")
            out = run(fx, "pkg/mod.py::f")
            self.assertIn("broken.py", out)
            self.assertIn("excluded", out)

    def test_false_positive_note_also_discloses_false_negatives(self):
        """The false-positive note must disclose the false-negative boundary too (alias calls, getattr and other indirect references get missed)."""
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIn("may contain false positives", out)   # the wording of the note itself must survive
            self.assertIn("filtering by hand", out)
            self.assertIn("getattr", out)

    def test_module_target_skips_text_search(self):
        """With <module> as the target, do not return an empty result silently; say that this kind of query does not apply."""
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            out = run(fx, "pkg/mod.py::<module>")
            self.assertIn("<module>", out)
            self.assertIn("does not apply", out)

    def test_unresolvable_target_warns_but_still_searches_and_returns_zero(self):
        """When the target is neither an entry ID nor a resolvable symbol, say so explicitly instead of silently returning nothing."""
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            out = run(fx, "pkg/mod.py::nonexistent")   # run() already asserts the exit code is 0
            self.assertIn("neither a ledger entry ID", out)


class TestBackslashAnchorStillExcludesItsDefinition(unittest.TestCase):
    def test_definition_site_not_reported_for_backslash_anchor(self):
        """Hits are keyed by the POSIX relpath; an anchor written with a backslash
        separator must still match its own definition site and be excluded."""
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            posix_sites, _ = cmd_impact._references(fx.ctx, "pkg/mod.py::f")
            backslash_sites, _ = cmd_impact._references(fx.ctx, "pkg\\mod.py::f")
            self.assertEqual(backslash_sites, posix_sites)
            self.assertNotIn("pkg/mod.py::f", backslash_sites)


if __name__ == "__main__":
    unittest.main()


class TestImpactInvolvedAndVendor(unittest.TestCase):
    def test_lists_every_entry_that_anchors_the_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::f")
            self.assertIn("[entries involved]", out)
            self.assertIn("R-T-001 (via pkg/mod.py::f)", out)

    def test_unanchored_symbol_says_no_entry(self):
        with tempfile.TemporaryDirectory() as d:
            out = run(build(Path(d)), "pkg/mod.py::caller")
            self.assertIn("(none — no entry anchors it)", out)

    def test_node_modules_is_left_out_of_the_search_domain(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            vendor = Path(d) / "backend" / "node_modules" / "tool"
            vendor.mkdir(parents=True)
            (vendor / "helper.py").write_text("from pkg.mod import f\n\n\ndef use():\n    return f()\n", encoding="utf-8")
            out = run(fx, "pkg/mod.py::f")
            self.assertNotIn("node_modules/tool/helper.py", out)
            self.assertIn("pkg/mod.py::caller", out)
