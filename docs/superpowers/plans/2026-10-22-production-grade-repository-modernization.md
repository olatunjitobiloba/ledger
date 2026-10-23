# Production-Grade Repository Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present Ledger as a polished production AI reliability product with a stable CLI, descriptive maintained surfaces, judge-ready documentation, and safe repository hygiene while preserving all existing commands, imports, data paths, and behavior.

**Architecture:** Modernize in compatibility-first phases. Add a descriptive `ledger` CLI and facade modules that delegate to the existing API and evaluation implementations, then migrate only seams covered by import/command tests. Keep `day3.py`–`day22.py` executable and import-compatible until a proven adapter replaces each public surface; never trade visual tidiness for behavior regression.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL/psycopg, standard-library `argparse`/`unittest`, Uvicorn, GitHub Actions, Markdown documentation.

## Global Constraints

- Preserve every existing command, import path, runtime behavior, and validated safety boundary.
- Keep historical `day3.py` through `day22.py` commands and import paths working as compatibility adapters.
- Do not rename environment variables, database tables, API routes, result paths, command flags, or importable legacy modules without adapters.
- Do not change evaluation policy, model behavior, spend limits, privacy defaults, authentication, deployment topology, or evidence trust rules.
- Do not fabricate performance, cost, user, reliability, or business-impact claims.
- Do not run paid model calls, live evaluation, live evidence export/restore, or destructive cleanup without separate explicit approval.
- The stable CLI must delegate to existing implementations and preserve their exit codes and error visibility.
- `doctor` is read-only and checks configuration shape, required files, Python dependencies, and database reachability only when explicitly requested.
- Never remove tracked files, `.env`, certificates, databases, or evidence by broad wildcard.
- Generated artifacts remain ignored and private.
- Existing CI, database schema, migrations, prompts, datasets, environment variables, result paths, and evidence semantics remain unchanged.
- Every phase ends with focused tests, compilation, `git diff --check`, and a commit.

---

## File Map

- Create: `ledger/__main__.py`
  - Package entry point for `python -m ledger`.
- Create: `ledger/cli.py`
  - Stable top-level parser, command dispatch, and read-only doctor.
- Create: `ledger/evaluation/__init__.py`
  - Public evaluation facade exports.
- Create: `ledger/evaluation/evidence.py`
  - Descriptive facade for Day 22 evidence export/restore.
- Create: `ledger/evaluation/reconciliation.py`
  - Descriptive facade for Day 21 reconciliation.
- Create: `ledger/observability/__init__.py`
  - Public observability facade exports.
- Create: `ledger/observability/sdk.py`
  - Descriptive facade for the existing SDK.
- Create: `ledger/observability/api.py`
  - Descriptive facade for the existing FastAPI application.
- Create: `ledger/observability/worker.py`
  - Descriptive facade for the existing worker entry point.
- Create: `tests/test_compatibility.py`
  - Import and command compatibility smoke tests.
- Create: `tests/test_cli.py`
  - Stable CLI help, dispatch, and doctor tests.
- Modify: `README.md`
  - Product, demo, architecture, Rumpty deployment, security, and testing story.
- Create: `docs/hackathon/submission.md`
  - Judge-facing pitch and evidence-backed proof points.
- Create: `docs/hackathon/demo-script.md`
  - Timed demo and offline fallback.
- Create: `docs/hackathon/evidence-map.md`
  - Claims mapped to code, tests, and commands.
- Modify: `docs/deployment.md`
  - Align deployment instructions with the polished README and current code.
- Modify: `.github/workflows/ledger-checks.yml`
  - Run compatibility and CLI tests in CI.
- Modify: `.gitignore`
  - Preserve ignored local artifacts while documenting generated directories.
- Create: `scripts/clean-local.ps1`
  - Explicit dry-run/confirmed cleanup for named ignored artifacts only.

## Interfaces

The stable CLI must provide:

