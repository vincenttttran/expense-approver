# CLAUDE.md — institutional knowledge

Guidance for Claude (and humans) working in this repo. This is a playbook input:
Stage 3 (Build) reads it, and later stages (Test, Deploy, Operate) build on it.

## What this project is

An expense-report approval tool built via the AI-native SDLC:
`intent.md` → `spec.md` → `plan.md` → code. **`spec.md` is the source of truth**
for behavior; when code and spec disagree, the spec wins (or the spec is amended
first). Every open question in the spec is resolved in its §9 decision table —
honor those rulings.

## Architecture

- `expense_approver/engine.py` — `decide(record, policy) -> Decision` is a **pure
  function** and the heart of the tool. Keep it pure and deterministic (spec §6):
  no I/O, no clock except the injectable `decided_at`. All rule logic lives here.
- `expense_approver/repository.py` — storage behind one `Repository` interface
  (`CsvRepository`, `SqliteRepository`); the `run()` orchestration wires a repo to
  the engine. The engine must stay storage-agnostic — never import a backend into it.
- `expense_approver/policy.py` — config load + validation. The `$75` hard cap is a
  global ceiling; category thresholds above it are rejected at load (spec §5.1/Q4).
- `models.py`, `parsing.py`, `summary.py`, `cli.py` — data model, field parsing,
  run summary, CLI.

## Conventions

- **Money is `Decimal`, quantized to cents with `ROUND_HALF_UP`** (spec §8.7).
  Never use `float` for amounts or comparisons.
- **Nothing is silently dropped** (intent + spec §10.1): a record is APPROVED,
  FLAGGED, or (if unparseable) routed to the errors output — always accounted for.
- Boundary convention is deliberately asymmetric (spec §5.2/Q5): flag the category
  threshold on `>=`, flag the hard cap on `>`. Don't "fix" it to match.
- Standard library only — no third-party runtime or test dependencies.

## Commands

```bash
py -m unittest discover -s tests -t . -v                 # run all tests
py -m expense_approver --backend csv --input F --policy policy.json
py -m expense_approver --backend sqlite --db F --policy policy.json
```

**Healthy test output** (the target to validate against — a run is only
"green" when it ends like this):

```
----------------------------------------------------------------------
Ran 40 tests in 0.10s

OK
```

Anything other than a trailing `OK` (a `FAILED (...)`, an error, or a
different test count without a matching spec/matrix change) means the
change is not done.

## Testing / Stage 4 (Test)

Verification is continuous, not a final gate: run the single test command
above after every change and iterate until the healthy output appears
**before** surfacing code for human review. Concrete pass/fail targets live
in the spec's §11 test matrix and §9 decision table; `test_spec_11_matrix`
enforces them.

- **`tests/**` is read-only during fixes.** A `PreToolUse` hook
  (`.claude/hooks/protect_tests.py`, wired in `.claude/settings.json`) blocks
  the agent from editing test files while fixing a bug — fix the code to pass
  the test, never the reverse.
- **Re-run evals whenever configuration changes.** Editing `policy.json`,
  this `CLAUDE.md`, `spec.md`, or the hooks/settings is a config change: run
  the full suite again, and for policy/spec changes also update the affected
  §11 matrix row and its `tests/test_engine.py` test in the same step.
- **Production incidents become permanent test cases** — reproduce any
  escaped defect as a failing test first, then fix, so it can't recur.

## When changing policy behavior

Bump `policy_version` in `policy.json` so historical decisions stay explainable
(spec §6). Add/adjust the corresponding row in the spec's §11 test matrix and its
test in `tests/test_engine.py`.
