"""SQLite backend tests (spec 2.3, 6 idempotency)."""

import tempfile
import unittest
from pathlib import Path

from expense_approver.repository import SqliteRepository, run
from tests.support import DECIDED_AT, default_policy

ROWS = [
    {"id": "E-1001", "employee": "alice@co", "category": "meals", "amount": "42.00", "receipt": "yes", "submitted_at": "2026-09-01"},
    {"id": "E-1002", "employee": "bob@co", "category": "software", "amount": "120.00", "receipt": "yes", "submitted_at": "2026-09-02"},
    {"id": "E-1003", "employee": "carol@co", "category": "travel", "amount": "60.00", "receipt": "no", "submitted_at": "2026-09-03"},
]


class TestSqliteBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "expenses.db"
        self.policy = default_policy()

    def _statuses(self, repo):
        cursor = repo.conn.execute("SELECT id, status, reason FROM expenses ORDER BY pk")
        return {r["id"]: (r["status"], r["reason"]) for r in cursor.fetchall()}

    def test_decides_and_stamps_in_place(self):
        repo = SqliteRepository(self.db)
        repo.insert_inputs(ROWS)
        summary = run(repo, self.policy, decided_at=DECIDED_AT)
        statuses = self._statuses(repo)
        repo.close()

        self.assertEqual(statuses["E-1001"], ("APPROVED", ""))
        self.assertEqual(statuses["E-1002"], ("FLAGGED", "OVER_HARD_CAP"))
        self.assertEqual(statuses["E-1003"], ("FLAGGED", "NO_RECEIPT"))
        self.assertEqual(summary.processed, 3)

    def test_rerun_is_idempotent_for_same_policy_version(self):
        repo = SqliteRepository(self.db)
        repo.insert_inputs(ROWS)
        run(repo, self.policy, decided_at=DECIDED_AT)
        first = self._statuses(repo)
        # Second run over already-decided rows must reproduce the same statuses.
        run(repo, self.policy, decided_at="2027-01-01T00:00:00Z")
        second = self._statuses(repo)
        repo.close()
        self.assertEqual(first, second)

    def test_no_null_status_after_run(self):
        repo = SqliteRepository(self.db)
        repo.insert_inputs(ROWS)
        run(repo, self.policy, decided_at=DECIDED_AT)
        cursor = repo.conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE status IS NULL OR status NOT IN ('APPROVED','FLAGGED')"
        )
        n = cursor.fetchone()["n"]
        repo.close()
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
