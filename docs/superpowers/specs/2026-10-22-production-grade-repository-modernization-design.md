# Production-Grade Repository Modernization

## Goal

Make Ledger present as a coherent production AI reliability product for the
Devcenter Hacktober / Rumpty Cloud deployment marathon while preserving every
existing command, import path, runtime behavior, and validated safety boundary.

This work improves the repository’s public surface and operability. It does not
claim or fabricate judging outcomes, customer metrics, or production adoption.
The hackathon outcome remains a judge decision; the repository will make the
product, deployment, evidence, and demo easy to understand and verify.

## Scope and compatibility contract

### In scope

- Move maintained implementation behind descriptive package/module boundaries.
- Add a stable top-level CLI with discoverable help and health checks.
- Keep historical `day3.py` through `day22.py` commands and import paths
  working as compatibility adapters.
- Rewrite the README around the actual Ledger product and Rumpty deployment.
- Add judge-facing hackathon submission and demo documentation.
- Add repository hygiene and safe local-cleanup guidance.
- Preserve existing CI, database schema, migrations, prompts, datasets,
  environment variables, result paths, and evidence semantics unless a
  compatibility test proves the change is equivalent.

### Explicitly out of scope

- Deleting or silently discarding source, migrations, evidence, tests, or
  configuration because a filename looks old.
- Renaming environment variables, database tables, API routes, result paths,
  command flags, or importable legacy modules without adapters.
- Changing evaluation policy, model behavior, spend limits, privacy defaults,
  authentication, deployment topology, or evidence trust rules.
- Fabricating performance, cost, user, reliability, or business-impact claims.
- Running paid model calls, live evaluation, live evidence export/restore, or
  destructive cleanup without separate explicit approval.

## Architecture

### Maintained package surface

Create descriptive modules under `ledger/` with one responsibility per
boundary. The exact extraction order must follow import dependencies and keep
the existing modules as the behavioral reference:

```text
ledger/
  __main__.py                 # python -m ledger
  cli.py                      # stable command parser and dispatch
  evaluation/
    __init__.py
    dataset.py                # dataset loading and hashing
    judging.py                # evaluator/rubric boundaries
    orchestration.py          # rehearsal and release orchestration
    spending.py               # plans, budgets, reservations, recovery
    reconciliation.py         # read-only cost/reconciliation flows
    evidence.py               # reservation evidence export/restore
  observability/
    __init__.py
    sdk.py                    # public SDK facade
    api.py                    # API application facade
    worker.py                 # worker facade
```

Only modules whose behavior can be extracted without changing public
interfaces should be moved in the first implementation. Large or tightly
coupled modules may remain internally delegated until focused compatibility
tests cover their extraction.

### Compatibility adapters

The root `day3.py`–`day22.py` files become small, explicit adapters only after
the corresponding descriptive implementation exists. Each adapter must:

- retain the existing executable command syntax;
- re-export symbols currently imported by other modules;
- delegate rather than duplicate business logic;
- include a short deprecation/compatibility note;
- remain covered by command and import smoke tests.

If a complete extraction would require risky changes to a tightly coupled
module, keep that module intact in the first pass and expose it through the
stable CLI instead. A smaller safe modernization is preferable to a broad
rewrite that changes behavior.

### Stable CLI

Add `python -m ledger` with:

```text
python -m ledger --help
python -m ledger doctor
python -m ledger serve
python -m ledger worker
python -m ledger evaluate
python -m ledger release-check
python -m ledger evidence export --reservation UUID --output PATH.zip
python -m ledger evidence restore --bundle PATH.zip
```

The CLI must delegate to existing implementations and preserve their exit
codes and error visibility. It must not create a second competing data path.
`doctor` is read-only and checks configuration shape, required files, Python
dependencies, and database reachability only when explicitly requested.

## README and hackathon presentation

Rewrite `README.md` to be judge- and contributor-facing:

1. One-sentence product positioning: Ledger is production AI reliability
   infrastructure for cost, quality, prompt-injection risk, and auditable
   release evidence.
2. The problem and why it matters for teams deploying AI.
3. A 60-second local demo that uses offline fixtures and does not require a
   provider key.
4. Rumpty Cloud deployment path with API, worker, PostgreSQL, TLS, and health
   verification.
5. Architecture diagram showing SDK/API/queue/worker/evaluation/evidence.
6. Capability table covering observability, evaluation, spend controls,
   reservation recovery, reconciliation, and portable evidence.
7. Security/privacy boundaries and explicit limitations.
8. Reproducible test and CI commands.
9. Hackathon demo flow and honest proof points.
10. Links to API, deployment, evidence, and contribution documentation.

The README must not claim that Ledger has won, guarantees selection, or has
unmeasured impact. Claims must be directly supported by code, tests, or
documented deployment behavior.

Add `docs/hackathon/`:

```text
docs/hackathon/
  submission.md       # judge-facing pitch and proof points
  demo-script.md      # timed walkthrough and fallback path
  evidence-map.md     # claims mapped to files/tests/commands
```

The submission material should make the differentiator clear:
Ledger is not merely an LLM wrapper; it connects runtime observability,
evaluation gates, spend admission/recovery, provenance, and portable evidence
into a verifiable release workflow.

## Data flow and safety

The modernization must preserve this behavior:

```text
Application
  -> SDK
  -> asynchronous ingest API
  -> PostgreSQL queue
  -> worker
  -> evaluation/release evidence
  -> read-only reconciliation and portable evidence
```

Compatibility adapters must not create duplicate database writes or model
calls. The stable CLI must call the same validated functions as existing
commands. All existing Day 20–22 context, hash, path, archive, read-only
transaction, and no-overwrite requirements remain binding.

Local cleanup must be explicit and narrow:

- never remove tracked files;
- never remove `.env`, certificates, databases, or evidence by broad wildcard;
- provide a dry-run inventory before deleting ignored caches/results;
- clean only named generated directories such as `__pycache__`, `.ruff_cache`,
  and selected ignored test output after user approval;
- keep generated artifacts ignored and private.

## Testing and validation

Add tests before or alongside each extraction:

- import smoke tests for every historical module path;
- `python dayN.py --help` smoke tests for every existing command adapter;
- stable CLI help and command-dispatch tests;
- `doctor` tests for missing/valid configuration without secrets;
- README command snippets checked against available offline commands;
- compatibility tests comparing adapter exit codes and delegated behavior;
- existing API, judge, offline evaluation, and Day 22 suites unchanged.

Required final validation:

```powershell
python -m ledger --help
python -m ledger doctor --help
python -m unittest test_judge test_api -v
python day22.py test
python -m py_compile ...
git diff --check
```

The complete existing offline suite and hosted CI must pass. No live provider
calls or database writes are part of the implementation validation. A separate
approval is required for any live Rumpty deployment rehearsal.

## Delivery

Implementation will be delivered in reviewed phases:

1. package boundaries and compatibility adapters;
2. stable CLI and read-only doctor;
3. README and judge-facing documentation;
4. hygiene tooling and complete regression validation.

Each phase must be independently testable and committed. The final branch
must have a clean working tree, passing local and hosted checks, and a concise
demo path suitable for a hackathon reviewer.

