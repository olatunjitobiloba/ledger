# Portable Reservation Evidence Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only export/restore utility that carries a finished reservation’s verified plan and exact Day 14 rehearsal report between machines without overwriting conflicting evidence.

**Architecture:** Create a standalone `day22.py` module that reuses Day 16/19/20/21 validation helpers. Separate pure path, hash, manifest, ZIP, and atomic-publication helpers from database-backed export/restore orchestration; all database transactions use repeatable-read, read-only snapshots. The archive is exactly three JSON members, and restore validates the archive against the receiving ledger before publishing only to the ledger-approved Day 14 report path.

**Tech Stack:** Python 3.11, standard library (`argparse`, `hashlib`, `json`, `tempfile`, `unittest`, `uuid`, `zipfile`, `pathlib`), existing `psycopg` connection helpers, PostgreSQL read-only transactions, GitHub Actions.

## Global Constraints

- Use `VERSION = "ledger-evidence-bundle-v1"`.
- Use exactly `MEMBERS = {"manifest.json", "plan.json", "rehearsal.json"}`.
- Reject any archive over `MAX_ARCHIVE_BYTES = 32 * 1024 * 1024`.
- Reject any expanded member over `MAX_MEMBER_BYTES = 8 * 1024 * 1024`.
- Export only `FINISHED` reservations with associated candidates.
- Reuse `day4.connect`, `day16.canonical_hash`, `day19.validate_candidate`, `day20.validate_context`, `day21.require_finished_candidate`, and `day21.validate_association`.
- Never make model calls, database writes, retries, refunds, release-policy changes, or archive-signing changes.
- Preserve rehearsal report bytes exactly; do not reserialize the report.
- Archive paths are untrusted; never extract archive-controlled paths directly.
- Restore only to `results/day14/<rehearsal UUID>/report.json`.
- Allow identical existing evidence; reject different existing evidence without replacing it.
- Publish archives and reports atomically with no-overwrite semantics; fail rather than falling back to overwrite-prone writes.
- Keep generated archives and restored evidence private and uncommitted.
- Offline tests must not require PostgreSQL, Docker, model credentials, real reservations, or external storage.
- Run Python 3.11-compatible syntax, focused tests, the full offline suite, and `git diff --check`.

---

## File Map

- Create: `day22.py`
  - Constants, pure validation helpers, archive creation/reading, safe
    no-overwrite publication, database-backed export/restore commands, and
    eight embedded offline tests.
- Modify: `.github/workflows/ledger-checks.yml`
  - Compile `day22.py` and execute `python day22.py test` in the offline job.
- Create: `docs/superpowers/specs/2026-10-22-portable-evidence-bundle-design.md`
  - Already completed and committed; implementation must follow this approved
    design and must not edit the specification during implementation.

## Interfaces

The implementation must expose these testable helpers in `day22.py`:

```python
def sha256(raw: bytes) -> str: ...
def validate_report_path(path: object, *, must_exist: bool) -> Path: ...
def canonical_plan_bytes(plan: dict[str, Any]) -> bytes: ...
def manifest_bytes(manifest: dict[str, Any]) -> bytes: ...
def build_archive(
    manifest: dict[str, Any],
    plan_bytes: bytes,
    rehearsal_bytes: bytes,
) -> bytes: ...
def read_archive_from_bytes(
    archive_bytes: bytes,
) -> tuple[dict[str, Any], bytes, bytes]: ...
def read_archive(path: Path) -> tuple[dict[str, Any], bytes, bytes]: ...
def publish_no_overwrite(path: Path, content: bytes) -> str: ...
```

`export(args: argparse.Namespace) -> int` and
`restore(args: argparse.Namespace) -> int` are CLI handlers. `main()` must
support:

```text
python day22.py test
python day22.py export --reservation RESERVATION_UUID --output PATH.zip
python day22.py restore --bundle PATH.zip
```

### Task 1: Add pure bundle primitives and failing tests

**Files:**
- Create: `day22.py`

