# Reservation-Bound Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate a validated reservation context through generation, candidate, and rehearsal evidence, then require that binding before Day 18 finalization or Day 19 recovery.

**Architecture:** Add an independent `day20.py` module that normalizes reservation UUIDs and plan SHA-256 hashes, reads the context only from reserved child-process environment variables, and validates saved candidate configuration through a database connection. Day 18 injects the context into the Day 16 child; Day 13, Day 7, and Day 14 preserve it; Day 18 and Day 19 enforce it before accepting evidence. Unreserved Day 14 runs remain valid but cannot finalize or recover a reservation.

**Tech Stack:** Python 3.11, `unittest`, psycopg PostgreSQL access, JSON/JSONB evidence, Docker subprocess orchestration, GitHub Actions.

## Global Constraints

- Do not run a fresh paid rehearsal or make model calls during this implementation.
- Use `VERSION = "ledger-execution-context-v1"` for the shared context.
- Require both `LEDGER_SPEND_RESERVATION_ID` and `LEDGER_SPEND_PLAN_SHA256` together; both absent means explicitly unbound.
- Reject incomplete or malformed context before application calls.
- Preserve existing conservative behavior: failed association leaves reservations consumed and unresolved.
- Do not manufacture execution context for historical reports.
- No database migration or dependency-image rebuild is required.
- Include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` in commits.
- Use Windows paths in local commands where paths are absolute; repository-relative Python and workflow paths stay as shown.

---

### Task 1: Create the shared execution-context module

**Files:**
- Create: `day20.py`
- Test: `day20.py` (`ExecutionContextTests`)

**Interfaces:**
- Produces `VERSION`, `RESERVATION_ENV`, `PLAN_ENV`, `make_context`, `context_from_environment`, `validate_context`, and `require_candidate_context`.
- `make_context(reservation_id: object, plan_sha256: object) -> dict[str, str]`.
- `context_from_environment(environment: Mapping[str, str] | None = None) -> dict[str, str] | None`.
- `validate_context(stored: object, reservation_id: object, plan_sha256: object) -> dict[str, str]`.
- `require_candidate_context(connection: Any, candidate_id: uuid.UUID, reservation_id: object, plan_sha256: object) -> None`.

- [ ] **Step 1: Add failing tests for all eight context behaviors**

Add these test methods to `ExecutionContextTests`:

```python
def test_unbound_execution(self):
    self.assertIsNone(context_from_environment({}))

def test_complete_environment(self):
    context = context_from_environment({
        RESERVATION_ENV: self.reservation(),
        PLAN_ENV: self.digest(),
    })
    self.assertEqual(context["reservation_id"], self.reservation())

def test_partial_environment_rejected(self):
    with self.assertRaises(ValueError):
        context_from_environment({RESERVATION_ENV: self.reservation()})

def test_empty_environment_value_rejected(self):
    with self.assertRaises(ValueError):
        context_from_environment({
            RESERVATION_ENV: "",
            PLAN_ENV: self.digest(),
        })

def test_invalid_hash_rejected(self):
    with self.assertRaises(ValueError):
        make_context(self.reservation(), "not-a-hash")

def test_matching_context(self):
    context = make_context(self.reservation(), self.digest())
    self.assertEqual(
        validate_context(context, self.reservation(), self.digest()),
        context,
    )

def test_wrong_reservation_rejected(self):
    context = make_context(self.reservation(), self.digest())
    with self.assertRaises(ValueError):
        validate_context(context, uuid.uuid4(), self.digest())

def test_missing_candidate_binding_rejected(self):
    from unittest.mock import Mock
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (
        {"execution_context": None},
    )
    with self.assertRaises(ValueError):
        require_candidate_context(
            connection, uuid.uuid4(), self.reservation(), self.digest()
        )
