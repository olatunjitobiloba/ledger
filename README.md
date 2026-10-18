# Ledger

Ledger is a lightweight, asynchronous observability and evaluation gate for
LLM applications. It records trace cost and injection-risk metadata without
blocking the host request, then evaluates versioned golden sets in a background
worker to detect regressions.

## What it delivers

- Fire-and-forget Python SDK and `202 Accepted` ingestion endpoint.
- Trace/span cost attribution: provider-reported actual cost when supplied and
  configurable per-model estimated cost.
- Versioned golden-set evaluation using GPT-4o-mini at temperature zero.
- Regression gate using `result_score < baseline_score - variance`, including
  worst-case examples and persisted alerts.
- Field-level privacy: project capture controls, client/server redaction, and
  retention cleanup.
- Non-blocking heuristic prompt-injection tags.
- Multi-project API-key isolation, a database-backed queue, retries, and a
  dead-letter job state.

## Architecture

```text
Application → Ledger SDK → POST /v1/ingest → Postgres job queue
                                                ↓
                              API ← Postgres metadata + payload blob storage
                                                ↓
                                      Worker → judge → alerts
```

The SDK deliberately ignores telemetry delivery failures; observability must
never fail or slow the host application's AI response.

## Quick start

Requirements: Python 3.11+ and an OpenAI or OpenRouter key for live evals.

```bash
pip install -r requirements.txt
copy .env.example .env
# Then set LEDGER_DATABASE_URL=sqlite:///./data/ledger.db in .env
uvicorn ledger_api.main:app --reload
```

Open interactive API documentation at `http://127.0.0.1:8000/docs`.

Run the test suite:

```bash
python -m unittest test_judge test_api -v
```

## API workflow

Create a project. The returned API key is shown once; store it in your secret
manager.

```bash
curl -X POST http://127.0.0.1:8000/v1/projects -H "Content-Type: application/json" -d "{\"name\": \"demo\", \"capture_prompt\": false}"
```

Send the frozen one-span SDK contract:

```json
{
  "trace_id": null,
  "span": {
    "span_id": "2e00d5cc-90dc-4dc5-b1ae-bc091db46057",
    "parent_span_id": null,
    "span_type": "llm_call",
    "name": "generate_response",
    "started_at": "2026-10-01T23:00:00Z",
    "ended_at": "2026-10-01T23:00:02Z",
    "model": "gpt-4o-mini",
    "prompt_tokens": 150,
    "completion_tokens": 80,
    "capture_prompt": false,
    "metadata": {}
  }
}
```

Submit it to `POST /v1/ingest` with `X-API-Key: <project-key>`. Ledger also
accepts a batch `{"traces": [...]}` payload for exporter use cases.

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/projects` | Create a project and initial API key. |
| `POST /v1/api-keys` | Issue an additional project API key. |
| `POST /v1/ingest` | Queue trace/span telemetry; responds immediately. |
| `GET /v1/traces/{project_id}` | List trace costs and maximum risk score. |
| `POST /v1/eval/run` | Queue a versioned golden-set evaluation. |
| `GET /v1/eval/runs/{project_id}` | View score, threshold, status, and worst cases. |
| `GET /v1/alerts/{project_id}` | List regression alerts. |

See [docs/deployment.md](docs/deployment.md) for Rumpty deployment and
[migrations/001_ledger_schema.sql](migrations/001_ledger_schema.sql) for the
reviewed PostgreSQL schema.

## Privacy and security

- `capture_prompt=false` prevents prompt/response payloads from being written.
- `redact_patterns` are applied before captured payloads are persisted; the SDK
  can redact before data leaves the host application.
- API keys are stored as SHA-256 hashes, not plaintext.
- Database credentials, `.env`, and server certificates are ignored by Git.
- In production, set a strong `LEDGER_ADMIN_TOKEN` and use TLS certificate
  verification for PostgreSQL.

## Development notes

`judge.py` remains a standalone, testable judge component. Use
`python judge.py --mock` to exercise it without a provider key. The API worker
uses the real judge for queued evaluation runs.

## License

No license has been selected yet.
