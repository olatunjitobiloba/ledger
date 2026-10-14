# Ledger ingestion contract (SDK -> backend)

**Status: FROZEN Day 1.** Both sides build against this. Any change is a new version,
not an edit. The machine-checkable form is `contract/span-ingest.schema.json`.

## Endpoint

`POST /v1/spans`

Headers:

| Header | Value |
| --- | --- |
| `Authorization` | `Bearer <org_api_key>` |
| `Content-Type` | `application/json` |

There is no separate "start trace" call. See **Decision 1** below.

## Request

```json
{
  "trace_id": "uuid-or-null-if-new",
  "span": {
    "span_id": "uuid",
    "parent_span_id": "uuid-or-null",
    "span_type": "llm_call",
    "name": "generate_response",
    "started_at": "2026-10-01T23:00:00Z",
    "ended_at": "2026-10-01T23:00:02Z",
    "model": "gpt-4o-mini",
    "prompt_tokens": 150,
    "completion_tokens": 80,
    "capture_prompt": true,
    "prompt_text": "...",
    "response_text": "...",
    "metadata": {}
  }
}
```

Field semantics:

| Field | Required | Notes |
| --- | --- | --- |
| `trace_id` | no | `null` starts a new trace; the server auto-creates it and returns the id. |
| `span.span_id` | yes | Client-generated UUID. Idempotency key for the span. |
| `span.parent_span_id` | no | `null` for a root span. Enables nested agent/RAG trees. |
| `span.span_type` | yes | One of `llm_call`, `tool_call`, `retrieval`, `judge_eval`. |
| `span.name` | yes | Human label, e.g. `generate_response`. |
| `span.started_at` | yes | RFC 3339 / ISO 8601, UTC. |
| `span.ended_at` | no | `null` for an in-flight span. Server derives `latency_ms`. |
| `span.capture_prompt` | no | Defaults to `true`. The privacy switch (Decision 3). |
| `span.prompt_text` / `response_text` | no | Must be omitted when `capture_prompt` is `false`. |
| `span.metadata` | no | Optional extras only (Decision 4). |
| cost fields | no | **Never sent by the client.** Server-computed (Decision 2). |

## Response

`201 Created`:

```json
{
  "trace_id": "uuid",
  "span_id": "uuid",
  "cost_estimated": 0.000123
}
```

`400` on schema violation, `401` on bad key. `trace_id` is echoed so the SDK can reuse
it for the remaining spans of the same trace without a local guess.

## Decisions locked today

### Decision 1 — trace auto-created on first span
No separate "start trace" endpoint. A span whose `trace_id` is `null` makes the server
create the trace and return the id. Fewer round-trips, simpler SDK. Starting a trace and
sending its first span are the same operation, so they cannot get out of sync.

### Decision 2 — cost is server-computed
`cost_estimated = (prompt_tokens * rate_in) + (completion_tokens * rate_out)`.
`rate_in` / `rate_out` are per-model and live server-side. `cost_actual` is the
provider-reported figure when available and falls back to `cost_estimated` otherwise.
`trace.total_cost_*` is the roll-up of its spans. The client never sends cost, so a
pricing change never requires a SDK release.

### Decision 3 — `capture_prompt` is a schema-level privacy control
The flag is a real column, not a bolted-on filter. When `false`, prompt/response text is
never stored (`prompt_text`/`response_text` stay `NULL`), while tokens, latency, model,
and cost are still recorded. You keep the metric without keeping the content.

### Decision 4 — `metadata JSONB` is not a dumping ground
Anything you will filter, sort, or aggregate on belongs in a real column. `metadata` is
for genuinely optional, per-integration extras. If a field shows up in a dashboard query,
promote it to a column. This is the named failure point for this schema.

## Checklist status

- [x] Schema + contract captured in-repo (`db/schema.sql`, this file).
- [x] Open design question resolved: trace auto-created on first span (Decision 1).
- [x] `eval_score` and `injection_risk_score` columns exist now, unpopulated until the
      judge/heuristics land. No migration later.
- [x] Cost formula agreed (Decision 2).
- [ ] Lekan runs `db/schema.sql` against Rumpty Cloud Postgres and confirms it applies clean.