**Interfaces:**
- Consumes: standard-library bytes, paths, JSON objects, and archive data.
- Produces: bounded archive validation, canonical plan bytes, manifest hashes,
  safe report-path resolution, and no-overwrite publication helpers for the
  export/restore tasks.

- [ ] **Step 1: Add the module shell, constants, and imports**

Create the module with the required constants and imports:

```python
VERSION = "ledger-evidence-bundle-v1"
MEMBERS = {"manifest.json", "plan.json", "rehearsal.json"}
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
```

Import the existing validation boundaries and standard-library primitives
without adding dependencies:

```python
from day4 import connect
from day16 import canonical_hash
from day19 import validate_candidate
from day20 import validate_context
from day21 import require_finished_candidate, validate_association
```

- [ ] **Step 2: Write the eight offline tests before implementation**

Add a `PortableEvidenceBundleTests(unittest.TestCase)` class covering these
behaviors with `TemporaryDirectory`, `BytesIO`, and `zipfile.ZipFile`:

```python
def test_canonical_report_path_is_accepted(self):
    path = Path("results/day14") / str(self.rehearsal_id) / "report.json"
    self.assertEqual(validate_report_path(path, must_exist=False), path.resolve())

def test_report_path_traversal_is_rejected(self):
    with self.assertRaises(ValueError):
        validate_report_path(Path("results/day14") / ".." / "secret" / "report.json",
                             must_exist=False)

def test_absolute_report_path_is_rejected(self):
    with self.assertRaises(ValueError):
        validate_report_path(Path.cwd() / "results/day14" / str(self.rehearsal_id)
                             / "report.json", must_exist=False)

def test_report_hash_mismatch_is_rejected(self):
    with self.assertRaises(ValueError):
        verify_member_hash(b"actual", "0" * 64)

def test_matching_manifest_hashes_are_accepted(self):
    self.assertEqual(verify_member_hash(b"actual", sha256(b"actual")), sha256(b"actual"))

def test_identical_existing_output_is_reused(self):
    with TemporaryDirectory() as directory:
        target = Path(directory) / "bundle.zip"
        target.write_bytes(b"same")
        self.assertEqual(publish_no_overwrite(target, b"same"), "ALREADY_PRESENT")

def test_different_existing_output_is_not_replaced(self):
    with TemporaryDirectory() as directory:
        target = Path(directory) / "report.json"
        target.write_bytes(b"original")
        with self.assertRaises(ValueError):
            publish_no_overwrite(target, b"different")
        self.assertEqual(target.read_bytes(), b"original")

def test_unexpected_archive_member_is_rejected(self):
    archive = make_test_archive({"unexpected.txt": b"bad"})
    with self.assertRaises(ValueError):
        read_archive_from_bytes(archive)
```

Use a fixed UUID fixture and create temporary roots or patch the module’s
report-root helper so path tests do not touch repository evidence. The test
names may follow the repository’s existing style, but each must assert the
specific safety behavior above.

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```powershell
python day22.py test
```

Expected: test collection or execution fails because the new helpers and
module implementation do not yet exist. Do not treat an absent command as a
passing result.

- [ ] **Step 4: Implement path, hash, JSON, and publication helpers**

Implement:

```python
def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def verify_member_hash(raw: bytes, expected: object) -> str:
    actual = sha256(raw)
    if expected != actual:
        raise ValueError("Evidence member hash differs from the manifest.")
    return actual
```

`validate_report_path` must resolve only under `Path("results/day14").resolve()`,
require the final name `report.json`, reject absolute inputs, `..`, Windows
separators, non-UUID parent directory names, and symlinked path components.
When `must_exist=True`, require a regular file.

`canonical_plan_bytes` must serialize the plan using sorted keys, compact
separators, UTF-8, and `allow_nan=False`; verify its `canonical_hash` wherever
the plan hash is checked. `manifest_bytes` must use the same deterministic
JSON encoding and include `"signed": False`.

