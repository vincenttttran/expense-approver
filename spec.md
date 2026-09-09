# Spec: Expense-Report Approval Tool

**Author:** Vincent Tran (spec derived from `intent.md`)
**Status:** Draft, ready for implementation review
**Source intent:** [intent.md](intent.md)

---

## 1. Overview

A batch tool that ingests submitted expense records, applies a deterministic
policy engine, and marks each record as either **APPROVED** (auto-approved) or
**FLAGGED** (routed to a manager for review). Every input record produces exactly
one output record with a decision and, when flagged, a human-readable reason.

The tool is non-interactive: it reads a store of expenses, decides, and writes
results back. It does not itself present a review UI; it produces the queue a
manager works from.

### 1.1 Goals

- Remove manual review of routine, low-value, receipt-backed expenses.
- Guarantee no record is lost: every record ends APPROVED or FLAGGED.
- Give the manager a clear reason for every flagged item.
- Keep the decision logic deterministic, auditable, and re-runnable.

### 1.2 Non-goals (v1)

- No approval *workflow* (no notifications, no manager sign-off capture beyond a
  status field — see [§9](#9-open-questions--decisions-needed)).
- No multi-currency handling (assume a single currency, see [§8](#8-edge-cases)).
- No fraud/duplicate detection beyond the stated rules.
- No user authentication or role management.

---

## 2. Data Model

### 2.1 Expense record (input)

| Field         | Type            | Required | Notes |
|---------------|-----------------|----------|-------|
| `id`          | string          | yes      | Unique record identifier. If absent in CSV, the tool assigns a stable row-derived id (see [§8.1](#81-missing-or-duplicate-ids)). |
| `employee`    | string          | yes      | Submitter identifier (name or email). |
| `category`    | string          | yes      | Normalized to lower-case, trimmed. Maps to a threshold (see [§4](#4-policy--rule-engine)). |
| `amount`      | decimal         | yes      | Monetary value. Must be non-negative. Stored/compared to 2 decimal places. |
| `receipt`     | boolean         | yes      | Whether a receipt is attached. Accepts `true/false`, `yes/no`, `1/0`, `y/n` (case-insensitive) on input. |
| `submitted_at`| ISO-8601 date   | no       | Informational; not used by the rule engine in v1. |

### 2.2 Decision record (output)

Output = every input field, plus:

| Field          | Type      | Notes |
|----------------|-----------|-------|
| `status`       | enum      | `APPROVED` or `FLAGGED`. |
| `reason`       | string    | Empty when `APPROVED`. One or more reason codes when `FLAGGED` (see [§4.4](#44-reason-codes)). |
| `decided_at`   | timestamp | When the tool made the decision (UTC ISO-8601). |
| `policy_version`| string   | Version of the policy config used, for auditability. |

`status` is never null and never any value other than the two enum members — this
is the machine enforcement of the intent's "no record silently dropped" constraint.

### 2.3 Storage backends

Two interchangeable backends selectable at runtime; the data model above is
identical across both.

**CSV**
- Input: one file, header row required, comma-delimited, UTF-8.
- Output: a new file (never overwrite input in place) with the decision columns
  appended. Default: `<input>.decided.csv`.

**SQLite**
- Single table `expenses` holding both input and decision columns.
- The decision columns are nullable until a decision run populates them.
- A run updates rows in place and stamps `decided_at` / `policy_version`.
- Re-runs are idempotent: re-deciding a row yields the same status for the same
  policy version (see [§6](#6-processing-model)).

**Recommendation:** implement CSV first (simplest, matches the "small team"
context); treat SQLite as the same schema behind a thin repository interface so
the rule engine is storage-agnostic.

---

## 3. Input / Output Formats

### 3.1 CSV input example

```csv
id,employee,category,amount,receipt,submitted_at
E-1001,alice@co,meals,42.00,yes,2026-09-01
E-1002,bob@co,software,120.00,yes,2026-09-02
E-1003,carol@co,travel,60.00,no,2026-09-03
```

### 3.2 CSV output example

```csv
id,employee,category,amount,receipt,submitted_at,status,reason,decided_at,policy_version
E-1001,alice@co,meals,42.00,yes,2026-09-01,APPROVED,,2026-09-09T14:00:00Z,v1
E-1002,bob@co,software,120.00,yes,2026-09-02,FLAGGED,OVER_HARD_CAP,2026-09-09T14:00:00Z,v1
E-1003,carol@co,travel,60.00,no,2026-09-03,FLAGGED,NO_RECEIPT,2026-09-09T14:00:00Z,v1
```

### 3.3 Run summary (stdout / log)

Every run prints a summary:

```
Processed 3 records | APPROVED: 1 | FLAGGED: 2 | ERRORS: 0
Flag reasons: OVER_HARD_CAP=1, NO_RECEIPT=1
Policy version: v1
```

Records that cannot be parsed at all are counted as ERRORS and are **not**
silently dropped — see [§8.4](#84-unparseable-rows).

---

## 4. Policy / Rule Engine

The engine evaluates rules in a fixed order and short-circuits to FLAGGED on the
first failing hard rule. It is a pure function: `decide(record, policy) -> decision`.

### 4.1 Policy inputs

- **Hard cap:** `$75.00`. Any amount **strictly greater than** the hard cap is
  always flagged, regardless of category or receipt. (From intent constraint:
  "Any expense over $75 always goes to manager review.")
- **Category thresholds:** a table mapping category → threshold amount.
- **Default threshold:** applied to categories not in the table (see
  [§4.3](#43-default-and-unknown-categories)).

Recommended starting thresholds (configurable — see [§9, Q1](#9-open-questions--decisions-needed)):

| Category   | Threshold |
|------------|-----------|
| `meals`    | $50.00    |
| `travel`   | $75.00    |
| `office`   | $50.00    |
| `software` | $75.00    |
| *(default)*| $25.00    |

> Note: because of the hard cap, no threshold above $75.00 can ever take full
> effect. See the conflict analysis in [§5](#5-policy-conflicts--areas-of-concern).

### 4.2 Decision procedure

For each record, in order:

1. **Validate** the record (required fields present, amount parseable and
   non-negative). On failure → `FLAGGED` with `INVALID_RECORD` (never dropped).
2. **Hard cap:** if `amount > 75.00` → `FLAGGED` with `OVER_HARD_CAP`. Stop.
3. **Receipt:** if `receipt` is not true → `FLAGGED` with `NO_RECEIPT`. Stop.
4. **Category threshold:** resolve threshold for the category. If
   `amount >= threshold` → `FLAGGED` with `OVER_THRESHOLD`. Stop.
5. Otherwise → `APPROVED`.

Auto-approval therefore requires **all** of: valid record AND `amount <= 75.00`
AND receipt attached AND `amount < category threshold`. This is the intent's
"under the category threshold AND a receipt is attached," with the hard cap
layered on top.

### 4.3 Default and unknown categories

The intent does not say what happens when a category has no configured threshold.
**Decision for v1:** unknown categories use the **default threshold ($25.00)** and
additionally attach an informational `UNKNOWN_CATEGORY` note. Rationale: fail
safe toward review rather than toward auto-approval. Flagged for confirmation in
[§9, Q3](#9-open-questions--decisions-needed).

### 4.4 Reason codes

| Code               | Meaning | Terminal? |
|--------------------|---------|-----------|
| `OVER_HARD_CAP`    | Amount > $75.00. | Flag |
| `NO_RECEIPT`       | No receipt attached. | Flag |
| `OVER_THRESHOLD`   | Amount at or above the category threshold. | Flag |
| `UNKNOWN_CATEGORY` | Category not in the policy table; default threshold applied. | Note (may accompany a flag) |
| `INVALID_RECORD`   | Missing/malformed required field. | Flag |

Because the engine short-circuits, a flagged record normally carries a **single**
primary reason code (the first rule it failed). `UNKNOWN_CATEGORY` is the one code
that may appear alongside another. See [§5.3](#53-single-vs-multiple-reasons) for
the trade-off.

---

## 5. Policy Conflicts & Areas of Concern

**These are the areas where the intent's constraints interact in ways that need a
human decision. They are called out explicitly per the task.**

### 5.1 Hard cap silently overrides high category thresholds ⚠️

The intent allows per-category thresholds *and* a blanket "$75 always goes to
review." Any category threshold set above $75 is partially dead: an expense of,
say, $90 in a category with a $150 threshold is "under threshold" (constraint 1
would auto-approve it) but "over $75" (constraint 2 forces review). **Constraint 2
wins in this spec**, so the effective ceiling for auto-approval is
`min(category_threshold, $75)` for every category.

- **Impact:** thresholds above $75 are misleading — they look configurable but
  can never permit auto-approval above $75.
- **Recommendation:** either (a) treat $75 as a documented global ceiling and
  reject/warn on any configured threshold above it, or (b) reinterpret the $75
  rule as the *default* threshold for categories without their own. This spec
  assumes (a). **Needs owner confirmation.**

### 5.2 Boundary semantics at the threshold and at $75 ⚠️

The intent says "**under** the category threshold" and "**over** $75" — both
exclusive wordings, but they leave the exact-boundary cases undefined:

- **At the category threshold** (`amount == threshold`): "under" is exclusive, so
  an amount *equal* to the threshold is **not** under it → **FLAGGED**
  (`OVER_THRESHOLD`). This spec uses `>=` for the flag.
- **At exactly $75.00**: "over $75" is exclusive, so `$75.00` is **not** over the
  cap. This spec uses `> 75.00`, meaning exactly $75.00 can still auto-approve if
  it also clears its category threshold and has a receipt.
- These two choices are **deliberately inconsistent** (threshold is inclusive-flag,
  cap is exclusive-flag) because they mirror the intent's exact wording. If the
  owner wants consistency, pick one convention. **Needs owner confirmation.**

### 5.3 Single vs. multiple reasons

The engine short-circuits, so a record failing several rules reports only the
first. A $200 expense with no receipt reports `OVER_HARD_CAP`, not also
`NO_RECEIPT`. This keeps the manager's queue readable but hides secondary issues.

- **Alternative:** evaluate all rules and report every failing reason. More
  complete, noisier.
- **Recommendation:** short-circuit for v1 (matches "flag with *the* reason" in
  the intent); revisit if managers want full reason lists.

### 5.4 "Receipt attached" is a flag, not a receipt

The tool trusts the `receipt` boolean; it never verifies a file exists or is
valid. A record can claim `receipt=yes` with no real document. This is in scope of
the intent (it says "receipt flag") but worth stating so it is not mistaken for
verification.

### 5.5 No amount lower bound in intent

The intent sets an upper cap but no floor. Zero and negative amounts are possible
in the data (refunds, corrections). See [§8.2](#82-zero-and-negative-amounts) for
the v1 handling; flagged as a policy gap.

---

## 6. Processing Model

- **Deterministic:** same input + same policy version → same decision, every run.
- **Idempotent:** re-running over already-decided records reproduces the same
  status (unless the policy version changed). SQLite runs update in place; CSV
  runs write a fresh output file.
- **Order-independent:** each record is decided in isolation; row order does not
  affect any decision.
- **Policy versioning:** the policy (thresholds, hard cap) is loaded from config
  and stamped onto every decision as `policy_version`. Changing thresholds means
  bumping the version so historical decisions remain explainable.

---

## 7. Configuration

Policy lives in a config file (e.g. `policy.json` / `policy.toml`), not hard-coded:

```json
{
  "policy_version": "v1",
  "hard_cap": 75.00,
  "default_threshold": 25.00,
  "reject_thresholds_above_hard_cap": true,
  "category_thresholds": {
    "meals": 50.00,
    "travel": 75.00,
    "office": 50.00,
    "software": 75.00
  }
}
```

Making thresholds configurable answers the intent's open question Q1 in favor of
*configurable*. Rationale: small teams' category limits change; recompiling to
adjust a dollar amount is friction. If the owner prefers fixed-in-spec values,
the same table is simply inlined as constants.

`reject_thresholds_above_hard_cap` operationalizes [§5.1](#51-hard-cap-silently-overrides-high-category-thresholds-): when true, the loader errors on any
category threshold above the hard cap rather than accepting a dead value.

---

## 8. Edge Cases

### 8.1 Missing or duplicate IDs
- Missing `id`: assign `ROW-<n>` from the input position; deterministic per file.
- Duplicate `id`: not de-duplicated in v1; each row is decided independently. The
  run summary reports a duplicate-id count as a warning.

### 8.2 Zero and negative amounts
- `amount == 0`: passes the hard cap and is auto-approvable if receipt + threshold
  clear. **Decision:** flag zero-amount records with `INVALID_RECORD` — a $0
  expense is almost certainly a data error worth a human glance. *Confirm.*
- `amount < 0`: treated as `INVALID_RECORD` → FLAGGED. Negative/refund handling is
  out of scope for v1; never auto-approved.

### 8.3 Malformed amount / receipt
- Non-numeric `amount`, or a `receipt` value outside the accepted set → the field
  fails validation → `INVALID_RECORD` → FLAGGED. Never dropped.

### 8.4 Unparseable rows
- A row that cannot be parsed into the schema at all (wrong column count, encoding
  failure) is written to an `errors` output (CSV: `<input>.errors.csv`; SQLite: an
  `expense_errors` table) with the raw line and a parse-error message, and counted
  in the run summary. This preserves the "nothing silently dropped" guarantee even
  for input the schema can't represent.

### 8.5 Empty input
- Zero data rows → a valid run producing an empty output plus a summary line
  `Processed 0 records`. Not an error.

### 8.6 Whitespace / case
- `category` is trimmed and lower-cased before lookup. `receipt` strings are
  trimmed and lower-cased before interpretation. `amount` tolerates surrounding
  whitespace and a leading currency symbol (`$`), which is stripped.

### 8.7 Precision
- Amounts are handled as fixed-point/decimal to 2 places (not binary float) to
  avoid `74.999999` style comparison errors near the $75 boundary. Comparisons
  round half-up to cents before applying rules.

---

## 9. Open Questions / Decisions Needed

Answered here with a recommended default; each still wants owner sign-off.

| # | Question (from intent + analysis) | This spec's default | Needs confirmation |
|---|-----------------------------------|---------------------|--------------------|
| Q1 | Are category thresholds configurable or fixed? | **Configurable** via `policy.json`. | Owner preference. |
| Q2 | Do we need an audit log of *who approved what*, or is status enough? | Status + `decided_at` + `policy_version` on each record (a lightweight audit trail); **no separate approver identity** in v1 because auto-approval has no human approver and manager sign-off is out of scope. | Confirm whether manager actions on flagged items must be recorded later. |
| Q3 | How are unknown categories handled? | Default threshold ($25) **plus** `UNKNOWN_CATEGORY` note; fail toward review. | Confirm default value and whether unknown category should hard-flag. |
| Q4 | Should thresholds above the $75 hard cap be allowed? ([§5.1](#51-hard-cap-silently-overrides-high-category-thresholds-)) | **Rejected at config load** (`reject_thresholds_above_hard_cap: true`). | Confirm, or choose the "$75 as default threshold" reinterpretation. |
| Q5 | Boundary convention at threshold and at $75 ([§5.2](#52-boundary-semantics-at-the-threshold-and-at-75-)) | Threshold flag on `>=`; hard cap flag on `>`. | Confirm, or unify. |
| Q6 | Multiple reasons per flag? ([§5.3](#53-single-vs-multiple-reasons)) | Single short-circuited reason (+ optional `UNKNOWN_CATEGORY`). | Confirm. |
| Q7 | Zero-amount handling ([§8.2](#82-zero-and-negative-amounts)) | Flag as `INVALID_RECORD`. | Confirm. |

---

## 10. Acceptance Criteria

The implementation is done when:

1. Every input record yields exactly one output record with `status` ∈
   {`APPROVED`, `FLAGGED`} — verified by a test asserting `input_count ==
   approved + flagged + errors` and that no output row has a null status.
2. A record auto-approves **iff** valid AND `amount <= 75.00` AND receipt attached
   AND `amount < category threshold`.
3. Any `amount > 75.00` is FLAGGED `OVER_HARD_CAP` regardless of category/receipt.
4. Both CSV and SQLite backends produce identical decisions for identical data.
5. Re-running is idempotent for an unchanged policy version.
6. The run summary reports counts and flag-reason breakdown.
7. Malformed and unparseable rows are captured (flagged or routed to errors), not
   dropped.
8. Boundary tests exist for `amount` = threshold, threshold − 0.01, $74.99,
   $75.00, and $75.01.
9. Policy thresholds are loaded from config and stamped as `policy_version` on
   every decision.

---

## 11. Suggested Test Matrix (illustrative)

| amount | category | receipt | threshold | Expected | Reason |
|--------|----------|---------|-----------|----------|--------|
| 42.00  | meals    | yes     | 50        | APPROVED | — |
| 50.00  | meals    | yes     | 50        | FLAGGED  | OVER_THRESHOLD (== threshold) |
| 49.99  | meals    | yes     | 50        | APPROVED | — |
| 60.00  | travel   | no      | 75        | FLAGGED  | NO_RECEIPT |
| 75.00  | travel   | yes     | 75        | FLAGGED  | OVER_THRESHOLD (== threshold) |
| 74.99  | travel   | yes     | 75        | APPROVED | under both cap and threshold |
| 75.01  | travel   | yes     | 75        | FLAGGED  | OVER_HARD_CAP |
| 120.00 | software | yes     | 75        | FLAGGED  | OVER_HARD_CAP |
| 20.00  | crypto   | yes     | (default 25) | APPROVED | + UNKNOWN_CATEGORY note |
| 30.00  | crypto   | yes     | (default 25) | FLAGGED  | OVER_THRESHOLD + UNKNOWN_CATEGORY |
| -5.00  | meals    | yes     | 50        | FLAGGED  | INVALID_RECORD |
| 0.00   | meals    | yes     | 50        | FLAGGED  | INVALID_RECORD |