```

Run: `python day20.py test`

Expected: FAIL because the context functions and test module do not yet exist.

- [ ] **Step 2: Implement context normalization and validation**

Implement the constants and functions with these exact rules:

```python
VERSION = "ledger-execution-context-v1"
RESERVATION_ENV = "LEDGER_SPEND_RESERVATION_ID"
PLAN_ENV = "LEDGER_SPEND_PLAN_SHA256"
```

Normalize UUIDs using `str(uuid.UUID(str(reservation_id)))`. Require the plan hash to match `[0-9a-f]{64}` using `re.fullmatch`. Return:

```python
{
    "version": VERSION,
    "reservation_id": normalized_uuid,
    "plan_sha256": plan_sha256,
}
```

`context_from_environment` must return `None` only when both variables are absent; reject one missing, empty values, or invalid values. `validate_context` must compare the complete stored dictionary to `make_context(...)`. `require_candidate_context` must query `SELECT config FROM ledger_eval_runs WHERE run_id = %s`, reject missing/non-dict rows, and validate `config.get("execution_context")`.

- [ ] **Step 3: Add the `test` CLI**

Use `argparse` with one `test` command, run `ExecutionContextTests` at verbosity 2, and exit 0 only when `result.wasSuccessful()` is true.

- [ ] **Step 4: Run the focused tests**

Run: `python day20.py test`

Expected: 8 tests pass.

- [ ] **Step 5: Commit the isolated module**

```powershell
git add day20.py
git commit -m "Add reservation execution context validation" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Preserve context in generated and candidate evidence

**Files:**
- Modify: `day13.py: imports and generate`
- Modify: `day7.py: evaluate config construction`
- Modify: `day14.py: imports and rehearsal report initialization`

**Interfaces:**
- Consumes `context_from_environment() -> dict[str, str] | None` from Task 1.
- Produces `execution_context` in generation manifests, saved candidate configs, and Day 14 reports.

- [ ] **Step 1: Stamp the Day 13 generation manifest**

Add:

```python
from day20 import context_from_environment
```

At the beginning of `generate`, before `clean_commit()` or any application call, assign:

```python
execution_context = context_from_environment()
```

When replacing the existing container-binding assignment, write both fields before replacing the artifact:

```python
manifest["container_binding"] = binding
manifest["execution_context"] = execution_context
```

- [ ] **Step 2: Preserve the manifest context in Day 7**

In `evaluate`, add this entry beside the existing provenance/runtime/container fields:

```python
"execution_context": manifest.get("execution_context"),
```

This must be included in the JSONB `config` inserted into `ledger_eval_runs`.

- [ ] **Step 3: Stamp the Day 14 report**

Add the `day20` import. Immediately after the main `try:` in `rehearsal`, before required-secret checks, assign:

```python
report["execution_context"] = context_from_environment()
```

This ensures early failures retain a valid context while ordinary runs record `None`.

- [ ] **Step 4: Run affected offline tests**

Run:

```powershell
python day13.py test
python day14.py test
```

Expected: the existing Day 13 and Day 14 test suites pass without model calls.

- [ ] **Step 5: Commit evidence propagation**

```powershell
git add day7.py day13.py day14.py
git commit -m "Preserve reservation context in evaluation evidence" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Inject context and enforce Day 18 finalization

**Files:**
- Modify: `day18.py: imports and run`
- Verify: `day18.py` existing `ReservationTests`

**Interfaces:**
- Consumes `PLAN_ENV`, `RESERVATION_ENV`, `validate_context`, and `require_candidate_context` from `day20.py`.
- Produces child-process environment values derived from the locked stored reservation.
- Leaves state `UNKNOWN` when report or candidate context does not match.

- [ ] **Step 1: Inject context only into the Day 16 child**

After loading and hash-validating the stored plan, create:

```python
child_environment = os.environ.copy()
child_environment[RESERVATION_ENV] = str(args.reservation)
child_environment[PLAN_ENV] = digest
```

Pass `env=child_environment` to the existing `subprocess.run` call that launches `day16.py`. Do not export these variables in the parent shell or alter ordinary unreserved commands.

- [ ] **Step 2: Require report and candidate context before finalization**

After loading the Day 14 report and before calculating the finalization fields, run:

```python
validate_context(
    report.get("execution_context"),
    args.reservation,
    digest,
)
candidate = associate(report, plan, code)

if candidate is not None:
    with connect() as connection:
        require_candidate_context(
            connection,
            candidate,
            args.reservation,
            digest,
        )
```

Keep report hashing and the existing `FINISHED`/`UNKNOWN` update logic unchanged. Any exception must follow the existing catch path and leave the reservation consumed.

- [ ] **Step 3: Run Day 18 tests**

Run: `python day18.py test`

Expected: the existing 6 tests pass without model calls.

- [ ] **Step 4: Commit Day 18 enforcement**

```powershell
git add day18.py
git commit -m "Require reservation context before finalization" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Enforce context during Day 19 recovery

