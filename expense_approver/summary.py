"""Run summary accumulation and rendering (spec 3.3)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .models import Decision, Status


@dataclass
class RunSummary:
    """Counts for one run; rendered to stdout at the end (spec 3.3)."""

    processed: int = 0
    approved: int = 0
    flagged: int = 0
    errors: int = 0
    duplicate_ids: int = 0
    flag_reasons: Counter = field(default_factory=Counter)
    policy_version: str = ""
    _seen_ids: set = field(default_factory=set)

    def record_decision(self, decision: Decision) -> None:
        self.processed += 1
        self.policy_version = decision.policy_version
        if decision.status is Status.APPROVED:
            self.approved += 1
        else:
            self.flagged += 1
            for code in decision.reasons:
                self.flag_reasons[code.value] += 1
        rid = decision.record.id
        if rid in self._seen_ids:
            self.duplicate_ids += 1
        else:
            self._seen_ids.add(rid)

    def record_error(self) -> None:
        self.errors += 1

    def render(self) -> str:
        lines = [
            f"Processed {self.processed} records | APPROVED: {self.approved} | "
            f"FLAGGED: {self.flagged} | ERRORS: {self.errors}"
        ]
        if self.flag_reasons:
            breakdown = ", ".join(
                f"{code}={count}" for code, count in sorted(self.flag_reasons.items())
            )
            lines.append(f"Flag reasons: {breakdown}")
        if self.duplicate_ids:
            lines.append(f"Warning: duplicate ids seen: {self.duplicate_ids}")
        lines.append(f"Policy version: {self.policy_version}")
        return "\n".join(lines)
