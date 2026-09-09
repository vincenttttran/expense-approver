"""Policy config loading and validation tests (spec 7, 5.1 / Q4)."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from expense_approver.policy import PolicyError, load_policy

GOOD = {
    "policy_version": "v1",
    "hard_cap": 75.00,
    "default_threshold": 25.00,
    "reject_thresholds_above_hard_cap": True,
    "category_thresholds": {"meals": 50.00, "travel": 75.00},
}


class TestLoadPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _write(self, data):
        path = self.tmp / "policy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_loads_amounts_as_decimal(self):
        policy = load_policy(self._write(GOOD))
        self.assertEqual(policy.hard_cap, Decimal("75.00"))
        self.assertEqual(policy.category_thresholds["meals"], Decimal("50.00"))
        self.assertIsInstance(policy.category_thresholds["travel"], Decimal)

    def test_threshold_lookup_and_unknown(self):
        policy = load_policy(self._write(GOOD))
        self.assertEqual(policy.threshold_for("meals"), (Decimal("50.00"), False))
        self.assertEqual(policy.threshold_for("crypto"), (Decimal("25.00"), True))

    def test_rejects_threshold_above_hard_cap(self):
        data = dict(GOOD, category_thresholds={"lux": 150.00})
        with self.assertRaises(PolicyError):
            load_policy(self._write(data))

    def test_allows_high_threshold_when_flag_off(self):
        data = dict(
            GOOD,
            reject_thresholds_above_hard_cap=False,
            category_thresholds={"lux": 150.00},
        )
        policy = load_policy(self._write(data))
        self.assertEqual(policy.category_thresholds["lux"], Decimal("150.00"))

    def test_missing_version_errors(self):
        data = dict(GOOD)
        del data["policy_version"]
        with self.assertRaises(PolicyError):
            load_policy(self._write(data))

    def test_non_numeric_hard_cap_errors(self):
        with self.assertRaises(PolicyError):
            load_policy(self._write(dict(GOOD, hard_cap="lots")))

    def test_missing_file_errors(self):
        with self.assertRaises(PolicyError):
            load_policy(self.tmp / "nope.json")


if __name__ == "__main__":
    unittest.main()
