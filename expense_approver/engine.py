"""The policy rule engine: ``decide(record, policy) -> Decision`` (spec 4).

A pure function. Rules are evaluated in a fixed order and short-circuit to
FLAGGED on the first failing hard rule (spec 4.2). The UNKNOWN_CATEGORY note
is attached only at the threshold step, so a record short-circuited earlier
(hard cap / no receipt) does not carry it -- matching the spec 11 matrix.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import Decision, RawRecord, ReasonCode, Status
from .parsing import parse_amount, parse_receipt
from .policy import Policy


def _now_iso() -> str:
    """Current time as UTC ISO-8601 with a trailing Z (spec 2.2)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def decide(record: RawRecord, policy: Policy, decided_at: str | None = None) -> Decision:
    """Decide one record against the policy (spec 4.2).

    ``decided_at`` is injectable so a whole run can share one timestamp and so
    tests are deterministic; it never affects the status/reason decision.
    """
    stamp = decided_at if decided_at is not None else _now_iso()

    def result(status: Status, *reasons: ReasonCode) -> Decision:
        return Decision(
            record=record,
            status=status,
            reasons=tuple(reasons),
            decided_at=stamp,
            policy_version=policy.policy_version,
        )

    # 1. Validate (spec 4.2 step 1, 8.2, 8.3). Never dropped -> INVALID_RECORD.
    if not record.employee or not record.employee.strip():
        return result(Status.FLAGGED, ReasonCode.INVALID_RECORD)
    if not record.category or not record.category.strip():
        return result(Status.FLAGGED, ReasonCode.INVALID_RECORD)
    try:
        amount = parse_amount(record.amount)
        receipt = parse_receipt(record.receipt)
    except ValueError:
        return result(Status.FLAGGED, ReasonCode.INVALID_RECORD)
    # Zero and negative amounts are data errors, never auto-approved (spec 8.2 / Q7).
    if amount <= 0:
        return result(Status.FLAGGED, ReasonCode.INVALID_RECORD)

    # 2. Hard cap: strictly greater than the cap always flags (spec 4.1, 5.2).
    if amount > policy.hard_cap:
        return result(Status.FLAGGED, ReasonCode.OVER_HARD_CAP)

    # 3. Receipt required (spec 4.2 step 3).
    if not receipt:
        return result(Status.FLAGGED, ReasonCode.NO_RECEIPT)

    # 4. Category threshold: inclusive flag at ``>=`` (spec 4.2 step 4, 5.2 / Q5).
    threshold, unknown = policy.threshold_for(record.category)
    note = (ReasonCode.UNKNOWN_CATEGORY,) if unknown else ()
    if amount >= threshold:
        return result(Status.FLAGGED, ReasonCode.OVER_THRESHOLD, *note)

    # 5. Otherwise approve (the UNKNOWN_CATEGORY note still rides along, spec 11).
    return result(Status.APPROVED, *note)
