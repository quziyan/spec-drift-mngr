"""Tests for lockfile.py."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import lockfile as LK
from ledger import Entry


def entry(entry_id: str, anchors: list[str]) -> Entry:
    return Entry(entry_id, "t", "a", "b", anchors, "2026-09-04", 1)


def lock_rec(anchors: list[str]) -> dict:
    return {
        "assertion_sha": "sha256:x",
        "anchors": {a: "sha256:y" for a in anchors},
        "confirmed_at": "2026-09-04T10:00:00+08:00",
        "confirmed_by": "Alice",
        "note": "n",
    }


class TestClassify(unittest.TestCase):
    def test_s1_md_only(self):
        st = LK.classify({"R-A": entry("R-A", ["f.py::a"])}, {})
        self.assertEqual(st, {"R-A": "S1"})

    def test_s2_lock_only(self):
        st = LK.classify({}, {"R-A": lock_rec(["f.py::a"])})
        self.assertEqual(st, {"R-A": "S2"})

    def test_s3_anchor_sets_differ(self):
        st = LK.classify(
            {"R-A": entry("R-A", ["f.py::a", "f.py::b"])},
            {"R-A": lock_rec(["f.py::a"])},
        )
        self.assertEqual(st, {"R-A": "S3"})

    def test_s4_anchor_sets_equal(self):
        st = LK.classify(
            {"R-A": entry("R-A", ["f.py::a", "f.py::b"])},
            {"R-A": lock_rec(["f.py::b", "f.py::a"])},
        )
        self.assertEqual(st, {"R-A": "S4"})

    def test_states_are_exhaustive_and_each_has_one_legal_command(self):
        for state in ("S1", "S2", "S3", "S4"):
            self.assertIn(state, LK.LEGAL_COMMAND)
        self.assertEqual(len(LK.LEGAL_COMMAND), 4)


class TestRoundTrip(unittest.TestCase):
    def test_save_load_stable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "drift-lock.json"
            data = {"R-B": lock_rec(["f.py::a"]), "R-A": lock_rec(["f.py::b"])}
            LK.save_lock(p, data)
            self.assertEqual(LK.load_lock(p), data)

    def test_output_is_sorted_and_utf8_readable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "drift-lock.json"
            LK.save_lock(p, {"R-B": lock_rec(["f.py::a"]), "R-A": lock_rec(["f.py::b"])})
            text = p.read_text(encoding="utf-8")
            self.assertLess(text.index('"R-A"'), text.index('"R-B"'))
            self.assertTrue(text.endswith("\n"))

    def test_missing_file_is_empty_dict(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(LK.load_lock(Path(d) / "nope.json"), {})


if __name__ == "__main__":
    unittest.main()