`publish_no_overwrite` must create parent directories, compare an existing
regular file byte-for-byte and return `"ALREADY_PRESENT"` only for identical
content, reject different content, write a uniquely named temporary file in
the destination directory, flush and close it, and publish with `os.link`.
If hard-link publication is unsupported or races with another publisher, raise
`ValueError` and do not replace the destination.

- [ ] **Step 5: Implement bounded exact-member archive handling**

Implement `build_archive` and `read_archive` using `zipfile.ZipFile`:

- reject input archive files larger than `MAX_ARCHIVE_BYTES`;
- reject encrypted entries, directories, duplicate names, unexpected names,
  missing names, and member compressed/uncompressed sizes over the defined
  limits;
- read members into memory only after all bounds pass;
- parse `manifest.json` as an object;
- verify the manifest version, `"signed": False`, and SHA-256 values for
  `plan.json` and `rehearsal.json`;
- never call `extract()` or use any archive member name as a filesystem path.

`build_archive` must write exactly the three required members and reject any
member over `MAX_MEMBER_BYTES` or any final archive over
`MAX_ARCHIVE_BYTES`.

- [ ] **Step 6: Run the focused tests and commit the primitives**

Run:

```powershell
python day22.py test
python -m py_compile day22.py
git diff --check
```

Expected: all eight tests pass, compilation succeeds, and there are no
whitespace errors.

Commit:

```powershell
git add day22.py
git commit -m "feat: add portable evidence bundle primitives" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement verified reservation export

**Files:**
- Modify: `day22.py`

**Interfaces:**
- Consumes: `build_archive`, `publish_no_overwrite`, Day 18 reservation rows,
  Day 14 report bytes, and existing Day 19/20/21 validators.
- Produces: `export(args) -> int`, which creates a three-member archive only
  after a read-only ledger snapshot verifies the complete association.

- [ ] **Step 1: Add the export command parser**

Add an `export` subparser requiring:

```python
command.add_argument("--reservation", required=True, type=uuid.UUID)
command.add_argument("--output", required=True, type=Path)
```

Dispatch `export(args)` from `main()` and return its integer status.

- [ ] **Step 2: Read and validate the reservation in a read-only snapshot**

Within `connect()` and a transaction, execute:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY
```

Select `state`, `plan`, `plan_sha256`, `candidate_run_id`, `exit_code`,
`rehearsal_report`, and `rehearsal_report_sha256` from
`ledger_spend_reservations` by UUID. Use
`require_finished_candidate` and `canonical_hash` to require a finished
candidate-associated reservation and a matching stored plan hash.

Read the report using the validated Day 14 path, preserving raw bytes. Verify
its ledger hash, parse it as an object, and call `validate_association` with
the reservation ID, plan, plan hash, candidate ID, exit code, and report.

Select the candidate `config` and `reviewed_by` from `ledger_eval_runs`.
Require the row, validate its execution context with `validate_context`, and
validate candidate provenance with `validate_candidate`.

- [ ] **Step 3: Build the manifest from trusted values**

Create a manifest containing at least:

```python
{
    "version": VERSION,
    "signed": False,
    "reservation_id": str(reservation_id),
    "candidate_run_id": str(candidate_id),
    "plan_sha256": plan_hash,
    "rehearsal_report": report_path,
    "rehearsal_report_sha256": sha256(report_bytes),
    "plan_file_sha256": sha256(plan_bytes),
    "rehearsal_file_sha256": sha256(report_bytes),
}
```

Use the reserved plan’s canonical bytes for `plan.json`, and the exact saved
report bytes for `rehearsal.json`. Reject any mismatch before archive creation.

- [ ] **Step 4: Publish the archive atomically without overwriting**

Call `build_archive` and `publish_no_overwrite(args.output, archive_bytes)`.
Print the output path and whether it was newly published or
`ALREADY_PRESENT`. Do not create or modify database rows.

- [ ] **Step 5: Run export-focused tests and commit**

Run:

```powershell
python day22.py test
python -m py_compile day22.py
```

Expected: all embedded tests pass. Commit:

