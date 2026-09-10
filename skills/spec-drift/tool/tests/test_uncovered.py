"""Tests for uncovered."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_uncovered
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

CODE = (
    "CONST = 1\n\n\n"
    "def f():\n    return 1\n\n\n"
    "def g():\n    return 2\n\n\n"
    "class Foo:\n    def bar(self):\n        return 3\n"
)


def build(tmp: Path) -> Fixture:
    fx = Fixture(tmp, md=MD, code=CODE)
    (tmp / "backend" / "tests").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "tests" / "test_mod.py").write_text(
        "def test_f():\n    pass\n\n\ndef test_other():\n    pass\n", encoding="utf-8"
    )
    return fx


class TestUncovered(unittest.TestCase):
    def test_reports_unanchored_symbols(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(cmd_uncovered.run(fx.ctx), 0)
            out = buf.getvalue()
            for name in ("pkg/mod.py::g", "pkg/mod.py::CONST",
                         "pkg/mod.py::Foo", "pkg/mod.py::Foo::bar"):
                self.assertIn(name, out)

    def test_anchored_symbol_not_reported(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_uncovered.run(fx.ctx)
            self.assertNotIn("pkg/mod.py::f\n", buf.getvalue())

    def test_tests_dir_excluded_from_hot_zone(self):
        """The hot zone excludes tests/, otherwise every other test function in that file would be reported."""
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            self.assertEqual(cmd_uncovered.hot_zone(fx.ctx), ["pkg/mod.py"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_uncovered.run(fx.ctx)
            self.assertNotIn("test_other", buf.getvalue())

    def test_module_pseudo_symbol_not_reported(self):
        with tempfile.TemporaryDirectory() as d:
            fx = build(Path(d))
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_uncovered.run(fx.ctx)
            self.assertNotIn("<module>", buf.getvalue())


class TestNestedTestsDirExcluded(unittest.TestCase):
    """A `tests` directory is excluded at any depth, not only directly under code_root.

    A code_root that holds several services (`svc/tests/...`) is the common layout of
    a real project; before this the prefix match only caught `tests/` at the top and
    the banner still claimed the exclusion had happened.
    """

    MD_NESTED = """# Pilot ledger

### R-T-001 Example rule

**Current rule**
f always returns 1.

**Boundary**
Nothing else is in scope.

**Anchors**
- `svc/mod.py::f`
- `svc/tests/test_mod.py::test_f`

**Last confirmed**
2026-09-04
"""

    def _build(self, tmp: Path) -> Fixture:
        fx = Fixture(tmp, md=self.MD_NESTED, code=CODE)
        (tmp / "backend" / "svc" / "tests").mkdir(parents=True)
        (tmp / "backend" / "svc" / "mod.py").write_text(CODE, encoding="utf-8")
        (tmp / "backend" / "svc" / "tests" / "test_mod.py").write_text(
            "def test_f():\n    pass\n\n\ndef test_other():\n    pass\n", encoding="utf-8"
        )
        (tmp / "backend" / "svc" / "tests" / "conftest.py").write_text(
            "def db():\n    pass\n", encoding="utf-8"
        )
        return fx

    def test_anchor_derived_nested_tests_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            fx = self._build(Path(d))
            self.assertEqual(cmd_uncovered.hot_zone(fx.ctx), ["svc/mod.py"])

    def test_configured_hot_zone_dir_drops_nested_tests(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = self._build(tmp)
            cfg = tmp / ".spec-drift.json"
            cfg.write_text(cfg.read_text(encoding="utf-8").replace(
                '"owner"', '"hot_zone": ["svc"], "owner"'), encoding="utf-8")
            self.assertEqual(cmd_uncovered.hot_zone(fx.ctx), ["svc/mod.py"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_uncovered.run(fx.ctx)
            out = buf.getvalue()
            self.assertNotIn("conftest", out)
            self.assertNotIn("test_other", out)
            self.assertIn("any `tests/` directory excluded", out)
