"""Tests for inventory (folded in from a one-off stock-take script)."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cli
import cmd_inventory
from tests.test_check import Fixture

MD = """# Pilot ledger

### R-T-001 Example rule

**Current rule**
f always returns 1.

**Boundary**
Nothing else is in scope.

**Anchors**
- `pkg/mod.py::f`
- `tests/test_mod.py::test_f`

**Last confirmed**
2026-09-04
"""

# One symbol covering all eight kinds (classified line by line in the comment below; the
# counts asserted in the tests correspond to it one for one):
#   ① branch 5: the if test, the else, the ternary, the match case, the second if test (no else)
#   ② return 4: the return statement itself + two BoolOp operands + one Compare comparison
#   ③ raise 1
#   ④ cross-module call 1: os.getcwd() (os is imported)
#   ⑤ field write 2: a.x = 1 (Attribute), d["k"] = 1 (Subscript)
#   ⑥ class member 0: f is not a class
#   ⑦ name assignment 3: z = the ternary, y = 1, d = {} (Name targets, a ternary RHS included)
#   ⑧ except 1: catching ValueError
CODE = """import os


def f(a, b, cond):
    if cond:
        pass
    else:
        pass
    z = 1 if cond else 2
    match cond:
        case 1:
            pass
    y = 1
    a.x = 1
    d = {}
    d["k"] = 1
    os.getcwd()
    try:
        pass
    except ValueError:
        pass
    if not cond:
        raise ValueError("bad")
    return a and (a > b)


class Foo:
    X = 1
    Y = 2

    def bar(self):
        return 1
