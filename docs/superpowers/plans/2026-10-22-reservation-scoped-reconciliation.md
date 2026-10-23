# Reservation-Scoped Cost Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile saved evaluation costs by verifying a reservation’s stored evidence chain instead of accepting a manually selected candidate.

**Architecture:** Create `day21.py` as a read-only reservation-scoped wrapper around the existing Day 17 reconciliation command. It loads and validates the finished reservation, stored plan, Day 14 report, Day 20 contexts, and candidate provenance before invoking Day 17 with the associated candidate. It saves a private linked report and never changes database state, budget capacity, release policy, or model execution.

**Tech Stack:** Python 3.11, `unittest`, psycopg PostgreSQL read-only transactions, JSON/JSONB evidence, subprocess orchestration, GitHub Actions.

## Global Constraints

- No model calls, database writes, refunds, budget releases, or release-policy changes.
- The command accepts only a reservation UUID: `python day21.py reconcile --reservation RESERVATION_UUID`.
- Only `FINISHED` reservations with an associated candidate are eligible.
- Verify the stored plan hash and saved rehearsal report hash before reconciliation.
- Verify Day 20 execution context in both the report and candidate configuration.
- Reuse `day16.canonical_hash`, `day19.validate_report`, `day19.validate_candidate`, and `day20.validate_context`.
- Use a repeatable-read, read-only PostgreSQL transaction for the association snapshot.
- Keep generated `results/day21` artifacts private and uncommitted.
- Use `VERSION = "ledger-reservation-reconciliation-v1"`.
- Use child statuses and exit codes: `RECONCILED_RECORDS: 0`, `PARTIAL: 2`, `INCONCLUSIVE: 3`.
- Do not run live reconciliation during implementation; stop after offline tests, PR creation, and hosted CI.
- Include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` in commits.

---

### Task 1: Implement reservation-scoped reconciliation

**Files:**
- Create: `day21.py`
- Reference: `day16.py`, `day17.py`, `day19.py`, `day20.py`
- Test: `day21.py` (`ReservationReconciliationTests`)

**Interfaces:**
- Consumes `connect()` from `day4`, `canonical_hash()` from `day16`, `validate_report()` and `validate_candidate()` from `day19`, and `validate_context()` from `day20`.
- Produces `sha256`, `require_finished_candidate`, `read_saved_report`, `validate_association`, `child_report_path`, `validate_child`, `reconcile`, and the `test`/`reconcile` CLI commands.
- `require_finished_candidate(state: object, candidate: object) -> uuid.UUID`.
- `read_saved_report(path: object, expected_hash: object) -> dict[str, Any]`.
- `validate_association(reservation_id: object, plan: dict[str, Any], plan_hash: object, candidate_id: uuid.UUID, exit_code: object, report: dict[str, Any]) -> None`.
- `validate_child(report: dict[str, Any], returncode: int, candidate_id: uuid.UUID, payload_hash: str) -> str`.

- [ ] **Step 1: Add the eight offline validation tests**

Create `ReservationReconciliationTests` with these exact cases:

```python
def test_finished_candidate(self):
    candidate = uuid.uuid4()
    self.assertEqual(require_finished_candidate("FINISHED", candidate), candidate)


def test_running_rejected(self):
    with self.assertRaises(ValueError):
        require_finished_candidate("RUNNING", uuid.uuid4())


def test_missing_candidate_rejected(self):
    with self.assertRaises(ValueError):
        require_finished_candidate("FINISHED", None)


def test_matching_child_report(self):
    candidate = uuid.uuid4()
    report = {
        "status": "RECONCILED_RECORDS",
        "candidate_run_id": str(candidate),
        "plan_payload_sha256": "a" * 64,
    }
    self.assertEqual(
        validate_child(report, 0, candidate, "a" * 64),
        "RECONCILED_RECORDS",
    )


def test_wrong_candidate_rejected(self):
    report = {
        "status": "PARTIAL",
        "candidate_run_id": str(uuid.uuid4()),
        "plan_payload_sha256": "a" * 64,
    }
    with self.assertRaises(ValueError):
        validate_child(report, 2, uuid.uuid4(), "a" * 64)


def test_wrong_plan_rejected(self):
    candidate = uuid.uuid4()
    report = {
        "status": "PARTIAL",
        "candidate_run_id": str(candidate),
        "plan_payload_sha256": "b" * 64,
    }
    with self.assertRaises(ValueError):
        validate_child(report, 2, candidate, "a" * 64)


