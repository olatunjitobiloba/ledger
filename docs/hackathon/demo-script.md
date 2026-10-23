# Ledger Demo Script (3 minutes)

This script is designed for a live hackathon demonstration. Every command runs
offline without a database, provider key, or network access.

---

## Minute 0:00 – The problem (30 seconds)

> "AI teams ship model updates without proof they didn't break quality.
> Cost is invisible. Injection is undetected. There's no portable proof that
> a release was safe."
>
> "Ledger solves this: asynchronous observability, automated evaluation gates,
> spend control, and portable release evidence — built for Rumpty Cloud."

## Minute 0:30 – Repository readiness (30 seconds)

Run the doctor to show the project is real and the offline checks pass:

```bash
python -m ledger doctor
```

Expected output:

```text
[PASS] Python 3.13 is supported (requires 3.11+)
[PASS] required file: runtime-config.json
[PASS] required file: evaluation-budget.json
[PASS] required file: datasets/golden-v1.json
[PASS] required file: migrations/001_ledger_schema.sql
[PASS] required module: fastapi
[PASS] required module: uvicorn
[PASS] required module: sqlalchemy
[PASS] required module: psycopg
[PASS] required module: groq
[INFO] secret OPENAI_API_KEY: ...
[INFO] secret OPENROUTER_API_KEY: ...
[INFO] secret GROQ_API_KEY: ...
[INFO] secret DATABASE_URL: ...
[INFO] secret LEDGER_DATABASE_URL: ...
[SKIP] database connection: use --check-database to test it
```

Point out: "Doctor checks configuration shape, required files, and
dependencies. It never exposes secret values — only present/missing."

## Minute 1:00 – API and judge tests (45 seconds)

Run the core product tests:

```bash
python -m unittest tests.test_api tests.test_judge tests.test_judge_groq -v
```

Highlight:
- **4 API tests** — async ingest returns 202, SDK contract is accepted,
  project isolation, privacy tier enforcement.
- **33 judge tests** — payload parsing, score coercion, discrimination checks,
  key diagnostics, dotenv safety.
- **6 strict-rubric Groq judge tests** — schema-constrained JSON, error
  handling, human-label agreement logic.
- "All 43 product tests pass with no database, no provider key, no network."

## Minute 1:45 – Evaluation evidence chain (45 seconds)

Run a key evaluation module:

```bash
python -m ledger.pipeline.evidence_bundle test
```

Explain the evidence chain:
- "Golden set → evaluation runs → cost attribution → spend plan →
  reservation → reconciliation → portable bundle."
- "Every step is independently testable. The bundle can be exported,
  transferred, and verified on any machine."

Show the regression gate:

```bash
python -m ledger.pipeline.regression test
```

"This compares stored results. Exit code 0 means PASS, 1 means BLOCK,
2 means INCONCLUSIVE. No provider calls."

## Minute 2:30 – Stable CLI and deployment (30 seconds)

Show the CLI:

```bash
python -m ledger --help
```

Explain:
- "The CLI wraps the existing API, worker, and evidence commands into a
  stable, discoverable surface."
- "On Rumpty Cloud, it runs as two processes from one Docker image:
  API on Uvicorn, worker polling the database queue."
- "55 offline tests run in GitHub Actions on every push."

Close:
> "This is what is proven. What I do not claim: this is not a full
> observability platform, the judge is model-dependent, injection monitoring
> is heuristic, and cost estimates are approximate. Every claim maps to a
> test you can run right now."

---

## Offline fallback

If the demo machine has no internet:

1. All commands above work without network access.
2. Skip `--check-database` in the doctor command.
3. Use `python -m ledger.pipeline.regression test` instead of live evaluation.
4. The entire demo runs from a clean checkout with `pip install -r
   requirements.txt` as the only setup step.