"""


def build(tmp: Path) -> Fixture:
    fx = Fixture(tmp, md=MD, code=CODE)
    (tmp / "backend" / "tests").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "tests" / "test_mod.py").write_text(
        "def test_f():\n    pass\n", encoding="utf-8"
    )
    return fx


def run_inventory(fx, **kwargs) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_inventory.run(fx.ctx, **kwargs)
    return code, buf.getvalue()


class TestEightCategories(unittest.TestCase):
    """Each of the eight kinds is hit at least once, and the counts match what is expected."""

    def test_symbol_mode_counts_all_eight_categories(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx, symbol="pkg/mod.py::f")
            self.assertEqual(code, 0)
            self.assertIn("① branch 5", out)
            self.assertIn("② return 4", out)
            self.assertIn("③ raise 1", out)
            self.assertIn("④ cross-module call 1", out)
            self.assertIn("⑤ field write 2", out)
            self.assertIn("⑥ class member 0", out)  # f is not a class
            self.assertIn("⑦ name assignment 3", out)
            self.assertIn("⑧ except 1", out)
            self.assertIn("items: 17", out)

    def test_return_counts_boolop_and_compare_operands(self):
        """② counts operands and comparisons, not the number of return statements."""
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out = run_inventory(fx, symbol="pkg/mod.py::f")
            self.assertIn("operand", out)
            self.assertIn("comparison", out)

    def test_class_member_category_on_class_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out = run_inventory(fx, symbol="pkg/mod.py::Foo")
            self.assertIn("⑥ class member 2", out)

    def test_class_method_symbol_uses_double_colon(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx, symbol="pkg/mod.py::Foo::bar")
            self.assertEqual(code, 0)
            self.assertIn("pkg/mod.py::Foo::bar", out)


class TestOutputShape(unittest.TestCase):
    def test_verdict_and_reason_columns_blank(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out = run_inventory(fx, symbol="pkg/mod.py::f")
            # A data row looks like "| 1 | ① branch | 5 | `if cond:` | | |" (verdict and reason left blank)
            self.assertRegex(out, r"\|\s*\d+\s*\|[^\n]+\|\s*\|\s*\|")

    def test_grand_total_section_present(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out = run_inventory(fx, symbol="pkg/mod.py::f")
            self.assertIn("## Totals", out)

    def test_verdict_kinds_and_known_limitations_present(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            _code, out = run_inventory(fx, symbol="pkg/mod.py::f")
            self.assertIn("asserted by entry X", out)
            self.assertIn("belongs to another book, no entry this round", out)
            self.assertIn("no business meaning (purely technical)", out)
            self.assertIn("Known limits", out)


class TestFileMode(unittest.TestCase):
    def test_enumerates_all_top_level_and_methods_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx, file="pkg/mod.py")
            self.assertEqual(code, 0)
            self.assertIn("pkg/mod.py::f", out)
            self.assertIn("pkg/mod.py::Foo", out)
            self.assertIn("pkg/mod.py::Foo::bar", out)
            self.assertLess(out.index("pkg/mod.py::f"), out.index("pkg/mod.py::Foo"))

    def test_missing_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx, file="pkg/nope.py")
            self.assertEqual(code, 0)
            self.assertIn("does not exist", out)


class TestNoArgsUsesLedgerAnchors(unittest.TestCase):
    def test_scans_ledger_anchors_excluding_tests(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx)
            self.assertEqual(code, 0)
            self.assertIn("pkg/mod.py::f", out)
            self.assertNotIn("tests/test_mod.py::test_f", out)

    def test_duplicate_anchor_across_entries_rendered_once(self):
        md = MD.replace(
            "**Last confirmed**\n2026-09-04\n",
            "**Last confirmed**\n2026-09-04\n\n"
            "### R-T-002 A second entry anchoring f as well\n\n"
            "**Current rule**\ng always returns 1 too.\n\n**Boundary**\nNothing else is in scope.\n\n"
            "**Anchors**\n- `pkg/mod.py::f`\n\n**Last confirmed**\n2026-09-04\n",
        )
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            fx.md_path.write_text(md, encoding="utf-8")
            _code, out = run_inventory(fx)
            self.assertEqual(out.count("## `pkg/mod.py::f`"), 1)


class TestBadInputStillExitsZero(unittest.TestCase):
    """By contract inventory is a query command, not a gate: the exit code is always 0."""

    def test_unresolvable_symbol_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx, symbol="pkg/mod.py::nonexistent")
            self.assertEqual(code, 0)
            self.assertIn("no such symbol", out)

    def test_module_pseudo_symbol_is_rejected_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            code, out = run_inventory(fx, symbol="pkg/mod.py::<module>")
            self.assertEqual(code, 0)
            self.assertIn("pseudo-symbol", out)


class TestChainedAssignmentCountsPerTarget(unittest.TestCase):
    """⑤ field writes must be counted per target, the same criterion the one-off script used —

    a chained assignment `a.x = b.y = 1` has two Attribute targets and counts 2, not 1.
    """

    MD2 = MD.replace("- `pkg/mod.py::f`\n", "- `pkg/mod.py::chained`\n")
    CODE2 = "class C:\n    def f(self, a, b):\n        a.x = b.y = 1\n"

    def test_chained_attribute_assignment_counts_two(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            fx.md_path.write_text(self.MD2, encoding="utf-8")
            (fx.root / "backend" / "pkg" / "mod.py").write_text(self.CODE2, encoding="utf-8")
            _code, out = run_inventory(fx, symbol="pkg/mod.py::C::f")
            self.assertIn("⑤ field write 2", out)


class TestClassAnchorDoesNotDoubleCountMethodBody(unittest.TestCase):
    """When a class anchor and its method anchors are enumerated separately, the class-level total must not include the method body twice.

    The synthetic case (the one a review used to reproduce it):
        class C:
            x = 1
            def f(self):
                self.z = 3
                if True: pass

    Taking stock of `C` (the class as a whole) should cover the class body level only —
    `x = 1` (⑥) — and should not descend into the body of `f` to count `self.z = 3` (⑤) or
    `if True` (①); those are enumerated separately under `C::f`.
    """

    CODE3 = (
        "class C:\n"
        "    x = 1\n"
        "    def f(self):\n"
        "        self.z = 3\n"
        "        if True:\n"
        "            pass\n"
    )
    MD3 = MD.replace("- `pkg/mod.py::f`\n", "- `pkg/mod.py::C`\n")

    def test_class_symbol_excludes_method_body_items(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            fx.md_path.write_text(self.MD3, encoding="utf-8")
            (fx.root / "backend" / "pkg" / "mod.py").write_text(self.CODE3, encoding="utf-8")
            _code, out = run_inventory(fx, symbol="pkg/mod.py::C")
            self.assertIn("⑥ class member 1", out)
            self.assertIn("⑤ field write 0", out)
            self.assertIn("① branch 0", out)
            self.assertIn("items: 1", out)
            self.assertIn("The methods of this class are enumerated on their own; this table does not cover method bodies", out)
            self.assertIn("pkg/mod.py::C::f", out)

    def test_method_symbol_still_reports_its_own_body(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            fx.md_path.write_text(self.MD3, encoding="utf-8")
            (fx.root / "backend" / "pkg" / "mod.py").write_text(self.CODE3, encoding="utf-8")
            _code, out = run_inventory(fx, symbol="pkg/mod.py::C::f")
            self.assertIn("⑤ field write 1", out)
            self.assertIn("① branch 1", out)


class TestCliWiring(unittest.TestCase):
    def test_symbol_and_file_are_mutually_exclusive(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["inventory", "--symbol", "a.py::f", "--file", "a.py"])

    def test_no_flags_parses_to_none(self):
        parser = cli.build_parser()
        args = parser.parse_args(["inventory"])
        self.assertIsNone(args.symbol)
        self.assertIsNone(args.file)

    def test_main_dispatches_to_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            import os
            old = os.getcwd()
            os.chdir(fx.root)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.main(["inventory", "--symbol", "pkg/mod.py::f"])
                self.assertEqual(code, 0)
                self.assertIn("pkg/mod.py::f", buf.getvalue())
            finally:
                os.chdir(old)



class TestLedgerAnchorsSkipNestedTests(unittest.TestCase):
    def test_nested_tests_anchor_is_not_inventoried(self):
        md = MD.replace("- `tests/test_mod.py::test_f`", "- `pkg/tests/test_mod.py::test_f`")
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = Fixture(tmp, md=md, code=CODE)
            (tmp / "backend" / "pkg" / "tests").mkdir(parents=True, exist_ok=True)
            (tmp / "backend" / "pkg" / "tests" / "test_mod.py").write_text(
                "def test_f():\n    pass\n", encoding="utf-8"
            )
            self.assertEqual(cmd_inventory._ledger_anchors(fx.ctx), ["pkg/mod.py::f"])


if __name__ == "__main__":
    unittest.main()
