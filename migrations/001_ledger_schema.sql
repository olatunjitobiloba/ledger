-- Ledger PostgreSQL schema. Apply once to a fresh Rumpty managed Postgres DB.
-- Requires pgcrypto for UUID generation; do not run this against an existing
-- production schema without reviewing it with the team.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'free',
    capture_prompt BOOLEAN NOT NULL DEFAULT false,
    redact_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
    retention_days INTEGER NOT NULL DEFAULT 7,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per end-to-end request. project_id and configuration fields retain
-- the multi-project and regression context required by the Ledger PRD.
CREATE TABLE traces (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id TEXT,
    session_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    total_cost_actual NUMERIC(10,6),
    total_cost_estimated NUMERIC(10,6),
    total_latency_ms INTEGER,
    config_id TEXT,
    prompt_hash TEXT,
    model TEXT,
    rag_index_version TEXT,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- One row per LLM/tool/retrieval/evaluator step. Raw text is only populated
-- when capture_prompt is enabled; production blob storage may replace these
-- two fields with payload_ref without changing the SDK contract.
CREATE TABLE spans (
    span_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id UUID REFERENCES spans(span_id),
    span_type TEXT NOT NULL,
    name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    latency_ms INTEGER,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cost_actual NUMERIC(10,6),
    cost_estimated NUMERIC(10,6),
    capture_prompt BOOLEAN NOT NULL DEFAULT false,
    prompt_text TEXT,
    response_text TEXT,
    payload_ref TEXT,
    eval_score NUMERIC(3,2),
    injection_risk_score NUMERIC(3,2),
    injection_risk_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_spans_trace_id ON spans(trace_id);
CREATE INDEX idx_traces_project_created_at ON traces(project_id, created_at DESC);
CREATE INDEX idx_traces_created_at ON traces(created_at);

CREATE TABLE api_keys (
    api_key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE eval_runs (
    eval_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_version TEXT NOT NULL,
    config_id TEXT NOT NULL,
    baseline_score NUMERIC(5,2) NOT NULL,
    variance NUMERIC(5,2) NOT NULL,
    result_score NUMERIC(5,2),
    passed BOOLEAN,
    status TEXT NOT NULL DEFAULT 'queued',
    worst_cases JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    eval_run_id UUID NOT NULL REFERENCES eval_runs(eval_run_id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'regression',
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Durable Postgres-backed queue and dead-letter record.
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_ready ON jobs(status, created_at) WHERE status = 'queued';
