# Expense-Report Approval Tool

A batch tool that ingests submitted expense records, applies a deterministic
policy engine, and marks each record **APPROVED** (auto-approved) or **FLAGGED**
(routed to a manager) with a reason. Every input record produces exactly one
output record — nothing is silently dropped.

Built as **Stage 3 (Build)** of the AI-native SDLC playbook:
[`intent.md`](intent.md) → [`spec.md`](spec.md) → [`plan.md`](plan.md) → this code.

## Requirements

Python 3.10+ (standard library only — no third-party dependencies). On Windows,
use the `py` launcher in the examples below.

## Usage

```bash
# CSV backend: reads a file, writes <input>.decided.csv (+ <input>.errors.csv)
py -m expense_approver --backend csv --input examples/sample.csv --policy policy.json

# SQLite backend: decides rows in the `expenses` table in place
py -m expense_approver --backend sqlite --db expenses.db --policy policy.json
```

Every run prints a summary, e.g.:

```
Processed 3 records | APPROVED: 1 | FLAGGED: 2 | ERRORS: 0
Flag reasons: NO_RECEIPT=1, OVER_HARD_CAP=1
Policy version: v1
```

## Policy

Policy lives in [`policy.json`](policy.json) (thresholds, hard cap, defaults) and
is stamped onto every decision as `policy_version` for auditability. A category
threshold above the `$75` hard cap is rejected at load time (spec §5.1 / Q4).

## Decision rules (summary)

Evaluated in order, short-circuiting on the first failure:

1. Invalid record (missing field, non-numeric / zero / negative amount) → `INVALID_RECORD`
2. `amount > $75.00` → `OVER_HARD_CAP`
3. no receipt → `NO_RECEIPT`
4. `amount >= category threshold` → `OVER_THRESHOLD`
5. otherwise → `APPROVED`

Unknown categories use the default threshold and get an `UNKNOWN_CATEGORY` note.
See [`spec.md`](spec.md) for the full contract.

## Tests

```bash
py -m unittest discover -s tests -t . -v
```

40 tests cover the spec's rule matrix (§11), boundary cases (§10.8), config
validation, both storage backends, and the acceptance criteria (§10).
