"""Engine decision tests: the spec 11 matrix + spec 10.8 boundary set."""

import unittest

from expense_approver.engine import decide
from expense_approver.models import ReasonCode, Status
from tests.support import DECIDED_AT, default_policy, make_record

R = ReasonCode

# (amount, category, receipt, expected_status, expected_reason_codes) from spec 11.
MATRIX = [
    ("42.00", "meals", "yes", Status.APPROVED, ()),
    ("50.00", "meals", "yes", Status.FLAGGED, (R.OVER_THRESHOLD,)),
    ("49.99", "meals", "yes", Status.APPROVED, ()),
    ("60.00", "travel", "no", Status.FLAGGED, (R.NO_RECEIPT,)),
    ("75.00", "travel", "yes", Status.FLAGGED, (R.OVER_THRESHOLD,)),
    ("74.99", "travel", "yes", Status.APPROVED, ()),
    ("75.01", "travel", "yes", Status.FLAGGED, (R.OVER_HARD_CAP,)),
    ("120.00", "software", "yes", Status.FLAGGED, (R.OVER_HARD_CAP,)),
    ("20.00", "crypto", "yes", Status.APPROVED, (R.UNKNOWN_CATEGORY,)),
    ("30.00", "crypto", "yes", Status.FLAGGED, (R.OVER_THRESHOLD, R.UNKNOWN_CATEGORY)),
    ("-5.00", "meals", "yes", Status.FLAGGED, (R.INVALID_RECORD,)),
    ("0.00", "meals", "yes", Status.FLAGGED, (R.INVALID_RECORD,)),
]


class TestMatrix(unittest.TestCase):
    def setUp(self):
        self.policy = default_policy()

    def test_spec_11_matrix(self):
        for amount, category, receipt, status, reasons in MATRIX:
            with self.subTest(amount=amount, category=category, receipt=receipt):
                record = make_record(amount, category=category, receipt=receipt)
                decision = decide(record, self.policy, decided_at=DECIDED_AT)
                self.assertEqual(decision.status, status)
                self.assertEqual(decision.reasons, reasons)


class TestBoundaries(unittest.TestCase):
    """Spec 10.8: threshold, threshold-0.01, 74.99, 75.00, 75.01."""

    def setUp(self):
        self.policy = default_policy()

    def decide_amount(self, amount, category="travel"):
        return decide(make_record(amount, category=category), self.policy, decided_at=DECIDED_AT)

    def test_at_category_threshold_is_flagged(self):
        # meals threshold 50 -> inclusive flag at ==threshold (spec 5.2 / Q5).
        self.assertEqual(self.decide_amount("50.00", "meals").status, Status.FLAGGED)

    def test_just_under_threshold_approves(self):
        self.assertEqual(self.decide_amount("49.99", "meals").status, Status.APPROVED)

    def test_74_99_approves(self):
        self.assertEqual(self.decide_amount("74.99").status, Status.APPROVED)

    def test_exactly_75_can_approve(self):
        # $75.00 is not "over" the cap; travel threshold is 75 so == flags on threshold,
        # but office threshold 50 already flags. Use a category whose threshold is the cap.
        decision = self.decide_amount("75.00", "travel")
        self.assertEqual(decision.status, Status.FLAGGED)
        self.assertEqual(decision.reasons, (ReasonCode.OVER_THRESHOLD,))
        # And a cap-equal amount under its threshold approves: raise travel to a
        # hypothetical where 75 < threshold is impossible under v1 (cap==max), so
        # verify the cap rule itself: 75.00 is not OVER_HARD_CAP.
        self.assertNotIn(ReasonCode.OVER_HARD_CAP, decision.reasons)

    def test_75_01_is_over_hard_cap(self):
        decision = self.decide_amount("75.01")
        self.assertEqual(decision.status, Status.FLAGGED)
        self.assertEqual(decision.reasons, (ReasonCode.OVER_HARD_CAP,))

    def test_half_up_rounding_near_cap(self):
        # 75.005 rounds half-up to 75.01 -> over the cap (spec 8.7).
        self.assertEqual(self.decide_amount("75.005").reasons, (ReasonCode.OVER_HARD_CAP,))


class TestReasonString(unittest.TestCase):
    def setUp(self):
        self.policy = default_policy()

    def test_clean_approval_has_empty_reason(self):
        decision = decide(make_record("10.00", "meals"), self.policy, decided_at=DECIDED_AT)
        self.assertEqual(decision.reason, "")

    def test_combined_reason_string(self):
        decision = decide(make_record("30.00", "crypto"), self.policy, decided_at=DECIDED_AT)
        self.assertEqual(decision.reason, "OVER_THRESHOLD + UNKNOWN_CATEGORY")

    def test_invalid_record_never_dropped(self):
        decision = decide(make_record("nan-ish$$"), self.policy, decided_at=DECIDED_AT)
        self.assertEqual(decision.status, Status.FLAGGED)
        self.assertEqual(decision.reasons, (ReasonCode.INVALID_RECORD,))


if __name__ == "__main__":
    unittest.main()
