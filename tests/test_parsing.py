"""Field parsing/normalization tests (spec 8.3, 8.6, 8.1, 8.7)."""

import unittest
from decimal import Decimal

from expense_approver.parsing import (
    normalize_category,
    parse_amount,
    parse_receipt,
    resolve_id,
)


class TestParseAmount(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_amount("42.00"), Decimal("42.00"))

    def test_strips_currency_and_whitespace(self):
        self.assertEqual(parse_amount("  $ 74.99 "), Decimal("74.99"))

    def test_quantizes_half_up_to_cents(self):
        self.assertEqual(parse_amount("74.999"), Decimal("75.00"))
        self.assertEqual(parse_amount("1.005"), Decimal("1.01"))

    def test_negative_parses_ok_rule_rejects_later(self):
        self.assertEqual(parse_amount("-5.00"), Decimal("-5.00"))

    def test_rejects_non_numeric(self):
        for bad in ("", "abc", "1.2.3", "nan", "inf", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_amount(bad)


class TestParseReceipt(unittest.TestCase):
    def test_truthy(self):
        for text in ("true", "TRUE", "yes", "Y", "1", " y "):
            with self.subTest(text=text):
                self.assertTrue(parse_receipt(text))

    def test_falsy(self):
        for text in ("false", "No", "0", "n", " N "):
            with self.subTest(text=text):
                self.assertFalse(parse_receipt(text))

    def test_unknown_raises(self):
        for bad in ("maybe", "", "2", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_receipt(bad)


class TestNormalizeCategory(unittest.TestCase):
    def test_trims_and_lowercases(self):
        self.assertEqual(normalize_category("  Meals "), "meals")
        self.assertEqual(normalize_category("TRAVEL"), "travel")


class TestResolveId(unittest.TestCase):
    def test_keeps_given_id(self):
        self.assertEqual(resolve_id(" E-1001 ", 3), "E-1001")

    def test_placeholder_for_missing(self):
        self.assertEqual(resolve_id("", 3), "ROW-3")
        self.assertEqual(resolve_id(None, 7), "ROW-7")


if __name__ == "__main__":
    unittest.main()