def test_inconsistent_exit_rejected(self):
    candidate = uuid.uuid4()
    report = {
        "status": "RECONCILED_RECORDS",
        "candidate_run_id": str(candidate),
        "plan_payload_sha256": "a" * 64,
    }
    with self.assertRaises(ValueError):
        validate_child(report, 3, candidate, "a" * 64)


def test_inconclusive_can_lack_plan_hash(self):
    candidate = uuid.uuid4()
    report = {
        "status": "INCONCLUSIVE",
        "candidate_run_id": str(candidate),
    }
    self.assertEqual(
        validate_child(report, 3, candidate, "a" * 64),
        "INCONCLUSIVE",
    )
```

Run: `python day21.py test`

Expected: FAIL because `day21.py` does not yet exist.

- [ ] **Step 2: Implement constants and pure validation helpers**

Add:

```python
VERSION = "ledger-reservation-reconciliation-v1"
CHILD_EXIT_CODES = {
    "RECONCILED_RECORDS": 0,
    "PARTIAL": 2,
    "INCONCLUSIVE": 3,
}
```

Implement `sha256(raw)` with `hashlib.sha256(raw).hexdigest()`.

Implement `require_finished_candidate` so it rejects every state other than
`FINISHED`, rejects `None`, and returns `uuid.UUID(str(candidate))`.

Implement `read_saved_report` with these checks:

```python
if not isinstance(path, str) or not path:
    raise ValueError("Reservation has no rehearsal report path.")

root = Path("results/day14").resolve()
resolved = Path(path).resolve()
if (
    not resolved.is_relative_to(root)
    or resolved.name != "report.json"
    or not resolved.is_file()
):
    raise ValueError("Saved rehearsal report is unavailable or outside results/day14.")

raw = resolved.read_bytes()
if sha256(raw) != expected_hash:
    raise ValueError("Saved rehearsal report hash differs from the ledger.")
return json.loads(raw)
```

Implement `validate_association` to:

1. Compare `canonical_hash(plan)` to `plan_hash`.
2. Validate `report["execution_context"]` against `reservation_id` and `plan_hash`.
3. Call `validate_report(report, plan)`.
4. Require its candidate to equal `candidate_id`.
5. Require its inferred report exit code to equal the saved reservation `exit_code`.

Implement `child_report_path` to parse exactly one `Report: ` line, require a
relative `.json` path under `results/day17`, resolve it within that directory,
and reject missing or escaped files.

Implement `validate_child` so the status is one of `CHILD_EXIT_CODES`, its
expected process code matches `returncode`, and its `candidate_run_id` equals
`str(candidate_id)`. For statuses other than `INCONCLUSIVE`, require
`plan_payload_sha256 == payload_hash`; allow that field to be absent only for
`INCONCLUSIVE`.

- [ ] **Step 3: Implement the read-only reconciliation flow**

Create a unique directory:

```python
directory = Path("results/day21") / str(uuid.uuid4())
directory.mkdir(parents=True)
```

Initialize the summary with:

```python
summary = {
    "version": VERSION,
    "reservation_id": str(args.reservation),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "status": "INCONCLUSIVE",
    "association_verified": False,
    "reasons": [],
    "model_calls_made": False,
    "database_modified": False,
    "budget_capacity_released": False,
    "provider_invoice_reconciled": False,
}
```

Inside `try`, open `connect()` and a transaction, then execute:

```python
connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
```

Select these reservation columns by UUID:

```sql
SELECT budget_id, state, plan, plan_sha256,
       reserved_usd, candidate_run_id, exit_code,
       rehearsal_report, rehearsal_report_sha256
