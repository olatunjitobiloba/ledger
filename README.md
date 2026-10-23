# Ledger

> Production AI reliability infrastructure — asynchronous observability,
> automated evaluation gates, and portable release evidence for LLM
> applications, built for Rumpty Cloud.

Ledger ensures that every AI model change ships with evidence that it did not
regress. It records trace cost and injection-risk metadata without blocking the
host request, evaluates versioned golden sets in a background worker, and gates
releases on stored evaluation results — all before a single user is affected.

## Why Ledger

AI teams ship model updates without a repeatable way to prove they did not break
quality. Manual spot-checks miss regressions. Cost is invisible until the
invoice arrives. Prompt injection is hard to detect and easy to ignore.

Ledger solves this:

- **Non-blocking telemetry** — the SDK fires and forgets; observability never
  slows or fails the host application's AI response.
- **Automated evaluation gate** — versioned golden-set scoring detects
  regressions before they reach users.
- **Cost attribution** — per-span estimated and actual cost, rolled up per
  trace and per project.
- **Prompt-injection monitoring** — heuristic tagging on every stored span.
- **Portable release evidence** — commit-bound, runtime-bound,
  container-bound evaluation bundles that can be exported, restored, and
  verified offline.

## 60-second offline demo

These commands run without a database, provider key, or network access:

```bash
# Verify the repository is ready
python -m ledger doctor

# Run the full offline test suite (43 product tests + 12 modernization tests)
python -m unittest test_judge test_judge_groq test_api -v
python -m unittest tests.test_compatibility tests.test_cli -v

# Run individual evaluation module tests
python day22.py test   # portable evidence bundles
python day6.py test    # regression gate
python day8.py test    # injection monitoring
python day9.py test    # release-readiness policy
```

Every command above exits 0 on a clean checkout with no credentials configured.

## Architecture

```text
Application
  └─ Ledger SDK (fire-and-forget)
       └─ POST /v1/ingest  ──▸  PostgreSQL job queue
                                     │
                  API ◂── Postgres metadata + blob storage
                                     │
                           Worker ──▸ Judge ──▸ Alerts
                                     │
                           Evaluation pipeline (offline)
                             ├─ Golden-set scoring
                             ├─ Regression gate
                             ├─ Spend planning & reconciliation
                             └─ Portable evidence bundles
```

The SDK deliberately ignores delivery failures. The API returns `202 Accepted`
and enqueues work. The worker processes jobs with retries and a dead-letter
state. The evaluation pipeline runs independently, produces immutable evidence,
and never modifies application behavior.

## What is production-grade here?

| Concern | How Ledger handles it |
| --- | --- |
| **Observability** | Async ingest, `202 Accepted`, database-backed queue, retries, dead-letter jobs |
| **Evaluation** | Versioned golden set, Groq-hosted gpt-oss judge at temperature 0, discrimination checks |
| **Regression gate** | Per-case mean with an allowed absolute drop; any case beyond it blocks the release |
| **Cost control** | Per-model pricing, spend plans, reservations, single-use enforcement, reconciliation |
| **Evidence chain** | Commit provenance → runtime fingerprint → container digest → portable bundle |
| **Privacy** | `capture_prompt` toggle, regex redaction (SDK and server), hashed API keys |
| **Injection monitoring** | Heuristic prompt-injection tags on stored spans |
| **Release policy** | Multi-check readiness gate: regression, injection, cost, provenance |
| **CI** | 55 offline tests in GitHub Actions, no provider keys required |

## Rumpty Cloud deployment

Ledger runs as two processes from a single Docker image on Rumpty Cloud:

```text
API:    uvicorn ledger_api.main:app --host 0.0.0.0 --port $PORT
Worker: python -m ledger_api.worker
```

1. Create a Rumpty managed PostgreSQL database.
2. Apply `migrations/001_ledger_schema.sql` once.
3. Save Rumpty's server/CA certificate at `certs/ledger-db-ca.crt`.
4. Configure `.env` from `.env.example` with Rumpty's internal connection
   string.
5. Deploy both processes. Verify with `GET /health`.

See [docs/deployment.md](docs/deployment.md) for the complete deployment guide,
SSL configuration, and environment variables.

## API and SDK quick start

**Requirements:** Python 3.11+ and a PostgreSQL database for live use. Offline
tests require no database or provider key.

```bash
pip install -r requirements.txt
copy .env.example .env
# Edit .env: set LEDGER_DATABASE_URL to your PostgreSQL connection string
python -m ledger serve
```

Open interactive API documentation at `http://127.0.0.1:8000/docs`.

### Create a project

```bash
curl -X POST http://127.0.0.1:8000/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "demo", "capture_prompt": false}'
```

### Ingest a span

```bash
curl -X POST http://127.0.0.1:8000/v1/ingest \
  -H "X-API-Key: <project-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id": null,
    "span": {
      "span_id": "2e00d5cc-90dc-4dc5-b1ae-bc091db46057",
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
  }'
```

### Python SDK

```python
from ledger_sdk import Ledger

client = Ledger("http://localhost:8000", api_key="<project-key>")
await client.ingest([{
    "spans": [Ledger.span(
        name="generate_response",
        model="gpt-4o-mini",
        prompt_tokens=150,
        completion_tokens=80,
    )]
}])
# Returns immediately — delivery is non-blocking.
```

