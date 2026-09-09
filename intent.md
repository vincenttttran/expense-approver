# Intent: expense-report approval tool
Author: Vincent Tran Status: draft.

## Problem
Small teams approve expense reports by hand. A manager reads every
submission, checks the amount and whether a receipt is attached, and
decides. Most are routine and under a small-dollar threshold, so the
manual review is slow and adds little value, while the few that genuinely
need scrutiny wait in the same queue.

## Proposed outcome
A tool that ingests submitted expenses (category, amount, receipt flag),
auto-approves anything that satisfies policy, and flags the rest for
manager review with the reason it was flagged.

## Affected users and systems
Employees who submit expenses, the manager who reviews flagged items,
and the store of expense records (CSV or SQLite).

## Constraints
- Auto-approve only when amount is under the category threshold AND a
  receipt is attached.
- Any expense over $75 always goes to manager review, regardless of category.
- No expense is silently dropped; every record ends as approved or flagged.

## Open questions
- Should category thresholds be configurable, or fixed in the spec?
- Do we need an audit log of who approved what, or is status enough?