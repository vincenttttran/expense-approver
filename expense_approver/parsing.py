"""Field normalization and parsing helpers (spec 8.6, 8.3, 8.1).

Pure functions. Parsers raise ``ValueError`` on bad input; the engine turns
that into an ``INVALID_RECORD`` decision (spec 4.2 step 1) rather than dropping
the record.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("0.01")

# Accepted receipt spellings, case-insensitive (spec 2.1).
_RECEIPT_TRUE = {"true", "yes", "1", "y"}
_RECEIPT_FALSE = {"false", "no", "0", "n"}


def normalize_category(value: str) -> str:
    """Trim and lower-case a category for threshold lookup (spec 8.6)."""
    return (value or "").strip().lower()


def parse_amount(value: str) -> Decimal:
    """Parse a monetary amount to a 2-decimal ``Decimal`` (spec 8.6, 8.7).

    Tolerates surrounding whitespace and a single leading ``$``. Rounds
    half-up to cents so boundary comparisons near $75 are exact. Raises
    ``ValueError`` on empty / non-numeric / non-finite input.
    """
    if value is None:
        raise ValueError("amount is missing")
    text = value.strip()
    if text.startswith("$"):
        text = text[1:].strip()
    if not text:
        raise ValueError("amount is empty")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"amount is not numeric: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"amount is not finite: {value!r}")
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def parse_receipt(value: str) -> bool:
    """Interpret a receipt flag (spec 2.1). Raises ``ValueError`` if unknown."""
    if value is None:
        raise ValueError("receipt is missing")
    text = value.strip().lower()
    if text in _RECEIPT_TRUE:
        return True
    if text in _RECEIPT_FALSE:
        return False
    raise ValueError(f"receipt not a recognized boolean: {value!r}")


def resolve_id(raw_id: str | None, row_index: int) -> str:
    """Return the given id, or a deterministic ``ROW-<n>`` placeholder (spec 8.1)."""
    if raw_id and raw_id.strip():
        return raw_id.strip()
    return f"ROW-{row_index}"
