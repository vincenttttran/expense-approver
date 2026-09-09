"""Policy configuration: load, validate, resolve thresholds (spec 4.1, 5.1, 7)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from .parsing import CENTS, normalize_category


class PolicyError(ValueError):
    """Raised when a policy config is malformed or violates a hard rule."""


def _money(value: object, field_name: str) -> Decimal:
    """Coerce a JSON number/string to a 2-decimal Decimal via str (no float)."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise PolicyError(f"{field_name} is not a valid amount: {value!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise PolicyError(f"{field_name} must be a non-negative amount: {value!r}")
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Policy:
    """A loaded, validated policy (spec 7)."""

    policy_version: str
    hard_cap: Decimal
    default_threshold: Decimal
    category_thresholds: dict[str, Decimal]
    reject_thresholds_above_hard_cap: bool = True

    def threshold_for(self, category: str) -> tuple[Decimal, bool]:
        """Resolve (threshold, is_unknown) for a normalized category (spec 4.3).

        Unknown categories fall back to the default threshold and are reported
        as unknown so the engine can attach the UNKNOWN_CATEGORY note.
        """
        key = normalize_category(category)
        if key in self.category_thresholds:
            return self.category_thresholds[key], False
        return self.default_threshold, True


def load_policy(path: str | Path) -> Policy:
    """Load and validate a policy JSON file (spec 7, 5.1 / Q4).

    When ``reject_thresholds_above_hard_cap`` is true, any category threshold
    above the hard cap is a load-time error rather than a silently-dead value
    (spec 5.1 decision Q4 -> option A). $75 stays an ironclad global ceiling.
    """
    path = Path(path)
    try:
        # utf-8-sig tolerates a UTF-8 BOM, which many Windows editors add.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise PolicyError(f"policy file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"policy file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError("policy file must be a JSON object")

    version = data.get("policy_version")
    if not isinstance(version, str) or not version.strip():
        raise PolicyError("policy_version must be a non-empty string")

    hard_cap = _money(data.get("hard_cap"), "hard_cap")
    default_threshold = _money(data.get("default_threshold"), "default_threshold")

    reject = data.get("reject_thresholds_above_hard_cap", True)
    if not isinstance(reject, bool):
        raise PolicyError("reject_thresholds_above_hard_cap must be a boolean")

    raw_table = data.get("category_thresholds", {})
    if not isinstance(raw_table, dict):
        raise PolicyError("category_thresholds must be a JSON object")

    thresholds: dict[str, Decimal] = {}
    for category, value in raw_table.items():
        key = normalize_category(category)
        amount = _money(value, f"category_thresholds.{category}")
        if reject and amount > hard_cap:
            raise PolicyError(
                f"category '{category}' threshold {amount} exceeds hard cap "
                f"{hard_cap}; such a threshold could never permit auto-approval "
                f"(spec 5.1). Lower it or set "
                f"reject_thresholds_above_hard_cap to false."
            )
        thresholds[key] = amount

    return Policy(
        policy_version=version.strip(),
        hard_cap=hard_cap,
        default_threshold=default_threshold,
        category_thresholds=thresholds,
        reject_thresholds_above_hard_cap=reject,
    )
