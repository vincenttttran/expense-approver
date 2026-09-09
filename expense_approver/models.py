"""Data model for the approval tool (spec.md sections 2.1, 2.2, 4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Status(str, Enum):
    """Decision status. Never null, never any other value (spec 2.2)."""

    APPROVED = "APPROVED"
    FLAGGED = "FLAGGED"


class ReasonCode(str, Enum):
    """Reason codes (spec 4.4)."""

    OVER_HARD_CAP = "OVER_HARD_CAP"
    NO_RECEIPT = "NO_RECEIPT"
    OVER_THRESHOLD = "OVER_THRESHOLD"
    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"  # note; may accompany a flag
    INVALID_RECORD = "INVALID_RECORD"


# Canonical input field order (spec 2.1 / 3.1).
INPUT_FIELDS = ("id", "employee", "category", "amount", "receipt", "submitted_at")
# Appended decision columns (spec 2.2 / 3.2).
DECISION_FIELDS = ("status", "reason", "decided_at", "policy_version")
OUTPUT_FIELDS = INPUT_FIELDS + DECISION_FIELDS


@dataclass(frozen=True)
class RawRecord:
    """One input record with raw (string) field values echoed to output.

    ``id`` is already resolved (a real id or a ``ROW-<n>`` placeholder, spec
    8.1). ``amount`` and ``receipt`` stay as raw strings here; the engine
    normalizes and validates them (spec 4.2 step 1) so all decision logic,
    including validation, lives in one pure function.
    """

    id: str
    employee: str
    category: str
    amount: str
    receipt: str
    submitted_at: str = ""
    row_index: int = 0  # 1-based input position, for diagnostics

    def as_input_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "employee": self.employee,
            "category": self.category,
            "amount": self.amount,
            "receipt": self.receipt,
            "submitted_at": self.submitted_at,
        }


@dataclass(frozen=True)
class Decision:
    """A decided record: the input plus the decision columns (spec 2.2)."""

    record: RawRecord
    status: Status
    reasons: tuple[ReasonCode, ...]
    decided_at: str
    policy_version: str

    @property
    def reason(self) -> str:
        """Human-readable reason string; empty on a clean APPROVED (spec 2.2).

        Multiple codes are joined with ' + ' (e.g. the OVER_THRESHOLD +
        UNKNOWN_CATEGORY case in spec 11).
        """
        return " + ".join(r.value for r in self.reasons)

    def as_output_dict(self) -> dict[str, str]:
        out = self.record.as_input_dict()
        out["status"] = self.status.value
        out["reason"] = self.reason
        out["decided_at"] = self.decided_at
        out["policy_version"] = self.policy_version
        return out


@dataclass(frozen=True)
class ParseError:
    """An input line that could not be mapped to the schema at all (spec 8.4).

    Routed to the errors output and counted as an ERROR — never dropped.
    """

    row_index: int
    raw_line: str
    message: str


@dataclass
class ReadResult:
    """What a repository yields per input line: a record or a parse error."""

    record: RawRecord | None = None
    error: ParseError | None = None
