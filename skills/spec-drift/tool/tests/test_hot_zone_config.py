"""Tests for the hot_zone configuration (making the hot zone configurable).

The default behaviour, with no hot_zone configured, must be byte-for-byte what it was
before the hot zone became configurable — that is already covered by test_uncovered.py, whose
Fixture configures no hot_zone. This file only tests the newly added config path itself.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_uncovered
import repo
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

CODE = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"


def build_with_hot_zone(tmp: Path, hot_zone) -> Fixture:
    """Reuse the Fixture from test_check to build the base repository, then add a hot_zone field to .spec-drift.json."""
    fx = Fixture(tmp, md=MD, code=CODE)
    cfg_path = tmp / ".spec-drift.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["hot_zone"] = hot_zone
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    fx.ctx = repo.build_ctx(tmp)
    return fx


def run_uncovered(ctx) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_uncovered.run(ctx)
    return code, buf.getvalue()


class TestConfiguredDirectoryIsUnioned(unittest.TestCase):
    def test_directory_entry_adds_its_py_files_to_hot_zone(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "backend" / "extra").mkdir(parents=True)
            (tmp / "backend" / "extra" / "other.py").write_text(
                "def h():\n    return 3\n", encoding="utf-8"
            )
            fx = build_with_hot_zone(tmp, ["extra"])
            self.assertEqual(
                cmd_uncovered.hot_zone(fx.ctx), ["extra/other.py", "pkg/mod.py"]
            )

    def test_file_entry_is_included(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "backend" / "extra").mkdir(parents=True)
            (tmp / "backend" / "extra" / "other.py").write_text("X = 1\n", encoding="utf-8")
            fx = build_with_hot_zone(tmp, ["extra/other.py"])
            self.assertIn("extra/other.py", cmd_uncovered.hot_zone(fx.ctx))

    def test_configured_and_anchor_derived_is_a_union_not_a_replacement(self):
        """Files brought in by configuration must not crowd out the anchor-derived ones: the two are unioned."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "backend" / "extra").mkdir(parents=True)
            (tmp / "backend" / "extra" / "other.py").write_text("X = 1\n", encoding="utf-8")
            fx = build_with_hot_zone(tmp, ["extra"])
            zone = cmd_uncovered.hot_zone(fx.ctx)
            self.assertIn("pkg/mod.py", zone)     # comes from anchor derivation
            self.assertIn("extra/other.py", zone)  # comes from the configuration


class TestTestsDirExclusionAppliesToConfiguredEntriesToo(unittest.TestCase):
    def test_configured_tests_subpath_is_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "backend" / "tests").mkdir(parents=True)
            (tmp / "backend" / "tests" / "test_extra.py").write_text(
                "def test_x():\n    pass\n", encoding="utf-8"
            )
            fx = build_with_hot_zone(tmp, ["tests"])
            self.assertEqual(cmd_uncovered.hot_zone(fx.ctx), ["pkg/mod.py"])


class TestMissingConfiguredEntryWarnsAndSkips(unittest.TestCase):
    def test_nonexistent_entry_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = build_with_hot_zone(tmp, ["does/not/exist"])
            code, out = run_uncovered(fx.ctx)
            self.assertEqual(code, 0)
            self.assertIn("does not exist, skipped", out)


class TestNonPyFileEntrySkipped(unittest.TestCase):
    def test_non_py_file_warns_and_skips(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = build_with_hot_zone(tmp, ["notes.txt"])
            (tmp / "backend" / "notes.txt").write_text("n\n", encoding="utf-8")
            code, out = run_uncovered(fx.ctx)
            self.assertEqual(code, 0)
            self.assertIn("is not a .py file, skipped", out)


class TestBadHotZoneType(unittest.TestCase):
    def test_non_list_hot_zone_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = build_with_hot_zone(tmp, "extra")  # should be a list, not a string
            with self.assertRaises(ValueError):
                cmd_uncovered.hot_zone(fx.ctx)


class TestOriginLabelingOnlyWhenConfigured(unittest.TestCase):
    def test_no_hot_zone_config_prints_no_origin_label(self):
        """The default path: the output format must be byte-for-byte what it was before the hot zone became configurable, with no origin annotation."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=MD, code=CODE)
            code, out = run_uncovered(fx.ctx)
            self.assertEqual(code, 0)
            self.assertIn("Hot zone (derived from the ledger anchors, tests/ excluded):", out)
            self.assertNotIn("(origin: ", out)

    def test_configured_hot_zone_prints_origin_label_for_every_file(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "backend" / "extra").mkdir(parents=True)
            (tmp / "backend" / "extra" / "other.py").write_text("X = 1\n", encoding="utf-8")
            fx = build_with_hot_zone(tmp, ["extra"])
            code, out = run_uncovered(fx.ctx)
            self.assertEqual(code, 0)
            self.assertIn("pkg/mod.py (origin: anchor-derived)", out)
            self.assertIn("extra/other.py (origin: configured)", out)


if __name__ == "__main__":
    unittest.main()