```text
python -m ledger --help
python -m ledger doctor --help
python -m ledger doctor
python -m ledger serve
python -m ledger worker
python -m ledger evidence export --reservation UUID --output PATH.zip
python -m ledger evidence restore --bundle PATH.zip
```

The compatibility tests must import:

```python
import day3, day4, day5, day6, day7, day8, day9
import day11, day12, day13, day14, day15, day16, day17
import day18, day19, day20, day21, day22
```

and execute each module’s `--help` without database, provider, or model access.

### Task 1: Establish descriptive facades and compatibility tests

**Files:**
- Create: `ledger/evaluation/__init__.py`
- Create: `ledger/evaluation/evidence.py`
- Create: `ledger/evaluation/reconciliation.py`
- Create: `ledger/observability/__init__.py`
- Create: `ledger/observability/sdk.py`
- Create: `ledger/observability/api.py`
- Create: `ledger/observability/worker.py`
- Create: `tests/__init__.py`
- Create: `tests/test_compatibility.py`

**Interfaces:**
- Consumes: existing `day21`, `day22`, `ledger_sdk`, `ledger_api.main`, and `ledger_api.worker`.
- Produces: descriptive imports that delegate to existing implementations without changing behavior.

- [ ] **Step 1: Add failing compatibility imports**

Create tests that import every legacy module and assert the descriptive facades
expose the existing key symbols:

```python
def test_legacy_day_modules_import(self):
    for name in ("day3", "day4", "day5", "day6", "day7", "day8",
                 "day9", "day11", "day12", "day13", "day14", "day15",
                 "day16", "day17", "day18", "day19", "day20", "day21", "day22"):
        importlib.import_module(name)

def test_descriptive_facades_delegate(self):
    from ledger.evaluation.evidence import export_reservation, restore_bundle
    from ledger.evaluation.reconciliation import reconcile
    from ledger.observability.api import app
    from ledger.observability.sdk import Ledger
    self.assertIsNotNone(export_reservation)
    self.assertIsNotNone(restore_bundle)
    self.assertIsNotNone(reconcile)
    self.assertIsNotNone(app)
    self.assertIsNotNone(Ledger)
```

- [ ] **Step 2: Run tests to verify the new facades fail**

Run:

```powershell
python -m unittest tests.test_compatibility -v
```

Expected: the legacy import test passes and the new descriptive facade import
test fails because the facade modules do not yet exist.

- [ ] **Step 3: Implement thin facades without moving business logic**

Use these direct imports/re-exports:

```python
# ledger/evaluation/evidence.py
from day22 import export_reservation, restore_bundle

__all__ = ["export_reservation", "restore_bundle"]
```

Do not duplicate function bodies. The observability facades must re-export
`Ledger` from `ledger_sdk`, `app` from `ledger_api.main`, and `main` from
`ledger_api.worker`. No source implementation should be moved in this task.

- [ ] **Step 4: Add command-help compatibility tests**

Extend `tests/test_compatibility.py` to run each legacy module with
`subprocess.run([sys.executable, module, "--help"], check=False, ...)`, assert
exit code 0, and assert output is non-empty. Use no environment credentials.

- [ ] **Step 5: Run focused validation and commit**

Run:

```powershell
python -m unittest tests.test_compatibility -v
python -m py_compile (Get-ChildItem ledger/evaluation,ledger/observability -Filter *.py -File).FullName tests/test_compatibility.py
git diff --check
```

Commit:

```powershell
git add ledger tests
git commit -m "refactor: add descriptive compatibility facades" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Add the stable CLI and read-only doctor

**Files:**
- Create: `ledger/__main__.py`
- Create: `ledger/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: descriptive facades from Task 1, `ledger_api.main.app`, and
  `ledger_api.worker.main`.
- Produces: `build_parser()`, `main(argv: list[str] | None = None) -> int`,
  and `python -m ledger` commands.

- [ ] **Step 1: Write CLI contract tests**

Add tests for help and dispatch without credentials:

