from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# The reviewed migration declares every identifier as UUID. The ORM must use
# the same type or Postgres rejects inserts such as
# "column project_id is of type uuid but expression is of type character varying".
# as_uuid=False keeps the Python-side value a string, which is what the API and
# the SQLite test schema already use.
ID = Uuid(as_uuid=False)


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column("project_id", ID, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    tier: Mapped[str] = mapped_column(String(16), default="free")
    capture_prompt: Mapped[bool] = mapped_column(Boolean, default=False)
    redact_patterns: Mapped[list] = mapped_column(JSON, default=list)
    retention_days: Mapped[int] = mapped_column(Integer, default=7)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column("api_key_id", ID, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ID, ForeignKey("projects.project_id"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="default")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Trace(Base):
    __tablename__ = "traces"
    id: Mapped[str] = mapped_column("trace_id", ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ID, ForeignKey("projects.project_id"), index=True
    )
    config_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rag_index_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="ok")
    total_cost_actual: Mapped[float] = mapped_column(Float, default=0)
    total_cost_estimated: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Span(Base):
    __tablename__ = "spans"
    id: Mapped[str] = mapped_column("span_id", ID, primary_key=True)
    trace_id: Mapped[str] = mapped_column(ID, ForeignKey("traces.trace_id"), index=True)
    parent_span_id: Mapped[str | None] = mapped_column(
        ID, ForeignKey("spans.span_id"), nullable=True
    )
    type: Mapped[str] = mapped_column("span_type", String(32), default="llm_call")
    name: Mapped[str] = mapped_column(String(160), default="llm_call")
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tokens_in: Mapped[int] = mapped_column("prompt_tokens", Integer, default=0)
    tokens_out: Mapped[int] = mapped_column("completion_tokens", Integer, default=0)
    cost_actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_estimated: Mapped[float] = mapped_column(Float, default=0)
    risk_score: Mapped[float] = mapped_column("injection_risk_score", Float, default=0)
    risk_tags: Mapped[list] = mapped_column("injection_risk_tags", JSON, default=list)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column("job_id", ID, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[str] = mapped_column("eval_run_id", ID, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ID, ForeignKey("projects.project_id"), index=True
    )
    dataset_version: Mapped[str] = mapped_column(String(120))
    config_id: Mapped[str] = mapped_column(String(120), index=True)
    baseline_score: Mapped[float] = mapped_column(Float)
    variance: Mapped[float] = mapped_column(Float)
    result_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    worst_cases: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column("alert_id", ID, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(
        ID, ForeignKey("projects.project_id"), index=True
    )
    eval_run_id: Mapped[str] = mapped_column(
        ID, ForeignKey("eval_runs.eval_run_id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), default="regression")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
