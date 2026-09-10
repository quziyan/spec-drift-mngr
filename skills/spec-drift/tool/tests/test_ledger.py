"""Tests for ledger.py."""
from __future__ import annotations

import unittest

import ledger as L

SAMPLE = """# Order rules

### R-ORD-007 Refund window

**Current rule**
An order can be refunded within 14 days of delivery,
provided the caller passes gate=open.

**Boundary**
Only asserts whether the transition is allowed given deadline and gate.

**Anchors**
- `app/domain/order.py::is_refundable`
- `app/features/order/service.py::refund_order`

**Last confirmed**
2026-09-04

### R-ORD-008 Cancel

**Current rule**
A queued order can be cancelled by the store.

**Boundary**
Quota settlement is out of scope.

**Anchors**
- `app/features/order/service.py::cancel_order`

**Last confirmed**
2026-09-04
"""


class TestParse(unittest.TestCase):
    def test_two_entries(self):
        entries = L.parse_ledger(SAMPLE)
        self.assertEqual(sorted(entries), ["R-ORD-007", "R-ORD-008"])

    def test_fields(self):
        e = L.parse_ledger(SAMPLE)["R-ORD-007"]
        self.assertEqual(e.title, "Refund window")
        self.assertIn("gate=open", e.assertion)
        self.assertIn("transition is allowed", e.boundary)
        self.assertEqual(e.anchors, [
            "app/domain/order.py::is_refundable",
            "app/features/order/service.py::refund_order",
        ])
        self.assertEqual(e.confirmed_date, "2026-09-04")

    def test_missing_label_rejected(self):
        broken = SAMPLE.replace("**Boundary**", "**Scope**")
        with self.assertRaises(L.LedgerError):
            L.parse_ledger(broken)

    def test_duplicate_id_rejected(self):
        dup = SAMPLE + SAMPLE.split("# Order rules", 1)[1]
        with self.assertRaises(L.LedgerError):
            L.parse_ledger(dup)

    def test_duplicate_label_within_entry_rejected(self):
        """A label repeated inside one entry used to silently keep only the last block; it is now fail-loud.

        Build an entry whose body carries two `**Current rule**` blocks, the second stating
        the opposite of the first. The earlier implementation overwrote the first with
        the second (`out[current] = []` reset), so the machine locked only the later
        sentence while a human reading the markdown saw both. This must now be rejected
        outright rather than quietly picking one block.
        """
        dup_label = SAMPLE.replace(
            "**Boundary**\nOnly asserts whether the transition is allowed given deadline and gate.",
            "**Current rule**\nThe opposite of the above: a refund is also allowed when gate=closed.\n\n"
            "**Boundary**\nOnly asserts whether the transition is allowed given deadline and gate.",
        )
        with self.assertRaises(L.LedgerError):
            L.parse_ledger(dup_label)


SECTIONED = SAMPLE + """
## Book two - quota

This book covers how allowances are counted.

### R-QUOTA-001 Allowance is monthly

**Current rule**
The allowance is counted per store and per calendar month.

**Boundary**
The size of the cap is out of scope.

**Anchors**
- `app/services/order_quota.py::used_count`

**Last confirmed**
2026-09-06
"""


class TestSectionHeadings(unittest.TestCase):
    """A section heading such as `## Book two ...` must terminate the preceding entry
    instead of being swallowed into its "last confirmed" block."""

    def test_section_heading_terminates_previous_entry(self):
        entries = L.parse_ledger(SECTIONED)
        self.assertEqual(
            sorted(entries), ["R-ORD-007", "R-ORD-008", "R-QUOTA-001"]
        )
        self.assertEqual(entries["R-ORD-008"].confirmed_date, "2026-09-04")

    def test_section_heading_does_not_move_assertion_sha(self):
        """Sectioning is grouping for human readers only; it must not change any entry's assertion fingerprint."""
        before = L.assertion_sha(L.parse_ledger(SAMPLE)["R-ORD-008"])
        after = L.assertion_sha(L.parse_ledger(SECTIONED)["R-ORD-008"])
        self.assertEqual(before, after)

    def test_bump_date_still_targets_the_date_line(self):
        out = L.bump_confirmed_date(SECTIONED, "R-ORD-008", "2026-12-25")
        entries = L.parse_ledger(out)
        self.assertEqual(entries["R-ORD-008"].confirmed_date, "2026-12-25")
        self.assertEqual(entries["R-QUOTA-001"].confirmed_date, "2026-09-06")


class TestLabelRecognition(unittest.TestCase):
    """A line counts as a label line only if, after stripping trailing whitespace, the
    whole line is exactly one of the four literals."""

    def test_bold_text_inside_body_is_not_a_label(self):
        md = SAMPLE.replace(
            "A queued order can be cancelled by the store.",
            "A queued order can be cancelled by the store.\n"
            "**Boundary** this line carries body text, so it is not a label line.",
        )
        e = L.parse_ledger(md)["R-ORD-008"]
        self.assertIn("carries body text", e.assertion)

    def test_trailing_whitespace_on_label_line_tolerated(self):
        md = SAMPLE.replace("**Boundary**\n", "**Boundary**   \n")
        self.assertIn("transition is allowed", L.parse_ledger(md)["R-ORD-007"].boundary)


