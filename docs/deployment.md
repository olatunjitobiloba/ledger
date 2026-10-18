# Deploying Ledger on Rumpty Cloud

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
OPENAI_API_KEY=sk-...
```

If a password contains reserved URL characters such as `@`, `:`, `/`, or `#`,
percent-encode it in the connection URL.

## 2. Apply the schema

Apply `migrations/001_ledger_schema.sql` once to a new database before starting
the service. Ledger intentionally does not create a production schema at
application startup.

The migration provides project/key tables, trace/span tables, evaluation runs,
alerts, and the database-backed job queue.

## 3. Deploy two processes

Build from the repository's `Dockerfile`. Deploy from the same image with two
commands:

```text
API:    uvicorn ledger_api.main:app --host 0.0.0.0 --port $PORT
Worker: python -m ledger_api.worker
```

The API embeds a worker only for a single-process local demonstration. Use a
separate worker in production to avoid duplicate consumers when the API scales.

## 4. Verify

After deployment, request `GET /health`. It should return:

```json
{"status":"ok"}
```

Then create a project and submit an ingest request through `/docs`. Confirm the
trace appears through `GET /v1/traces/{project_id}` after the worker processes
the job.