```powershell
git add day22.py
git commit -m "feat: export verified reservation evidence" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Implement ledger-verified restore

**Files:**
- Modify: `day22.py`

**Interfaces:**
- Consumes: `read_archive`, `validate_report_path`, `publish_no_overwrite`,
  archive manifest/bytes, and the receiving database.
- Produces: `restore(args) -> int`, which restores only the trusted original
  Day 14 report path and preserves the database and existing files.

- [ ] **Step 1: Add the restore command parser**

Add:

```python
command = subparsers.add_parser("restore")
command.add_argument("--bundle", required=True, type=Path)
```

Dispatch `restore(args)` from `main()`.

- [ ] **Step 2: Validate the archive before database access**

Call `read_archive(args.bundle)` and parse the manifest, canonical plan, and
exact rehearsal bytes. Validate:

- manifest version and unsigned status;
- canonical plan hash against both manifest and plan content;
- reservation and candidate UUID syntax;
- report path with `validate_report_path(..., must_exist=False)`;
- report’s `rehearsal_id` matches the UUID parent directory;
- exact report member hash.

Reject all malformed, oversized, encrypted, duplicated, missing, unexpected,
or path-bearing archive content before writing any file.

- [ ] **Step 3: Compare the bundle to the receiving ledger snapshot**

Open a repeatable-read, read-only transaction and select the same reservation
fields used by export. Require that the receiving reservation’s state,
candidate, plan hash, report path, report hash, and plan exactly match the
manifest and bundled plan/report.

Call `require_finished_candidate`, `validate_association`, `validate_context`,
and `validate_candidate` against the receiving database’s candidate row.
Reject any mismatch, missing candidate, or missing report association. Do not
update any table.

- [ ] **Step 4: Publish only the ledger-approved report**

After the read-only validation succeeds, call
`publish_no_overwrite(validated_report_path, rehearsal_bytes)`. Print
`ALREADY_PRESENT` for identical evidence and a restored status for a newly
published file. Never use the archive’s member names or manifest path as an
output path.

- [ ] **Step 5: Run restore-focused tests and commit**

Run:

```powershell
python day22.py test
python -m py_compile day22.py
git diff --check
```

Expected: all eight tests pass and the module compiles. Commit:

```powershell
git add day22.py
git commit -m "feat: restore ledger-verified reservation evidence" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Wire CI and validate the complete offline change

**Files:**
- Modify: `.github/workflows/ledger-checks.yml`

**Interfaces:**
- Consumes: the completed `day22.py` test command.
- Produces: CI coverage for syntax compilation and portable evidence bundle
  offline tests, with no live database or archive operations.

- [ ] **Step 1: Add Day 22 to syntax compilation**

Extend the existing `py_compile` command by adding `day22.py` after
`day21.py`:

```yaml
day19.py day20.py day21.py day22.py
```

- [ ] **Step 2: Add the portable bundle test step**

Add after the Day 21 test step:

```yaml
- name: Test portable evidence bundles
  run: python day22.py test
```

- [ ] **Step 3: Run focused and complete validation**

Run:

```powershell
python day22.py test
python -m py_compile judge.py day3.py day4.py day5.py day6.py day7.py day8.py day9.py day11.py day12.py day13.py day14.py day15.py day16.py day17.py day18.py day19.py day20.py day21.py day22.py
python day5.py test
python day6.py test
python day8.py test
python day9.py test
python day11.py test
python day12.py test
python day13.py test
python day14.py test
python day15.py test
python day16.py test
python day17.py test
python day18.py test
python day19.py test
python day20.py test
python day21.py test
git diff --check
git status --short
```

Expected: every command exits successfully, the full offline suite is green,
and only the intended Day 22 module, workflow, and prior committed design
remain in the working tree.

- [ ] **Step 4: Commit CI wiring and final validation**

```powershell
git add .github/workflows/ledger-checks.yml
git commit -m "ci: test portable evidence bundles" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

After this commit, push the feature branch and open a pull request against the
known base branch. Verify hosted Offline tests and GitGuardian checks. Do not
run live export/restore, retain a real archive externally, or merge the pull
request without separate user direction.
