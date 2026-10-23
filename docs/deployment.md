# Deploying Ledger on Rumpty Cloud

## Overview

Ledger runs as two processes from a single Docker image:

- **API** — handles ingestion, project management, and evaluation queries.
- **Worker** — polls the database-backed job queue and processes evaluation
  jobs with retries and dead-letter state.

The API embeds a worker only for single-process local demonstration. Use a
separate worker in production to avoid duplicate consumers when the API scales.

## 1. Configure managed PostgreSQL

Create a Rumpty managed PostgreSQL database. Save its server/CA certificate at
`certs/ledger-db-ca.crt`; this file is ignored by Git.

For an API and worker hosted on Rumpty, use its **internal** connection string.
Use the external connection string only from a local development machine.

```env
LEDGER_DATABASE_URL=postgresql+psycopg://USER:PERCENT_ENCODED_PASSWORD@INTERNAL_HOST:PORT/DATABASE
LEDGER_DB_SSLMODE=verify-full
LEDGER_DB_SSLROOTCERT=./certs/ledger-db-ca.crt
LEDGER_AUTO_CREATE_SCHEMA=false
LEDGER_ADMIN_TOKEN=long-random-secret
LEDGER_BLOB_DIR=./data/blobs
GROQ_API_KEY=gsk_...
# Or set exactly one of these instead of Groq:
# OPENAI_API_KEY=sk-...
# OPENROUTER_API_KEY=sk-or-v1-...
# Optional override; Groq defaults to openai/gpt-oss-120b.
# LEDGER_JUDGE_MODEL=openai/gpt-oss-120b
```

If a password contains reserved URL characters such as `@`, `:`, `/`, or `#`,
percent-encode it in the connection URL.

See [.env.example](../.env.example) for all available environment variables.

## 2. Apply the schema

Apply `migrations/001_ledger_schema.sql` once to a new database before starting
the service. Ledger intentionally does not create a production schema at
application startup.

The migration provides project/key tables, trace/span tables, evaluation runs,
alerts, and the database-backed job queue.

```bash
psql "$LEDGER_DATABASE_URL" -f migrations/001_ledger_schema.sql
```

## 3. Deploy two processes

Build from the repository's `Dockerfile`. Deploy from the same image with two
commands:

```text
API:    uvicorn ledger_api.main:app --host 0.0.0.0 --port $PORT
Worker: python -m ledger_api.worker
```

Or use the stable CLI:

```text
API:    python -m ledger serve
Worker: python -m ledger worker
```

## 4. Verify

After deployment, request `GET /health`. It should return:

```json
{"status":"ok"}
```

Then create a project and submit an ingest request through `/docs`. Confirm the
trace appears through `GET /v1/traces/{project_id}` after the worker processes
the job.

## 5. Run the doctor (optional)

On the deployed machine, run the read-only doctor to verify configuration:

```bash
python -m ledger doctor --check-database
```

This checks Python version, required files, modules, secret presence, and
database reachability without writing schema or data.
