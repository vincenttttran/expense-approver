"""Storage backends behind one interface (spec 2.3) + the run orchestration.

The rule engine is storage-agnostic: a repository yields ``ReadResult``s and
persists ``Decision``s / ``ParseError``s. ``run`` wires a repository to the
pure ``decide`` function and a ``RunSummary``.
"""

from __future__ import annotations

import csv
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, Iterator

from .engine import decide, _now_iso
from .models import (
    DECISION_FIELDS,
    INPUT_FIELDS,
    OUTPUT_FIELDS,
    Decision,
    ParseError,
    RawRecord,
    ReadResult,
)
from .parsing import resolve_id
from .policy import Policy
from .summary import RunSummary

_REQUIRED_COLUMNS = ("employee", "category", "amount", "receipt")


class Repository(ABC):
    """Read input records and persist decisions/errors for one backend."""

    @abstractmethod
    def read(self) -> Iterator[ReadResult]:
        """Yield one ReadResult per input line (a record or a parse error)."""

    @abstractmethod
    def write(self, decisions: Iterable[Decision], errors: Iterable[ParseError]) -> None:
        """Persist all decisions and parse errors."""

    def close(self) -> None:  # pragma: no cover - default no-op
        pass


def run(repository: Repository, policy: Policy, decided_at: str | None = None) -> RunSummary:
    """Decide every record from ``repository`` and persist results (spec 6).

    One timestamp is shared across the run. Each record is decided in
    isolation, so row order never affects a decision (order-independent).
    """
    stamp = decided_at if decided_at is not None else _now_iso()
    summary = RunSummary()
    summary.policy_version = policy.policy_version  # shown even on a zero-record run
    decisions: list[Decision] = []
    errors: list[ParseError] = []
    for result in repository.read():
        if result.error is not None:
            errors.append(result.error)
            summary.record_error()
        elif result.record is not None:
            decision = decide(result.record, policy, decided_at=stamp)
            decisions.append(decision)
            summary.record_decision(decision)
    repository.write(decisions, errors)
    return summary


# --------------------------------------------------------------------------- CSV


def _default_output(input_path: Path) -> Path:
    return input_path.with_name(input_path.stem + ".decided.csv")


def _default_errors(input_path: Path) -> Path:
    return input_path.with_name(input_path.stem + ".errors.csv")


class CsvRepository(Repository):
    """CSV backend (spec 2.3, 3.1, 3.2, 8.4).

    Reads one comma-delimited UTF-8 file with a header row; writes a *new*
    output file (never overwrites the input) with the decision columns
    appended, plus a separate errors file for unparseable rows.
    """

    def __init__(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        errors_path: str | Path | None = None,
    ) -> None:
        self.input_path = Path(input_path)
        self.output_path = Path(output_path) if output_path else _default_output(self.input_path)
        self.errors_path = Path(errors_path) if errors_path else _default_errors(self.input_path)
        if self.output_path.resolve() == self.input_path.resolve():
            raise ValueError("output path must differ from input path (spec 2.3)")

    def read(self) -> Iterator[ReadResult]:
        # utf-8-sig strips a leading BOM so the first header name isn't corrupted.
        with self.input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                return  # empty file -> zero records (spec 8.5)
            header = [h.strip() for h in header]
            missing = [c for c in _REQUIRED_COLUMNS if c not in header]
            if missing:
                raise ValueError(
                    f"input CSV is missing required column(s): {', '.join(missing)}"
                )
            index = {name: pos for pos, name in enumerate(header)}
            width = len(header)
            for offset, row in enumerate(reader, start=1):
                if len(row) != width:
                    yield ReadResult(
                        error=ParseError(
                            row_index=offset,
                            raw_line=",".join(row),
                            message=f"expected {width} columns, got {len(row)}",
                        )
                    )
                    continue
                get = lambda name: row[index[name]] if name in index else ""
                record = RawRecord(
                    id=resolve_id(get("id"), offset),
                    employee=get("employee"),
                    category=get("category"),
                    amount=get("amount"),
                    receipt=get("receipt"),
                    submitted_at=get("submitted_at"),
                    row_index=offset,
                )
                yield ReadResult(record=record)

    def write(self, decisions: Iterable[Decision], errors: Iterable[ParseError]) -> None:
        with self.output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(OUTPUT_FIELDS)
            for decision in decisions:
                out = decision.as_output_dict()
                writer.writerow([out[field] for field in OUTPUT_FIELDS])

        errors = list(errors)
        if errors:
            with self.errors_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["row_index", "raw_line", "error"])
                for err in errors:
                    writer.writerow([err.row_index, err.raw_line, err.message])


# ------------------------------------------------------------------------ SQLite


class SqliteRepository(Repository):
    """SQLite backend (spec 2.3).

    A single ``expenses`` table holds input + (nullable) decision columns.
    A run updates rows in place and stamps the decision columns; because
    ``decide`` is deterministic, re-running is idempotent for an unchanged
    policy version (spec 6). Unparseable rows go to ``expense_errors``.
    """

    def __init__(self, db_path: str | Path, table: str = "expenses") -> None:
        self.db_path = str(db_path)
        self.table = table
        self.errors_table = f"{table}_errors"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        input_cols = ", ".join(f"{name} TEXT" for name in INPUT_FIELDS)
        decision_cols = ", ".join(f"{name} TEXT" for name in DECISION_FIELDS)
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table} "
            f"(pk INTEGER PRIMARY KEY AUTOINCREMENT, {input_cols}, {decision_cols})"
        )
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.errors_table} "
            f"(row_index INTEGER, raw_line TEXT, message TEXT)"
        )
        self.conn.commit()

    def insert_inputs(self, rows: Iterable[dict]) -> None:
        """Insert input-only rows (decision columns left null). For ingestion/tests."""
        cols = ", ".join(INPUT_FIELDS)
        placeholders = ", ".join("?" for _ in INPUT_FIELDS)
        self.conn.executemany(
            f"INSERT INTO {self.table} ({cols}) VALUES ({placeholders})",
            [tuple(row.get(field, "") for field in INPUT_FIELDS) for row in rows],
        )
        self.conn.commit()

    def read(self) -> Iterator[ReadResult]:
        cols = ", ".join(INPUT_FIELDS)
        cursor = self.conn.execute(f"SELECT pk, {cols} FROM {self.table} ORDER BY pk")
        for row in cursor.fetchall():
            pk = row["pk"]
            record = RawRecord(
                id=resolve_id(row["id"], pk),
                employee=row["employee"] or "",
                category=row["category"] or "",
                amount="" if row["amount"] is None else str(row["amount"]),
                receipt="" if row["receipt"] is None else str(row["receipt"]),
                submitted_at=row["submitted_at"] or "",
                row_index=pk,
            )
            yield ReadResult(record=record)

    def write(self, decisions: Iterable[Decision], errors: Iterable[ParseError]) -> None:
        assignments = ", ".join(f"{name} = ?" for name in DECISION_FIELDS)
        for decision in decisions:
            out = decision.as_output_dict()
            self.conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE pk = ?",
                (*[out[field] for field in DECISION_FIELDS], decision.record.row_index),
            )
        for err in errors:
            self.conn.execute(
                f"INSERT INTO {self.errors_table} (row_index, raw_line, message) "
                f"VALUES (?, ?, ?)",
                (err.row_index, err.raw_line, err.message),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
