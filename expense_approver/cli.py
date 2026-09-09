"""Command-line entrypoint (spec 1, 3.3).

Non-interactive: read a store of expenses, decide, write results back, print a
run summary. Usage:

  py -m expense_approver --backend csv --input expenses.csv --policy policy.json
  py -m expense_approver --backend sqlite --db expenses.db --policy policy.json
"""

from __future__ import annotations

import argparse
import sys

from .policy import PolicyError, load_policy
from .repository import CsvRepository, SqliteRepository, run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense_approver",
        description="Auto-approve or flag submitted expense reports (spec.md v1).",
    )
    parser.add_argument("--backend", choices=("csv", "sqlite"), required=True)
    parser.add_argument("--policy", required=True, help="Path to policy.json")
    parser.add_argument("--input", help="Input CSV path (csv backend)")
    parser.add_argument("--output", help="Output CSV path (csv backend; default <input>.decided.csv)")
    parser.add_argument("--errors", help="Errors CSV path (csv backend; default <input>.errors.csv)")
    parser.add_argument("--db", help="SQLite database path (sqlite backend)")
    parser.add_argument("--table", default="expenses", help="SQLite table (default: expenses)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        policy = load_policy(args.policy)
    except PolicyError as exc:
        print(f"Policy error: {exc}", file=sys.stderr)
        return 2

    repository = None
    try:
        if args.backend == "csv":
            if not args.input:
                print("--input is required for the csv backend", file=sys.stderr)
                return 2
            repository = CsvRepository(args.input, args.output, args.errors)
        else:
            if not args.db:
                print("--db is required for the sqlite backend", file=sys.stderr)
                return 2
            repository = SqliteRepository(args.db, args.table)

        summary = run(repository, policy)
    except (ValueError, OSError) as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if repository is not None:
            repository.close()

    print(summary.render())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