```python
def test_help_lists_product_commands(self):
    result = run_cli("--help")
    self.assertEqual(result.returncode, 0)
    for command in ("doctor", "serve", "worker", "evidence"):
        self.assertIn(command, result.stdout)

def test_doctor_help_is_read_only(self):
    result = run_cli("doctor", "--help")
    self.assertEqual(result.returncode, 0)
    self.assertIn("read-only", result.stdout.lower())

def test_evidence_parser_requires_arguments(self):
    result = run_cli("evidence", "export")
    self.assertNotEqual(result.returncode, 0)
```

- [ ] **Step 2: Implement parser and package entry point**

Create `build_parser()` with subcommands:

```python
parser = argparse.ArgumentParser(prog="ledger")
commands = parser.add_subparsers(dest="command", required=True)
commands.add_parser("doctor")
commands.add_parser("serve")
commands.add_parser("worker")
evidence = commands.add_parser("evidence")
evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
export = evidence_commands.add_parser("export")
export.add_argument("--reservation", required=True, type=uuid.UUID)
export.add_argument("--output", required=True, type=Path)
restore = evidence_commands.add_parser("restore")
restore.add_argument("--bundle", required=True, type=Path)
```

`ledger/__main__.py` must call `sys.exit(main())`.

- [ ] **Step 3: Implement delegation and doctor**

`evidence export` and `evidence restore` delegate to the existing Day 22
handlers. `serve` delegates to `uvicorn` with the existing `ledger_api.main:app`;
`worker` delegates to `ledger_api.worker.main`.

`doctor` must be read-only by default. It checks:

- Python version is at least 3.11;
- required files such as `runtime-config.json`, `evaluation-budget.json`,
  `datasets/golden-v1.json`, and `migrations/001_ledger_schema.sql` exist;
- required Python modules import;
- provider/database secrets are reported only as present/missing, never printed;
- database reachability is skipped unless `--check-database` is supplied.

Return 0 for a healthy local offline configuration, 1 for failed checks, and
print actionable messages without exposing secret values.

- [ ] **Step 4: Run CLI tests and commit**

Run:

```powershell
python -m unittest tests.test_cli tests.test_compatibility -v
python -m ledger --help
python -m ledger doctor --help
python -m py_compile ledger/__main__.py ledger/cli.py tests/test_cli.py
git diff --check
```

Commit:

```powershell
git add ledger tests
git commit -m "feat: add stable Ledger CLI and doctor" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Rewrite README and add hackathon submission materials

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.md`
- Create: `docs/hackathon/submission.md`
- Create: `docs/hackathon/demo-script.md`
- Create: `docs/hackathon/evidence-map.md`

**Interfaces:**
- Consumes: the stable CLI, existing API/deployment behavior, Day 20–22
  evidence guarantees, and verified local commands.
- Produces: judge-facing documentation with no unsupported claims.

- [ ] **Step 1: Inventory every README command**

Extract every shell command currently shown in `README.md` and run it in a
safe mode or replace it with a verified equivalent. Do not retain the current
SQLite claim if the shipped API configuration requires SQLAlchemy-compatible
database settings; document the actual supported local test configuration.

- [ ] **Step 2: Write the product-first README**

Use this structure:

```markdown
# Ledger
> Production AI reliability infrastructure...

## Why Ledger
## 60-second offline demo
## Architecture
## What is production-grade here?
## Rumpty Cloud deployment
## API and SDK quick start
## Evaluation and release evidence
## Security and privacy
## Testing and CI
## Hackathon demo
## Limitations
## Documentation
```

The offline demo must use commands verified in Task 2 and existing test
fixtures; it must not require a provider key or database writes.

- [ ] **Step 3: Write judge-facing supporting documents**

`submission.md` must contain a short pitch, problem, solution, differentiation,
architecture, proof points, honest limitations, and exact demo commands.

`demo-script.md` must contain a 3-minute sequence:

