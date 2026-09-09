# REVIEW.md — PR review policy (Stage 5: Deploy)

This file defines how PRs are reviewed in this repo. It is the policy the
automated review pass (`/code-review`, or a tagged `@claude`) enforces, and the
checklist a human uses before signing off. It is version-controlled so the
standard is the same for every PR.

The **source of truth for behavior is [`spec.md`](spec.md)** (see
[`CLAUDE.md`](CLAUDE.md)). When code and spec disagree, the spec wins — or the
spec is amended first, in the same PR, with its §11 matrix row and test updated.

## How to run a review

```bash
# On a GitHub PR:
/code-review <PR#>            # ranked findings for the PR diff
/code-review ultra <PR#>      # deeper multi-agent cloud review
# Tag @claude on a PR comment to request fixes for specific findings.
```

A PR is mergeable only when: CI is green (`Ran 40 tests ... OK`), every
**Blocking** finding is resolved, and a human other than the author has
signed off. **The agent never approves its own PR and never clears the
production gate** (spec §6 / playbook Stage 5).

## Severity levels

- **Blocking** — must be fixed before merge. Violates the spec, the decision
  table, the test matrix, or a hard invariant below.
- **Major** — fix before merge unless the author documents an explicit,
  spec-consistent reason in the PR.
- **Minor** — style/readability/naming. Note it; does not block merge.

## Blocking invariants (from spec + CLAUDE.md)

A finding is **Blocking** if the change does any of the following:

1. **Impurity in the engine.** `decide(record, policy) -> Decision` in
   [`engine.py`](expense_approver/engine.py) does I/O, reads a clock other than
   the injectable `decided_at`, or is otherwise non-deterministic (spec §6).
2. **Storage leaks into the engine.** The engine imports or references a
   backend (`CsvRepository`, `SqliteRepository`, `sqlite3`, file handles). It
   must stay storage-agnostic behind the `Repository` interface.
3. **`float` used for money.** Any amount or amount comparison not done as
   `Decimal` quantized to cents with `ROUND_HALF_UP` (spec §8.7).
4. **A record is silently dropped.** Every input must yield exactly one
   APPROVED / FLAGGED record, or be routed to the errors output —
   `input_count == approved + flagged + errors` (intent + spec §10.1).
5. **Boundary convention changed.** The asymmetry is deliberate (spec §5.2 / Q5):
   flag the **category threshold on `>=`**, flag the **hard cap on `>`**.
   $75.00 may auto-approve; `amount == threshold` is FLAGGED. Do not "fix" it.
6. **Hard-cap ceiling weakened.** The `$75` cap is a global ceiling; category
   thresholds above it must be rejected at policy load (spec §5.1 / Q4).
7. **Third-party dependency added.** Runtime and tests are **standard library
   only** (spec / `pyproject.toml`: `dependencies = []`).
8. **Policy behavior changed without versioning.** Any change to decision
   behavior must bump `policy_version` in [`policy.json`](policy.json) and
   update the affected [spec §11](spec.md) matrix row **and** its test in
   [`tests/test_engine.py`](tests/test_engine.py) in the same PR (CLAUDE.md).
9. **Tests weakened to pass code.** Tests were relaxed/deleted to make buggy
   code pass, rather than the code fixed to pass the test. `tests/**` changes
   are legitimate only as a deliberate, spec-backed amendment (see the
   `protect_tests.py` hook).
10. **Decision-table / matrix regression.** Any case in spec §9 (Q1–Q7) or the
    §11 matrix now produces a different result, without a matching spec amendment.

## Major (fix unless justified)

- New behavior added without a spec §11 matrix row and a corresponding test.
- Acceptance criteria (spec §10) not all satisfied by the change.
- CSV and SQLite backends could diverge on identical data (spec §10, item 4).
- Missing boundary tests for a newly-touched threshold.

## Minor

- Naming, comments, and structure that don't match surrounding code.
- Non-behavioral refactors that don't affect the decision path.

## Reviewer checklist

- [ ] CI green: `py -m unittest discover -s tests -t . -v` ends in `OK`.
- [ ] No Blocking invariant violated.
- [ ] Spec / §11 matrix / `test_engine.py` updated together for any behavior change.
- [ ] `policy_version` bumped if decision behavior changed.
- [ ] Human (not the author, not the agent) has signed off.
