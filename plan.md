# Plan: Stage 3 (Build) — Expense-Report Approval Tool

> **AI-native SDLC, Stage 3 (Build) artifact.** This is the accepted implementation
> plan for turning the reviewed [`spec.md`](spec.md) (itself derived from
> [`intent.md`](intent.md)) into working code. Per the playbook's rule —
> *"nothing is implemented without an accepted plan"* — this plan was accepted
> before code generation. See the "Build outcome" section for what was delivered.

## Context

Stages 1–2 are complete: `intent.md` (approved intent) and `spec.md` (reviewed,
all open questions resolved). Stage 3 builds a working, tested Python tool that
ingests expense records, applies the deterministic policy engine, and writes each
record back as `APPROVED` or `FLAGGED` with a reason — with both CSV and SQLite
backends, JSON-configured policy, and a test suite proving the spec's acceptance
criteria (§10) and test matrix (§11).

**Decisions locked in with the owner:** Python, standard library only (`csv`,
`sqlite3`, `decimal`, `json`, `argparse`); full spec v1 (both backends behind one
repository interface).

## Approach

A small package with a **pure decision function** at its core (`decide(record,
policy) -> Decision`, spec §4), wrapped by storage-agnostic repositories (CSV +
SQLite behind one interface, spec §2.3) and a thin CLI. Money is handled as
`Decimal` quantized to 2 places with `ROUND_HALF_UP` (spec §8.7) — never float —
so the $75 / threshold boundaries are exact.

### File layout

```
expense_approver/
  __init__.py
  models.py        # RawRecord, Decision, ParseError, Status/ReasonCode enums (§2)
  parsing.py       # field normalization + parsers (amount, receipt, category, id; §8)
  policy.py        # Policy dataclass + load_policy(path) with §5.1/§7 validation
  engine.py        # decide(record, policy) -> Decision   (pure, §4.2)
  repository.py    # Repository ABC; CsvRepository; SqliteRepository; run() (§2.3, §6)
  summary.py       # RunSummary accumulate + render (§3.3)
  cli.py           # argparse entrypoint: wire repo + engine + summary
  __main__.py      # enables `py -m expense_approver`
tests/             # stdlib unittest suite (see Build outcome for the pytest note)
  support.py, test_engine.py, test_parsing.py, test_policy.py,
  test_repository_csv.py, test_repository_sqlite.py, test_acceptance.py
policy.json        # default v1 policy (spec §7, verbatim)
examples/sample.csv# spec §3.1 sample input
pyproject.toml     # package metadata (no runtime deps)
README.md, CLAUDE.md
```

### Key implementation notes (traceable to the spec)

- **Engine order (§4.2), short-circuit to first failing hard rule:**
  1. Validate → `INVALID_RECORD` on missing/malformed required field, non-numeric
     amount, `amount < 0`, **or `amount == 0`** (§8.2 / Q7).
  2. `amount > 75.00` → `OVER_HARD_CAP`.
  3. receipt not true → `NO_RECEIPT`.
  4. `amount >= category_threshold` → `OVER_THRESHOLD` (inclusive flag, §5.2/Q5).
  5. else `APPROVED`.
  Cap uses `>` (exactly $75.00 can pass); threshold uses `>=` — the deliberate
  asymmetry from §5.2. Each record decided in isolation (order-independent, §6).
- **Policy load + validation (§7, §5.1/Q4):** parse `policy.json`; when
  `reject_thresholds_above_hard_cap` is true, `load_policy` raises on any category
  threshold above `hard_cap` (fail at load, not silently dead). `default_threshold`
  ($25) applies to unknown categories.
- **Unknown category (§4.3):** default threshold **and** an `UNKNOWN_CATEGORY`
  note, attached only at the threshold step so a record short-circuited earlier
  does not carry it (matches the §11 matrix).
- **Parsing/normalization (§8.6):** `category` trimmed + lower-cased; `receipt`
  accepts `true/false,yes/no,1/0,y/n` case-insensitively; `amount` tolerates
  whitespace and a leading `$`.
- **IDs (§8.1):** missing `id` → `ROW-<n>` by input position; duplicate ids not
  de-duped, counted as a warning in the summary.
- **Decision record (§2.2):** append `status`, `reason`, `decided_at` (UTC
  ISO-8601), `policy_version`. CSV writes a new `<input>.decided.csv` (never
  overwrites input); SQLite updates rows in place.
- **Unparseable rows (§8.4):** routed to `<input>.errors.csv` / an
  `expenses_errors` table with the raw line + message, counted as ERRORS.
- **Run summary (§3.3):** processed/approved/flagged/errors + flag-reason
  breakdown + policy version.

### One spec ambiguity — flagged, with chosen default

§2.2 says `reason` is "empty when APPROVED," but the §11 matrix shows an
**APPROVED** unknown-category row carrying an `UNKNOWN_CATEGORY` note (`20.00
crypto yes → APPROVED + UNKNOWN_CATEGORY`), and §4.4 calls `UNKNOWN_CATEGORY` a
*note that may accompany* a decision. **Chosen default:** emit `UNKNOWN_CATEGORY`
in the `reason` field whenever the category is unknown, regardless of status —
matching §11 and §4.4. A one-line change if the owner prefers a separate `notes`
column or a strictly-empty approved reason.

## Verification

1. **Test suite:** `py -m unittest discover -s tests -t .` — the full §11 matrix,
   the §10.8 boundary set, config rejection of thresholds > cap, and the §10
   acceptance criteria (conservation + no null status §10.1, CSV/SQLite parity
   §10.4, idempotent re-runs §10.5).
2. **CSV end-to-end:** `py -m expense_approver --backend csv --input examples/sample.csv --policy policy.json`
   → output matches spec §3.2, summary matches §3.3.
3. **SQLite end-to-end:** seed a db, run twice, confirm identical decisions and an
   idempotent second run.
4. **Config rejection:** a policy with a category threshold of $150 makes the
   loader error (Q4 guarantee).

## Build outcome

Delivered and verified: **40 tests pass**; CSV output matches spec §3.2/§3.3
exactly; SQLite produces identical decisions (parity) and re-runs idempotently;
the loader rejects thresholds above the cap. Two deviations/robustness additions
made during the build:

- **Tests use the stdlib `unittest` runner, not pytest** — keeps the tool
  dependency-free (the plan's "stdlib only"); no install step needed.
- **BOM tolerance:** policy JSON and input CSV are read as `utf-8-sig` so a
  Windows-added UTF-8 BOM does not corrupt loading. The run summary also prints
  the policy version on a zero-record run.
