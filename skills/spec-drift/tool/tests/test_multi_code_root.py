"""Tests for a multi-value code_root: the non-git half — read_source / check / impact / uncovered.

For the git half (the `changed` family) see tests/test_multi_code_root_changed.py.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_check
import cmd_impact
import cmd_uncovered
import repo


def build_two_root_ctx(tmp: Path, *, md: str, lock: dict | None = None) -> repo.Ctx:
    cfg = {
        "code_root": ["svc_a", "svc_b"],
        "ledger": "docs/ledger.md",
        "lock": "docs/drift-lock.json",
        "owner": "Alice",
        "assistant": "Bot",
    }
    (tmp / ".spec-drift.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp / "docs").mkdir(parents=True, exist_ok=True)
    (tmp / "docs" / "ledger.md").write_text(md, encoding="utf-8")
    if lock is not None:
        (tmp / "docs" / "drift-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return repo.build_ctx(tmp)


MD_TWO_ROOTS = """# Pilot ledger

### R-A-001 Rule on the A side

**Current rule**
f always returns 1.

**Boundary**
Nothing else is in scope.

**Anchors**
- `pkg/mod_a.py::f`

**Last confirmed**
2026-09-06

### R-B-001 Rule on the B side

**Current rule**
g always returns 2.

**Boundary**
Nothing else is in scope.

**Anchors**
- `pkg/mod_b.py::g`