1. state the production AI reliability problem;
2. run the offline test/demo;
3. show asynchronous ingestion and the API contract;
4. show evaluation/spend/evidence controls;
5. show Rumpty deployment topology;
6. close with what is proven and what is intentionally not claimed.

`evidence-map.md` must map each claim to a source file and command, for
example:

```markdown
| Claim | Source | Verification |
| Async ingestion | ledger_api/main.py | python -m unittest test_api -v |
| Portable evidence | day22.py | python day22.py test |
```

- [ ] **Step 4: Validate documentation and commit**

Run every documented offline command, then:

```powershell
git diff --check
git add README.md docs
git commit -m "docs: polish Ledger product and hackathon story" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Add safe local hygiene tooling and CI coverage

**Files:**
- Create: `scripts/clean-local.ps1`
- Modify: `.gitignore`
- Modify: `.github/workflows/ledger-checks.yml`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: repository-local ignored artifact paths.
- Produces: dry-run/confirmed cleanup and CI coverage for compatibility,
  stable CLI, and documentation command checks.

- [ ] **Step 1: Write cleanup safety tests/documentation**

Document and test the cleanup contract:

- default is dry-run;
- only named directories are eligible;
- tracked files are never candidates;
- `.env`, certificates, databases, and `results/` are excluded unless an
  explicit named path is supplied and confirmed;
- deletion requires `-Confirm`.

- [ ] **Step 2: Implement `scripts/clean-local.ps1`**

Use explicit parameters and resolved named paths:

```powershell
param(
    [switch]$Confirm,
    [string[]]$Path = @("__pycache__", ".ruff_cache", ".pytest_cache")
)
```

Reject paths outside the repository root, tracked files, and protected names.
Print the exact candidates in dry-run mode. Delete only individually resolved
directories after `-Confirm`; never recursively delete the repository root or
use a wildcard.

- [ ] **Step 3: Update ignore documentation and CI**

Keep current ignore behavior and add comments explaining `results/`, caches,
local secrets, and certificates. Add CI steps:

```yaml
- name: Test compatibility and stable CLI
  run: python -m unittest tests.test_compatibility tests.test_cli -v
```

Do not change release-check behavior.

- [ ] **Step 4: Run hygiene/CI-focused validation and commit**

Run:

```powershell
& .\scripts\clean-local.ps1
python -m unittest tests.test_compatibility tests.test_cli -v
python -m py_compile ledger/__main__.py ledger/cli.py
git diff --check
```

Expected: cleanup prints a dry-run inventory and deletes nothing.

Commit:

```powershell
git add scripts .gitignore .github/workflows/ledger-checks.yml tests
git commit -m "chore: add safe repository hygiene checks" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Run complete regression validation and delivery review

**Files:**
- Modify only files required to fix regressions found by validation.

**Interfaces:**
- Consumes: all prior modernization surfaces.
- Produces: verified backwards compatibility and a clean, judge-ready branch.

- [ ] **Step 1: Run stable CLI and compatibility checks**

```powershell
python -m ledger --help
python -m ledger doctor
python -m ledger doctor --help
python -m unittest tests.test_compatibility tests.test_cli -v
```

- [ ] **Step 2: Run existing product and evaluation tests**

```powershell
python -m unittest test_judge test_api -v
python day22.py test
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
```

- [ ] **Step 3: Compile and inspect repository state**

```powershell
python -m py_compile judge.py day3.py day4.py day5.py day6.py day7.py day8.py day9.py day11.py day12.py day13.py day14.py day15.py day16.py day17.py day18.py day19.py day20.py day21.py day22.py ledger/__main__.py ledger/cli.py
git diff --check
git status --short
```

Expected: all tests pass, no secrets or generated evidence are tracked, and
only intended source/documentation changes are present.

- [ ] **Step 4: Commit final fixes and prepare delivery**

Run the hosted CI workflow, verify Offline tests and GitGuardian, and stop
before live deployment or merge until the user explicitly chooses integration.
If a pull request is requested, describe the compatibility adapters and the
offline-only validation boundary.