### API endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/projects` | Create a project and initial API key |
| `POST /v1/api-keys` | Issue an additional project API key |
| `POST /v1/ingest` | Queue trace/span telemetry; responds immediately |
| `GET /v1/traces/{project_id}` | List trace costs and maximum risk score |
| `POST /v1/eval/run` | Queue a versioned golden-set evaluation |
| `GET /v1/eval/runs/{project_id}` | View score, threshold, status, and worst cases |
| `GET /v1/alerts/{project_id}` | List regression alerts |

See [docs/api-contract.md](docs/api-contract.md) for the frozen SDK contract
and design decisions.

## Evaluation and release evidence

Ledger's evaluation pipeline produces commit-bound, runtime-bound,
container-bound evidence that a model change did not regress:

```bash
# Versioned golden-set evaluation
python day3.py run --reviewed-by "Tobi" --repeats 3

# Regression gate (compares stored results, no provider calls)
python day6.py compare --baseline <UUID> --candidate <UUID> --allowed-drop 0.05

# Release-readiness policy check
python day9.py check --baseline <UUID> --candidate <UUID>

# Export portable evidence bundle
python -m ledger evidence export --reservation <UUID> --output evidence.zip

# Restore and verify on another machine
python -m ledger evidence restore --bundle evidence.zip
```

The evidence chain: **golden set** → **evaluation runs** → **cost attribution**
→ **spend plan** → **reservation** → **reconciliation** → **portable bundle**.

Each step is independently testable and produces results that can be verified
without running the full pipeline.

## Security and privacy

- **`capture_prompt=false`** prevents prompt/response payloads from being
  stored. Tokens, latency, model, and cost are still recorded.
- **Regex redaction** is applied before captured payloads are persisted; the
  SDK can redact before data leaves the host application.
- **API keys** are stored as SHA-256 hashes, never plaintext.
- **Database credentials**, `.env`, and server certificates are gitignored.
- **Heuristic injection tags** flag suspicious wording without blocking
  requests; a match is not proof of an attack.
- **TLS certificate verification** is supported for PostgreSQL connections on
  Rumpty Cloud.

## Testing and CI

```bash
# Full offline test suite
python -m unittest test_judge test_judge_groq test_api -v      # 43 product tests
python -m unittest tests.test_compatibility tests.test_cli -v  # 12 modernization tests

# Individual evaluation modules (each has a self-contained test mode)
python day5.py test    # cost attribution
python day6.py test    # regression gate
python day8.py test    # injection monitoring
python day9.py test    # release policy
python day11.py test   # commit provenance
python day12.py test   # runtime binding
python day13.py test   # container binding
python day14.py test   # evaluation orchestration
python day15.py test   # preflight validation
python day16.py test   # spend planning
python day17.py test   # cost reconciliation
python day18.py test   # spend reservations
python day19.py test   # reservation recovery
python day20.py test   # execution context
python day21.py test   # reservation-scoped reconciliation
python day22.py test   # portable evidence bundles
```

GitHub Actions runs all offline tests on every push to `main` and on pull
requests. The release-check job validates container-bound evidence against a
Rumpty-hosted database through a manual workflow dispatch. See
[.github/workflows/ledger-checks.yml](.github/workflows/ledger-checks.yml).

## Stable CLI

```bash
python -m ledger --help
python -m ledger doctor              # read-only local readiness check
python -m ledger doctor --check-database
python -m ledger serve               # start the API with Uvicorn
python -m ledger worker              # start the background worker
python -m ledger evidence export --reservation <UUID> --output <path.zip>
python -m ledger evidence restore --bundle <path.zip>
```

The CLI delegates to the existing API, worker, and evaluation implementations.
It adds no new behavior; it provides a stable, discoverable entry point.

## Limitations

- **Not a full observability platform.** Ledger handles ingestion, cost, and
  evaluation gates. It does not provide dashboards, distributed tracing UIs,
  or log aggregation.
- **Evaluation is model-dependent.** The judge uses a Groq-hosted gpt-oss model
  (`openai/gpt-oss-20b` in the evaluation pipeline, `openai/gpt-oss-120b` in
  the API) at temperature 0. Results depend on the judge model's behavior.
- **Injection monitoring is heuristic.** A match is suspicious wording, not
  proof of an attack. A zero score is not proof of safety.
- **Cost estimates are approximate.** Provider-reported actual cost is used
  when available; otherwise Ledger uses configurable per-model token pricing.
- **Single-region deployment.** The current architecture is designed for a
  single Rumpty Cloud region.
- **No user-facing dashboard.** API and CLI access only; there is no web UI.

## Documentation

| Document | Description |
| --- | --- |
| [docs/api-contract.md](docs/api-contract.md) | Frozen SDK ingestion contract and design decisions |
| [docs/deployment.md](docs/deployment.md) | Rumpty Cloud deployment guide |
| [docs/hackathon/submission.md](docs/hackathon/submission.md) | Hackathon submission brief |
| [docs/hackathon/demo-script.md](docs/hackathon/demo-script.md) | 3-minute demo sequence |
| [docs/hackathon/evidence-map.md](docs/hackathon/evidence-map.md) | Claims mapped to source and verification |
| [migrations/001_ledger_schema.sql](migrations/001_ledger_schema.sql) | Reviewed PostgreSQL schema |
| [.env.example](.env.example) | Annotated environment configuration |

## License

No license has been selected yet.
