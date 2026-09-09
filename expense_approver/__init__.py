"""Expense-report approval tool (spec.md v1).

A batch tool that ingests expense records, applies a deterministic policy
engine, and marks each record APPROVED or FLAGGED with a reason. See spec.md
for the full contract; see plan.md for the Stage-3 build plan.
"""

from .models import Decision, ReasonCode, Status, RawRecord
from .policy import Policy, PolicyError, load_policy
from .engine import decide

__all__ = [
    "Decision",
    "ReasonCode",
    "Status",
    "RawRecord",
    "Policy",
    "PolicyError",
    "load_policy",
    "decide",
]
