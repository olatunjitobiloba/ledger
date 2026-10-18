-- Ledger trace/span schema. Day 1: frozen. Do not change without a migration.
--
-- Target: PostgreSQL 13+ (gen_random_uuid() is built in; no extension needed).
-- Apply with: psql "$DATABASE_URL" -f db/schema.sql
--
-- One trace = one end-to-end request (an agent run, a RAG query).
-- One span  = one step inside that trace (LLM call, tool call, retrieval).
-- The parent_span_id self-reference is what lets multi-step agents and RAG
-- nest without a schema redesign later. Freeze it now.

CREATE TABLE IF NOT EXISTS traces (
    trace_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id              TEXT,
    session_id           TEXT,
    status               TEXT NOT NULL DEFAULT 'pending', -- pending, completed, failed
    total_cost_actual    NUMERIC(10,6),
    total_cost_estimated NUMERIC(10,6),
    total_latency_ms     INTEGER,
    metadata             JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS spans (
    span_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id              UUID NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id        UUID REFERENCES spans(span_id), -- NULL = root span
    span_type             TEXT NOT NULL, -- 'llm_call', 'tool_call', 'retrieval', 'judge_eval'
    name                  TEXT NOT NULL,
    started_at            TIMESTAMPTZ NOT NULL,
    ended_at              TIMESTAMPTZ,
    latency_ms            INTEGER,
    model                 TEXT,
    prompt_tokens         INTEGER,
    completion_tokens     INTEGER,
    cost_actual           NUMERIC(10,6),
    cost_estimated        NUMERIC(10,6),
    capture_prompt        BOOLEAN DEFAULT true,
    prompt_text           TEXT, -- NULL when capture_prompt = false
    response_text         TEXT,
    eval_score            NUMERIC(3,2), -- populated by the judge (judge.py) later
    injection_risk_score  NUMERIC(3,2), -- populated by heuristics later
    error                 TEXT,
    metadata              JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_created_at ON traces(created_at);
