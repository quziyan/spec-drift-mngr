"""Configurable ledger labels: config validation and end-to-end parsing with non-default labels."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import ledger as L
import repo

ZH = {"assertion": "**现行口径**", "boundary": "**边界**", "anchors": "**锚点**", "confirmed": "**最后确认**"}

# Neutral content with Chinese labels: the fixture proving a non-English ledger still parses.
ZH_LEDGER = """# Order rules

### R-ORD-001 Refund window

**现行口径**
An order can be refunded within 14 days of delivery.

**边界**
Nothing about partial refunds.

**锚点**
- `svc/order.py::is_refundable`

**最后确认**
2026-09-04
"""

SRC = "def is_refundable(order):\n    return order.days_since_delivery <= 14\n"


class TestLabelsFromConfig(unittest.TestCase):
    def test_absent_means_default(self):
        self.assertEqual(L.labels_from_config({}), L.DEFAULT_LABELS)
        self.assertEqual(L.DEFAULT_LABELS.assertion, "**Current rule**")

    def test_explicit_null_rejected(self):
        """Only an absent key means "use the defaults"; an explicit null is a mistake,
        not a silent fallback to English."""
        with self.assertRaises(ValueError) as cm:
            L.labels_from_config({"labels": None})
        self.assertIn("must be an object", str(cm.exception))

    def test_non_dict_rejected(self):
        with self.assertRaises(ValueError) as cm:
            L.labels_from_config({"labels": "x"})
        self.assertIn("must be an object", str(cm.exception))

    def test_full_block_accepted(self):
        self.assertEqual(L.labels_from_config({"labels": ZH}), L.Labels(**ZH))

    def test_partial_block_rejected(self):
        with self.assertRaises(ValueError) as cm:
            L.labels_from_config({"labels": {"assertion": "**A**", "boundary": "**B**"}})
        self.assertIn("anchors", str(cm.exception))
        self.assertIn("confirmed", str(cm.exception))

    def _bad(self, **override):
        cfg = {"labels": {**{"assertion": "**A**", "boundary": "**B**", "anchors": "**C**", "confirmed": "**D**"}, **override}}
        with self.assertRaises(ValueError) as cm:
            L.labels_from_config(cfg)
        return str(cm.exception)

    def test_trailing_whitespace_rejected(self):
        self.assertIn("surrounding whitespace", self._bad(assertion="**A** "))

    def test_empty_rejected(self):
        self.assertIn("empty", self._bad(boundary="   "))

    def test_multiline_rejected(self):
        self.assertIn("single line", self._bad(anchors="**C**\nmore"))

    def test_duplicates_rejected(self):
        self.assertIn("distinct", self._bad(confirmed="**A**"))

    def test_section_heading_shape_rejected(self):
        self.assertIn("heading", self._bad(assertion="## A"))

    def test_entry_heading_shape_rejected(self):
        self.assertIn("heading", self._bad(assertion="### R-X-001 title"))

    def test_anchor_line_shape_rejected(self):
        self.assertIn("anchor line", self._bad(assertion="- `mod.py::f`"))

    def test_fence_rejected(self):
        self.assertIn("code fence", self._bad(assertion="```**A**"))

    def test_non_string_rejected(self):
        self.assertIn("string", self._bad(assertion=3))


class TestChineseLabelsEndToEnd(unittest.TestCase):
    def _repo(self, tmp: Path, with_labels: bool) -> Path:
        (tmp / "svc").mkdir()
        (tmp / "svc" / "order.py").write_text(SRC, encoding="utf-8")
        (tmp / "ledger.md").write_text(ZH_LEDGER, encoding="utf-8")
        cfg = {"code_root": "svc", "ledger": "ledger.md", "lock": "lock.json", "owner": "Alice", "assistant": "Bot"}
        if with_labels:
            cfg["labels"] = ZH
        (tmp / ".spec-drift.json").write_text(json.dumps(cfg), encoding="utf-8")
        return tmp

    def test_ctx_carries_labels_and_parses(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._repo(Path(d), with_labels=True)
            ctx = repo.build_ctx(root)
            self.assertEqual(ctx.labels, L.Labels(**ZH))
            entries = L.parse_ledger((root / "ledger.md").read_text(encoding="utf-8"), ctx.labels)
            self.assertEqual(list(entries), ["R-ORD-001"])

    def test_default_labels_do_not_parse_chinese_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._repo(Path(d), with_labels=False)
            ctx = repo.build_ctx(root)
            with self.assertRaises(L.LedgerError):
                L.parse_ledger((root / "ledger.md").read_text(encoding="utf-8"), ctx.labels)

    def test_sha_same_under_both_label_sets(self):
        en = (ZH_LEDGER.replace("**现行口径**", "**Current rule**").replace("**边界**", "**Boundary**")
                       .replace("**锚点**", "**Anchors**").replace("**最后确认**", "**Last confirmed**"))
        a = L.parse_ledger(ZH_LEDGER, L.Labels(**ZH))["R-ORD-001"]
        b = L.parse_ledger(en, L.DEFAULT_LABELS)["R-ORD-001"]
        self.assertEqual(L.assertion_sha(a), L.assertion_sha(b))


if __name__ == "__main__":
    unittest.main()
