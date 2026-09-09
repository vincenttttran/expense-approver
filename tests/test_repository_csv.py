"""CSV backend tests (spec 3.1, 3.2, 8.4, 8.5)."""

import csv
import tempfile
import unittest
from pathlib import Path

from expense_approver.repository import CsvRepository, run
from tests.support import DECIDED_AT, default_policy

SAMPLE = (
    "id,employee,category,amount,receipt,submitted_at\n"
    "E-1001,alice@co,meals,42.00,yes,2026-09-01\n"
    "E-1002,bob@co,software,120.00,yes,2026-09-02\n"
    "E-1003,carol@co,travel,60.00,no,2026-09-03\n"
)


class TestCsvBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.policy = default_policy()

    def _write_input(self, text, name="expenses.csv"):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def _read_output(self, repo):
        with repo.output_path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_matches_spec_3_2_expected_output(self):
        repo = CsvRepository(self._write_input(SAMPLE))
        summary = run(repo, self.policy, decided_at=DECIDED_AT)
        rows = {r["id"]: r for r in self._read_output(repo)}

        self.assertEqual(rows["E-1001"]["status"], "APPROVED")
        self.assertEqual(rows["E-1001"]["reason"], "")
        self.assertEqual(rows["E-1002"]["status"], "FLAGGED")
        self.assertEqual(rows["E-1002"]["reason"], "OVER_HARD_CAP")
        self.assertEqual(rows["E-1003"]["status"], "FLAGGED")
        self.assertEqual(rows["E-1003"]["reason"], "NO_RECEIPT")
        for row in rows.values():
            self.assertEqual(row["decided_at"], DECIDED_AT)
            self.assertEqual(row["policy_version"], "v1")

        self.assertEqual(summary.processed, 3)
        self.assertEqual(summary.approved, 1)
        self.assertEqual(summary.flagged, 2)
        self.assertEqual(summary.errors, 0)

    def test_never_overwrites_input(self):
        with self.assertRaises(ValueError):
            path = self._write_input(SAMPLE)
            CsvRepository(path, output_path=path)

    def test_unparseable_row_routed_to_errors(self):
        bad = SAMPLE + "E-1004,dave@co,meals,10.00\n"  # too few columns
        repo = CsvRepository(self._write_input(bad))
        summary = run(repo, self.policy, decided_at=DECIDED_AT)
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.processed, 3)
        self.assertTrue(repo.errors_path.exists())
        with repo.errors_path.open(encoding="utf-8", newline="") as handle:
            err_rows = list(csv.DictReader(handle))
        self.assertEqual(len(err_rows), 1)
        self.assertIn("expected 6 columns", err_rows[0]["error"])

    def test_missing_id_gets_row_placeholder(self):
        text = (
            "employee,category,amount,receipt\n"
            "e@co,meals,10.00,yes\n"
        )
        repo = CsvRepository(self._write_input(text))
        run(repo, self.policy, decided_at=DECIDED_AT)
        rows = self._read_output(repo)
        self.assertEqual(rows[0]["id"], "ROW-1")

    def test_empty_input_is_valid_zero_run(self):
        repo = CsvRepository(self._write_input("id,employee,category,amount,receipt,submitted_at\n"))
        summary = run(repo, self.policy, decided_at=DECIDED_AT)
        self.assertEqual(summary.processed, 0)
        self.assertEqual(summary.errors, 0)

    def test_missing_required_column_errors(self):
        repo = CsvRepository(self._write_input("id,employee,category,amount\nE-1,e,meals,10\n"))
        with self.assertRaises(ValueError):
            run(repo, self.policy, decided_at=DECIDED_AT)


if __name__ == "__main__":
    unittest.main()