class TestAssertionSha(unittest.TestCase):
    """The rule text and the boundary text are each normalized with leading and trailing
    blank lines removed, joined with a single \\n, then hashed with sha256."""

    def test_stable(self):
        e = L.parse_ledger(SAMPLE)["R-ORD-007"]
        self.assertEqual(L.assertion_sha(e), L.assertion_sha(e))
        self.assertTrue(L.assertion_sha(e).startswith("sha256:"))

    def test_wording_change_moves_sha(self):
        a = L.parse_ledger(SAMPLE)["R-ORD-007"]
        b = L.parse_ledger(SAMPLE.replace("gate=open", "gate=unblocked"))["R-ORD-007"]
        self.assertNotEqual(L.assertion_sha(a), L.assertion_sha(b))

    def test_boundary_change_moves_sha(self):
        a = L.parse_ledger(SAMPLE)["R-ORD-007"]
        b = L.parse_ledger(
            SAMPLE.replace("transition is allowed", "transition is permitted")
        )["R-ORD-007"]
        self.assertNotEqual(L.assertion_sha(a), L.assertion_sha(b))

    def test_anchor_change_does_not_move_sha(self):
        """Anchors do not enter assertion_sha: changes to the anchor set are handled by S3/relink."""
        a = L.parse_ledger(SAMPLE)["R-ORD-007"]
        b = L.parse_ledger(
            SAMPLE.replace("- `app/features/order/service.py::refund_order`\n", "")
        )["R-ORD-007"]
        self.assertEqual(L.assertion_sha(a), L.assertion_sha(b))

    def test_confirmed_date_does_not_move_sha(self):
        a = L.parse_ledger(SAMPLE)["R-ORD-007"]
        b = L.parse_ledger(SAMPLE.replace("2026-09-04\n\n### R-ORD-008", "2027-01-01\n\n### R-ORD-008"))["R-ORD-007"]
        self.assertEqual(L.assertion_sha(a), L.assertion_sha(b))

    def test_trailing_blank_lines_ignored(self):
        a = L.parse_ledger(SAMPLE)["R-ORD-007"]
        b = L.parse_ledger(SAMPLE.replace("provided the caller passes gate=open.\n", "provided the caller passes gate=open.\n\n\n"))["R-ORD-007"]
        self.assertEqual(L.assertion_sha(a), L.assertion_sha(b))


class TestBumpDate(unittest.TestCase):
    def test_only_target_entry_bumped(self):
        out = L.bump_confirmed_date(SAMPLE, "R-ORD-007", "2026-12-25")
        entries = L.parse_ledger(out)
        self.assertEqual(entries["R-ORD-007"].confirmed_date, "2026-12-25")
        self.assertEqual(entries["R-ORD-008"].confirmed_date, "2026-09-04")

    def test_unknown_id_raises(self):
        with self.assertRaises(L.LedgerError):
            L.bump_confirmed_date(SAMPLE, "R-ORD-999", "2026-12-25")


class TestLabelsParameter(unittest.TestCase):
    CHINESE = L.Labels("**现行口径**", "**边界**", "**锚点**", "**最后确认**")

    def _chinese_sample(self):
        return (SAMPLE.replace("**Current rule**", "**现行口径**")
                      .replace("**Boundary**", "**边界**")
                      .replace("**Anchors**", "**锚点**")
                      .replace("**Last confirmed**", "**最后确认**"))

    def test_parse_with_custom_labels(self):
        entries = L.parse_ledger(self._chinese_sample(), self.CHINESE)
        self.assertEqual(sorted(entries), ["R-ORD-007", "R-ORD-008"])
        self.assertEqual(entries["R-ORD-008"].anchors, ["app/features/order/service.py::cancel_order"])

    def test_assertion_sha_ignores_labels(self):
        a = L.parse_ledger(SAMPLE, L.DEFAULT_LABELS)["R-ORD-007"]
        b = L.parse_ledger(self._chinese_sample(), self.CHINESE)["R-ORD-007"]
        self.assertEqual(L.assertion_sha(a), L.assertion_sha(b))

    def test_wrong_labels_report_missing(self):
        with self.assertRaises(L.LedgerError) as cm:
            L.parse_ledger(SAMPLE, self.CHINESE)
        self.assertIn("is missing label", str(cm.exception))
        self.assertIn("**现行口径**", str(cm.exception))

    def test_bump_date_with_custom_labels(self):
        out = L.bump_confirmed_date(self._chinese_sample(), "R-ORD-008", "2027-01-01", self.CHINESE)
        self.assertIn("2027-01-01", out)
        self.assertEqual(out.count("2026-09-04"), 1)


if __name__ == "__main__":
    unittest.main()