FROM ledger_spend_reservations
WHERE reservation_id = %s
```

Reject a missing row. Require a finished candidate, load the saved report,
validate the association, load `config` and `reviewed_by` from
`ledger_eval_runs`, validate the candidate context, and call:

```python
validate_candidate(config, reviewer, plan)
```

After the read-only association transaction succeeds, update the summary with
the budget ID, reservation state, reserved estimate, candidate ID, plan hash,
rehearsal path/hash, and:

```python
"association_snapshot_scope": (
    "Read-only database snapshot before Day 17 execution"
)
```

Write the stored plan to `reserved-plan.json` in the private directory. Start
Day 17 with stdout/stderr logs:

```python
[
    sys.executable,
    "day17.py",
    "reconcile",
    "--plan",
    str(plan_path),
    "--candidate",
    str(candidate_id),
]
```

Parse the child report path, hash/read the child report, validate it with
`validate_child`, and update the summary with `status`, child reasons, report
path/hash, and the embedded `cost_reconciliation`.

Catch `ValueError` into a single reason. Catch other exceptions into a reason
that identifies the exception type and points the operator to stored evidence,
policy, database access, and local logs. Always set `finished_at`, write
`report.json` with `allow_nan=False`, print association/status/reasons/report,
and return the status’s `CHILD_EXIT_CODES` value.

- [ ] **Step 4: Add the CLI**

Use required subcommands:

```python
parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
commands.add_parser("test")
command = commands.add_parser("reconcile")
command.add_argument("--reservation", required=True, type=uuid.UUID)
```

Run `ReservationReconciliationTests` at verbosity 2 for `test`; dispatch
`reconcile(args)` for the reconciliation command.

- [ ] **Step 5: Run the focused tests**

Run:

```powershell
python -m py_compile day21.py
python day21.py test
```

Expected: compilation succeeds and all eight tests pass. Do not run
`day21.py reconcile`; that is the separately scoped live operation.

- [ ] **Step 6: Commit the Day 21 implementation**

```powershell
git add day21.py
git commit -m "Add reservation-scoped cost reconciliation" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Wire CI and validate the complete offline pipeline

**Files:**
- Modify: `.github/workflows/ledger-checks.yml`
- Verify: `day21.py` and Days 5–20 test modules

**Interfaces:**
- CI compiles `day21.py`.
- CI runs `python day21.py test` after the Day 20 execution-context test.
- No live reconciliation is part of CI or this task.

- [ ] **Step 1: Update the syntax-check list**

Append `day21.py` to the existing `python -m py_compile` command:

```yaml
day13.py day14.py day15.py day16.py day17.py day18.py day19.py day20.py day21.py
```

- [ ] **Step 2: Add the Day 21 test step**

Append after the Day 20 test:

```yaml
- name: Test reservation-scoped reconciliation
  run: python day21.py test
```

- [ ] **Step 3: Run focused validation**

Run:

```powershell
python -m py_compile day21.py
python day21.py test
python day19.py test
python day20.py test
git diff --check
```

Expected: Day 21 has 8 passing tests, existing Day 19/20 suites pass, and no
whitespace errors occur.

- [ ] **Step 4: Run the complete offline suite**

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
if ($LASTEXITCODE -eq 0) { python day21.py test }
```

Expected: every command succeeds; the existing 83 offline tests plus 8 Day 21
tests pass, for 91 total before any additional regression assertions.

- [ ] **Step 5: Commit CI wiring**

```powershell
git add .github/workflows/ledger-checks.yml
git commit -m "Test reservation-scoped reconciliation in CI" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Deliver the offline-only implementation

**Files:**
- Verify: `day21.py`, `.github/workflows/ledger-checks.yml`
- Do not add: live reconciliation results or database exports

**Interfaces:**
- Branch contains the Day 21 implementation and CI wiring.
- Pull request explicitly states that no live reconciliation or model call was run.

- [ ] **Step 1: Check the final patch**

Run:

```powershell
git diff --check
git status --short
```

Expected: no diff-check errors and no generated `results/day21` artifacts
tracked or staged.

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin day13-container-bound
```

- [ ] **Step 3: Open the pull request**

```powershell
gh pr create --base main --head day13-container-bound --title "Reconcile costs through verified reservation associations" --body "Adds read-only Day 21 reservation-scoped reconciliation. It verifies stored plan/report hashes, Day 20 context, candidate provenance, and Day 17 child evidence. No live reconciliation or model calls were run."
```

- [ ] **Step 4: Verify hosted CI**

Run:

```powershell
$prNumber = gh pr view --json number --jq .number
gh pr checks $prNumber --watch
```

Expected: Offline tests and GitGuardian checks pass; the release-check job is
skipped because this is not a workflow dispatch.

- [ ] **Step 5: Stop before live reconciliation**

Do not run:

```powershell
python day21.py reconcile --reservation ...
```

Live reconciliation requires separate explicit approval and a confirmed
finished Day 20 reservation with a usable read-only database connection.