**Files:**
- Modify: `day19.py: imports, recover`
- Test: `day19.py` (`RecoveryTests`)

**Interfaces:**
- Consumes `require_candidate_context` and `validate_context` from `day20.py`.
- Produces recovery audit evidence containing the validated `execution_context`.
- Preserves row locking and the one-transaction audit/update behavior.

- [ ] **Step 1: Validate the report context before existing report checks**

Import the Day 20 functions and, inside the locked recovery transaction, immediately before `validate_report` add:

```python
validate_context(
    report.get("execution_context"),
    args.reservation,
    plan_hash,
)
candidate, code = validate_report(report, plan)
```

This intentionally makes historical reports without context unrecoverable.

- [ ] **Step 2: Validate candidate context and record it in audit evidence**

Inside the existing `if candidate is not None:` block, after `validate_candidate(...)`, call:

```python
require_candidate_context(
    connection,
    candidate,
    args.reservation,
    plan_hash,
)
```

Add `"execution_context": report["execution_context"]` to the `evidence` dictionary before inserting the audit row. Do not change reservation amount or budget rows.

- [ ] **Step 3: Run Day 19 tests**

Run: `python day19.py test`

Expected: the existing 7 tests pass without database access.

- [ ] **Step 4: Commit Day 19 enforcement**

```powershell
git add day19.py
git commit -m "Require reservation context during recovery" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Wire CI, run the complete offline suite, and deliver

**Files:**
- Modify: `.github/workflows/ledger-checks.yml`
- Verify: `day7.py`, `day13.py`, `day14.py`, `day18.py`, `day19.py`, `day20.py`

**Interfaces:**
- CI compiles `day20.py`.
- CI runs `python day20.py test` after the Day 19 recovery test.
- Delivery ends before any paid rehearsal.

- [ ] **Step 1: Update CI syntax and test steps**

Add `day20.py` to the `py_compile` command and add:

```yaml
- name: Test execution context
  run: python day20.py test
```

- [ ] **Step 2: Run focused validation**

Run:

```powershell
python -m py_compile day7.py day13.py day14.py day18.py day19.py day20.py
python day18.py test
python day19.py test
python day20.py test
```

Expected: 6 + 7 + 8 focused tests pass.

- [ ] **Step 3: Run the complete offline suite**

Run:

```powershell
$ErrorActionPreference = 'Stop'
python day5.py test
if ($LASTEXITCODE -eq 0) { python day6.py test }
if ($LASTEXITCODE -eq 0) { python day8.py test }
if ($LASTEXITCODE -eq 0) { python day9.py test }
if ($LASTEXITCODE -eq 0) { python day11.py test }
if ($LASTEXITCODE -eq 0) { python day12.py test }
if ($LASTEXITCODE -eq 0) { python day13.py test }
if ($LASTEXITCODE -eq 0) { python day14.py test }
if ($LASTEXITCODE -eq 0) { python day15.py test }
if ($LASTEXITCODE -eq 0) { python day16.py test }
if ($LASTEXITCODE -eq 0) { python day17.py test }
if ($LASTEXITCODE -eq 0) { python day18.py test }
if ($LASTEXITCODE -eq 0) { python day19.py test }
if ($LASTEXITCODE -eq 0) { python day20.py test }
```

Expected: every command succeeds; the suite includes the existing 75 tests plus 8 Day 20 tests and any added propagation assertions.

- [ ] **Step 4: Check the patch**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Commit CI wiring and push**

```powershell
git add day7.py day13.py day14.py day18.py day19.py day20.py .github/workflows/ledger-checks.yml
git commit -m "Bind rehearsal and candidate evidence to spend reservations" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

Expected: branch is pushed with no untracked generated results.

- [ ] **Step 6: Open the pull request and verify CI**

Use:

```powershell
gh pr create --base main --head day13-container-bound --title "Bind rehearsal and candidate evidence to spend reservations" --body "Adds reservation execution context propagation and strict finalization/recovery checks. No paid rehearsal was run."
gh pr checks <PR_NUMBER> --watch
```

Expected: offline tests and security checks pass. Stop here; do not create a new plan, reservation, or paid rehearsal in this implementation task.