**Last confirmed**
2026-09-06
"""


class TestReadSourceAcrossRoots(unittest.TestCase):
    def test_resolves_file_in_whichever_root_actually_has_it(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "svc_a" / "pkg").mkdir(parents=True)
            (tmp / "svc_b" / "pkg").mkdir(parents=True)
            (tmp / "svc_a" / "pkg" / "mod_a.py").write_text(
                "def f():\n    return 1\n", encoding="utf-8"
            )
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def g():\n    return 2\n", encoding="utf-8"
            )
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            self.assertIn("def f", repo.read_source(ctx, "pkg/mod_a.py"))
            self.assertIn("def g", repo.read_source(ctx, "pkg/mod_b.py"))
            self.assertIsNone(repo.read_source(ctx, "pkg/nope.py"))

    def test_current_fingerprint_works_for_anchors_in_either_root(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "svc_a" / "pkg").mkdir(parents=True)
            (tmp / "svc_b" / "pkg").mkdir(parents=True)
            (tmp / "svc_a" / "pkg" / "mod_a.py").write_text(
                "def f():\n    return 1\n", encoding="utf-8"
            )
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def g():\n    return 2\n", encoding="utf-8"
            )
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            self.assertIsNotNone(repo.current_fingerprint(ctx, "pkg/mod_a.py::f"))
            self.assertIsNotNone(repo.current_fingerprint(ctx, "pkg/mod_b.py::g"))


class TestCheckAcrossRoots(unittest.TestCase):
    def _seed_lock(self, tmp: Path, ctx: repo.Ctx) -> dict:
        import ledger as L
        entries = L.parse_ledger((tmp / "docs" / "ledger.md").read_text(encoding="utf-8"))
        lock = {}
        for entry_id, entry in entries.items():
            lock[entry_id] = {
                "assertion_sha": L.assertion_sha(entry),
                "anchors": {a: repo.current_fingerprint(ctx, a) for a in entry.anchors},
                "confirmed_at": "2026-09-06T10:00:00+08:00",
                "confirmed_by": "Alice",
                "note": "seed",
            }
        return lock

    def test_clean_ledger_across_two_roots_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "svc_a" / "pkg").mkdir(parents=True)
            (tmp / "svc_b" / "pkg").mkdir(parents=True)
            (tmp / "svc_a" / "pkg" / "mod_a.py").write_text(
                "def f():\n    return 1\n", encoding="utf-8"
            )
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def g():\n    return 2\n", encoding="utf-8"
            )
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            lock = self._seed_lock(tmp, ctx)
            (tmp / "docs" / "drift-lock.json").write_text(json.dumps(lock), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_check.run(ctx)
            self.assertEqual(code, 0, buf.getvalue())

    def test_drift_in_second_root_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "svc_a" / "pkg").mkdir(parents=True)
            (tmp / "svc_b" / "pkg").mkdir(parents=True)
            (tmp / "svc_a" / "pkg" / "mod_a.py").write_text(
                "def f():\n    return 1\n", encoding="utf-8"
            )
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def g():\n    return 2\n", encoding="utf-8"
            )
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            lock = self._seed_lock(tmp, ctx)
            (tmp / "docs" / "drift-lock.json").write_text(json.dumps(lock), encoding="utf-8")
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def g():\n    return 999\n", encoding="utf-8"
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_check.run(ctx)
            out = buf.getvalue()
            self.assertNotEqual(code, 0)
            self.assertIn("fingerprint drift", out)
            self.assertIn("pkg/mod_b.py::g", out)


class TestImpactAcrossRoots(unittest.TestCase):
    def test_search_domain_covers_both_roots(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "svc_a" / "pkg").mkdir(parents=True)
            (tmp / "svc_b" / "pkg").mkdir(parents=True)
            (tmp / "svc_a" / "pkg" / "mod_a.py").write_text(
                "def f():\n    return 1\n", encoding="utf-8"
            )
            # Root B references a symbol name defined in root A: the text-matching impact
            # scan should hit it across roots.
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def caller():\n    return f()\n", encoding="utf-8"
            )
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_impact.run(ctx, "pkg/mod_a.py::f")
            out = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("pkg/mod_b.py::caller", out)


class TestUncoveredAcrossRoots(unittest.TestCase):
    def test_hot_zone_spans_both_roots_via_anchors(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "svc_a" / "pkg").mkdir(parents=True)
            (tmp / "svc_b" / "pkg").mkdir(parents=True)
            (tmp / "svc_a" / "pkg" / "mod_a.py").write_text(
                "def f():\n    return 1\n\n\ndef unanchored_a():\n    return 9\n",
                encoding="utf-8",
            )
            (tmp / "svc_b" / "pkg" / "mod_b.py").write_text(
                "def g():\n    return 2\n\n\ndef unanchored_b():\n    return 8\n",
                encoding="utf-8",
            )
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            self.assertEqual(
                cmd_uncovered.hot_zone(ctx), ["pkg/mod_a.py", "pkg/mod_b.py"]
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_uncovered.run(ctx)
            out = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("pkg/mod_a.py::unanchored_a", out)
            self.assertIn("pkg/mod_b.py::unanchored_b", out)



class TestUniquenessSkipsExcludedFiles(unittest.TestCase):
    """Files outside the business view must not veto the config.

    `tests/` directories are excluded from every other command, and every Python
    package root carries an `__init__.py`, so neither may count as a relative-path
    collision between two code roots — otherwise no real multi-package project could
    ever configure a multi-value code_root.
    """

    def _two_roots(self, tmp: Path) -> None:
        for root in ("svc_a", "svc_b"):
            (tmp / root / "pkg").mkdir(parents=True)
            (tmp / root / "tests").mkdir(parents=True)
            (tmp / root / "pkg" / "sub" / "tests").mkdir(parents=True)
            (tmp / root / "__init__.py").write_text("", encoding="utf-8")
            (tmp / root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (tmp / root / "tests" / "conftest.py").write_text("def db():\n    pass\n", encoding="utf-8")
            (tmp / root / "pkg" / "sub" / "tests" / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        (tmp / "svc_a" / "pkg" / "mod_a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (tmp / "svc_b" / "pkg" / "mod_b.py").write_text("def g():\n    return 2\n", encoding="utf-8")

    def test_shared_tests_dir_and_init_py_are_not_a_collision(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._two_roots(tmp)
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            self.assertEqual(len(ctx.code_roots), 2)

    def test_impact_keeps_reference_sites_in_both_shared_tests_files(self):
        """A file exempt from the uniqueness check must not be dropped by the scan of impact."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._two_roots(tmp)
            (tmp / "svc_a" / "tests" / "conftest.py").write_text("from pkg.mod_a import f\n", encoding="utf-8")
            (tmp / "svc_b" / "tests" / "conftest.py").write_text("x = f\n", encoding="utf-8")
            ctx = build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            sites, skipped = cmd_impact._references(ctx, "pkg/mod_a.py::f")
            joined = "\n".join(sites)
            self.assertIn("svc_a/tests/conftest.py", joined)
            self.assertIn("svc_b/tests/conftest.py", joined)
            self.assertEqual(skipped, [])

    def test_shared_production_module_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._two_roots(tmp)
            (tmp / "svc_b" / "pkg" / "mod_a.py").write_text("def f():\n    return 9\n", encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                build_two_root_ctx(tmp, md=MD_TWO_ROOTS)
            self.assertIn("pkg/mod_a.py", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
