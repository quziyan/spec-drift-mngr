"""Tests for check and for the CLI.

A minimal repository is built in a temporary directory; no real ledger is involved.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import cmd_check
import repo
import lockfile as LK
import ledger as L

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


class Fixture:
    def __init__(self, tmp: Path, md: str = MD, code: str = CODE):
        self.root = tmp
        (tmp / ".spec-drift.json").write_text(
            '{"code_root": "backend", '
            '"ledger": "docs/ledger.md", '
            '"lock": "docs/drift-lock.json", '
            '"owner": "Alice", "assistant": "Bot"}',
            encoding="utf-8",
        )
        (tmp / "backend" / "pkg").mkdir(parents=True)
        (tmp / "backend" / "pkg" / "mod.py").write_text(code, encoding="utf-8")
        (tmp / "docs").mkdir(parents=True)
        self.md_path = tmp / "docs" / "ledger.md"
        self.md_path.write_text(md, encoding="utf-8")
        self.lock_path = tmp / "docs" / "drift-lock.json"
        self.ctx = repo.build_ctx(tmp)

    def seed_lock(self, *, anchors=("pkg/mod.py::f",), drift_assertion=False):
        entry = L.parse_ledger(self.md_path.read_text(encoding="utf-8"))["R-T-001"]
        rec = {
            "assertion_sha": "sha256:stale" if drift_assertion else L.assertion_sha(entry),
            "anchors": {a: (repo.current_fingerprint(self.ctx, a) or "sha256:gone") for a in anchors},
            "confirmed_at": "2026-09-04T10:00:00+08:00",
            "confirmed_by": "Alice",
            "note": "seed",
        }
        LK.save_lock(self.lock_path, {"R-T-001": rec})


def run_check(fx) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cmd_check.run(fx.ctx)
    return code, buf.getvalue()


class TestCheck(unittest.TestCase):
    def test_clean_ledger_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            code, out = run_check(fx)
            self.assertEqual(code, 0, out)

    def test_non_s4_state_is_nonzero(self):
        """① the lock has no such entry → S1 → non-zero."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("S1", out)
            self.assertIn("R-T-001", out)

    def test_unresolvable_md_anchor_is_nonzero(self):
        """② an anchor in the markdown does not resolve in the code."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=MD.replace("::f`", "::nonexistent`"))
            fx.seed_lock(anchors=("pkg/mod.py::nonexistent",))
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("do not resolve", out)

    def test_vanished_lock_anchor_reported_separately(self):
        """③ a vanished lock anchor must be shown apart from ordinary hash drift."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            (fx.root / "backend" / "pkg" / "mod.py").write_text(
                "def renamed():\n    return 1\n", encoding="utf-8"
            )
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("anchors that vanished", out)
            head_vanished = out.index("anchors that vanished")
            self.assertNotIn("fingerprint drift", out[head_vanished:head_vanished + 200])

    def test_fingerprint_drift_is_nonzero(self):
        """④ the code changed and the ledger was never confirmed."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            (fx.root / "backend" / "pkg" / "mod.py").write_text(
                "def f():\n    return 2\n", encoding="utf-8"
            )
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("fingerprint drift", out)

    def test_assertion_sha_drift_is_nonzero(self):
        """④ rewording the ledger without touching the code must be reported too."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock(drift_assertion=True)
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("assertion text changed", out)


class TestEmptyOrMissingLedgerIsNonzero(unittest.TestCase):
    """A missing ledger file, or one that parses to 0 entries, must exit non-zero and name the reason; never a false green.

    The earlier behaviour (since changed, hence these assertions on the new behaviour):
    - ledger file missing → FileNotFoundError went uncaught and a traceback was printed.
    - ledger markdown present but malformed, parsing to 0 entries → `check` printed `0` for
      all five categories and exited 0 — indistinguishable in output from a genuinely clean
      ledger.
    """

    def test_missing_ledger_file_is_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.md_path.unlink()
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("ledger missing", out)
            self.assertIn("does not exist", out)

    def test_zero_entries_ledger_is_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md="# The ledger format is wrong, not one entry parses\n")
            code, out = run_check(fx)
            self.assertNotEqual(code, 0)
            self.assertIn("ledger empty", out)
            self.assertIn("0 entries", out)


class TestDuplicateWarningDoesNotAffectExit(unittest.TestCase):
    """⑤ a symbol defined more than once is only a warning; it does not affect the exit code."""

    DUP = "if C:\n    pass\n\ndef f():\n    return 1\n\n\ndef f():\n    return 2\n"

    def test_warning_only_still_zero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), code=self.DUP)
            fx.seed_lock()
            code, out = run_check(fx)
            self.assertIn("defined more than once", out)
            self.assertEqual(code, 0, out)

    def test_warning_plus_real_error_is_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), code=self.DUP)   # no seeded lock → S1
            code, out = run_check(fx)
            self.assertIn("defined more than once", out)
            self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
