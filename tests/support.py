"""Shared test helpers (not a test module)."""

from __future__ import annotations

from decimal import Decimal

from expense_approver.models import RawRecord
from expense_approver.policy import Policy

DECIDED_AT = "2026-09-09T14:00:00Z"


def default_policy() -> Policy:
    """The spec 7 v1 policy, built directly (independent of file loading)."""
    return Policy(
        policy_version="v1",
        hard_cap=Decimal("75.00"),
        default_threshold=Decimal("25.00"),
        category_thresholds={
            "meals": Decimal("50.00"),
            "travel": Decimal("75.00"),
            "office": Decimal("50.00"),
            "software": Decimal("75.00"),
        },
    )


def make_record(
    amount,
    category: str = "meals",
    receipt: str = "yes",
    rid: str = "E-1",
    employee: str = "e@co",
    submitted_at: str = "2026-09-01",
    row_index: int = 1,
) -> RawRecord:
    return RawRecord(
        id=rid,
        employee=employee,
        category=category,
        amount=str(amount),
        receipt=str(receipt),
        submitted_at=submitted_at,
        row_index=row_index,
    )
