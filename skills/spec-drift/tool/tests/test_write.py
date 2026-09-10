"""Tests for the write commands."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cmd_write
import ledger as L
import lockfile as LK
from tests.test_check import MD, CODE, Fixture

TODAY = "2026-12-25"


def call(fx, command, *, entry_id="R-T-001", by="Alice", note="n", delete=False):
    return cmd_write.run(fx.ctx, command, entry_id, by, note, delete, TODAY)


class TestSync(unittest.TestCase):
    def test_sync_on_s1_creates_record_and_bumps_date(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            self.assertEqual(call(fx, "sync"), 0)
            lock = LK.load_lock(fx.lock_path)
            entry = L.parse_ledger(fx.md_path.read_text(encoding="utf-8"))["R-T-001"]
            self.assertEqual(lock["R-T-001"]["assertion_sha"], L.assertion_sha(entry))
            self.assertIn("pkg/mod.py::f", lock["R-T-001"]["anchors"])
            self.assertEqual(lock["R-T-001"]["confirmed_by"], "Alice")
            self.assertEqual(lock["R-T-001"]["note"], "n")
            self.assertEqual(entry.confirmed_date, TODAY)

    def test_sync_rejects_assistant(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            self.assertNotEqual(call(fx, "sync", by="Bot"), 0)

    def test_sync_rejects_wrong_state(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()                      # already S4
            self.assertNotEqual(call(fx, "sync"), 0)


class TestConfirm(unittest.TestCase):
    def test_confirm_refreshes_fingerprints(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            (fx.root / "backend" / "pkg" / "mod.py").write_text(
                "def f():\n    return 2\n", encoding="utf-8"
            )
            self.assertEqual(call(fx, "confirm", by="Bot"), 0)
            import cmd_check
            self.assertEqual(cmd_check.run(fx.ctx), 0)

    def test_confirm_accepts_assistant(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            self.assertEqual(call(fx, "confirm", by="Bot"), 0)
            self.assertEqual(LK.load_lock(fx.lock_path)["R-T-001"]["confirmed_by"], "Bot")

    def test_confirm_rejects_unknown_by(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            self.assertNotEqual(call(fx, "confirm", by="someone"), 0)


class TestRelink(unittest.TestCase):
    MD2 = MD.replace(
        "- `pkg/mod.py::f`\n",
        "- `pkg/mod.py::f`\n- `pkg/mod.py::g`\n",
    )
    CODE2 = CODE + "\n\ndef g():\n    return 2\n"

    def test_relink_on_s3_rebuilds_and_recomputes(self):
        """relink must recompute assertion_sha and every anchor fingerprint, write the
        confirmation metadata and bump the date in the markdown — otherwise check reports
        sha drift the moment relink finishes."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=self.MD2, code=self.CODE2)
            fx.seed_lock(anchors=("pkg/mod.py::f",))     # the lock holds one anchor → S3
            self.assertEqual(call(fx, "relink"), 0)
            lock = LK.load_lock(fx.lock_path)
            self.assertEqual(
                sorted(lock["R-T-001"]["anchors"]), ["pkg/mod.py::f", "pkg/mod.py::g"]
            )
            import cmd_check
            self.assertEqual(cmd_check.run(fx.ctx), 0, "check must be clean after relink")
            entry = L.parse_ledger(fx.md_path.read_text(encoding="utf-8"))["R-T-001"]
            self.assertEqual(entry.confirmed_date, TODAY)

    def test_relink_delete_on_s2(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            fx.md_path.write_text("# Empty ledger\n", encoding="utf-8")   # not in md, in lock → S2
            self.assertEqual(call(fx, "relink", delete=True), 0)
            self.assertEqual(LK.load_lock(fx.lock_path), {})

    def test_relink_delete_skips_anchor_precheck(self):
        """relink --delete does not apply the "every anchor must resolve" precondition."""
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d))
            fx.seed_lock()
            fx.md_path.write_text("# Empty ledger\n", encoding="utf-8")
            (fx.root / "backend" / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(call(fx, "relink", delete=True), 0)


class TestCommonPrecheck(unittest.TestCase):
    """Before a write command runs, every anchor in the markdown must resolve."""

    def test_sync_rejected_when_anchor_unresolvable(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Fixture(Path(d), md=MD.replace("::f`", "::nope`"))
            self.assertNotEqual(call(fx, "sync"), 0)
            self.assertEqual(LK.load_lock(fx.lock_path), {})


if __name__ == "__main__":
    unittest.main()
