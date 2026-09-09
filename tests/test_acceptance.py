"""Acceptance criteria (spec 10): conservation, backend parity, idempotency."""

import csv
import tempfile
import unittest
from pathlib import Path

from expense_approver.models import Status
from expense_approver.repository import CsvRepository, SqliteRepository, run
from tests.support import DECIDED_AT, default_policy

# A spread that exercises approve / each flag reason / invalid / unknown category.
DATA = [
    {"id": "E-1", "employee": "a@co", "category": "meals", "amount": "42.00", "receipt": "yes", "submitted_at": "2026-09-01"},
    {"id": "E-2", "employee": "b@co", "category": "software", "amount": "120.00", "receipt": "yes", "submitted_at": "2026-09-02"},
    {"id": "E-3", "employee": "c@co", "category": "travel", "amount": "60.00", "receipt": "no", "submitted_at": "2026-09-03"},
    {"id": "E-4", "employee": "d@co", "category": "meals", "amount": "50.00", "receipt": "yes", "submitted_at": "2026-09-04"},
    {"id": "E-5", "employee": "e@co", "category": "crypto", "amount": "20.00", "receipt": "yes", "submitted_at": "2026-09-05"},
    {"id": "E-6", "employee": "f@co", "category": "meals", "amount": "0.00", "receipt": "yes", "submitted_at": "2026-09-06"},
]
CSV_HEADER = "id,employee,category,amount,receipt,submitted_at\n"


def _as_csv(rows):
    lines = [CSV_HEADER]
    for r in rows:
        lines.append(
            f"{r['id']},{r['employee']},{r['category']},{r['amount']},{r['receipt']},{r['submitted_at']}\n"
        )
    return "".join(lines)


class TestAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.policy = default_policy()

    def _run_csv(self):
        path = self.tmp / "in.csv"
        path.write_text(_as_csv(DATA), encoding="utf-8")
        repo = CsvRepository(path)
        summary = run(repo, self.policy, decided_at=DECIDED_AT)
        with repo.output_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return summary, {r["id"]: (r["status"], r["reason"]) for r in rows}

    def _run_sqlite(self):
        repo = SqliteRepository(self.tmp / "in.db")
        repo.insert_inputs(DATA)
        summary = run(repo, self.policy, decided_at=DECIDED_AT)
        cursor = repo.conn.execute("SELECT id, status, reason FROM expenses ORDER BY pk")
        rows = {r["id"]: (r["status"], r["reason"]) for r in cursor.fetchall()}
        repo.close()
        return summary, rows

    def test_10_1_conservation_and_no_null_status(self):
        summary, rows = self._run_csv()
        # input_count == approved + flagged + errors (spec 10.1)
        self.assertEqual(len(DATA), summary.approved + summary.flagged + summary.errors)
        self.assertEqual(summary.processed, summary.approved + summary.flagged)
        valid = {Status.APPROVED.value, Status.FLAGGED.value}
        for status, _reason in rows.values():
            self.assertIn(status, valid)

    def test_10_4_backend_parity(self):
        _, csv_rows = self._run_csv()
        _, sqlite_rows = self._run_sqlite()
        self.assertEqual(csv_rows, sqlite_rows)

    def test_10_5_idempotent_rerun(self):
        _, first = self._run_sqlite()
        # Re-run against the now-decided db (same policy version) -> identical.
        repo = SqliteRepository(self.tmp / "in.db")
        run(repo, self.policy, decided_at="2099-01-01T00:00:00Z")
        cursor = repo.conn.execute("SELECT id, status, reason FROM expenses ORDER BY pk")
        second = {r["id"]: (r["status"], r["reason"]) for r in cursor.fetchall()}
        repo.close()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
