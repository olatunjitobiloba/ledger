from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from .config import ADMIN_TOKEN, AUTO_CREATE_SCHEMA, CORS_ORIGINS, POLL_SECONDS
from .database import Base, SessionLocal, engine
from .migrate import apply_migrations
from .models import Alert, EvalRun, Job, Project, Span, Trace
from .services import authenticate, make_api_key, process_one_job, purge_expired

logger = logging.getLogger("ledger_api")


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def worker() -> None:
    while True:
        db = SessionLocal()
        try:
            process_one_job(db)
        finally:
            db.close()
        await asyncio.sleep(POLL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if AUTO_CREATE_SCHEMA:
        Base.metadata.create_all(engine)
    # Apply any pending SQL migrations.  For Postgres this is the primary
    # schema management path; for SQLite it catches additions like new columns.
    try:
        apply_migrations(engine)
    except Exception:
        logger.exception("migration runner failed — continuing with current schema")
    task = asyncio.create_task(worker())
    yield
    task.cancel()


app = FastAPI(title="Ledger API", version="0.1.0", lifespan=lifespan)


# Registered before CORSMiddleware so it runs inside it: unexpected errors then
# leave with CORS headers and a JSON body that browsers can read, instead of a
# bare 500 that a cross-origin dashboard can only report as a network failure.
@app.middleware("http")
async def json_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except DBAPIError:
        logger.exception("database error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "database unavailable"}, status_code=503)
    except Exception:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "internal server error"}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tier: str = "free"
    capture_prompt: bool = False
    redact_patterns: list[str] = []
    retention_days: int = Field(default=7, ge=1, le=3650)


class ApiKeyIn(BaseModel):
    name: str = Field(default="default", max_length=120)


class SpanIn(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    type: str = "llm_call"
    name: str | None = None
    model: str | None = None
    started_at: dt.datetime | None = None
    ended_at: dt.datetime | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_actual: float | None = None
    latency_ms: float | None = None
    prompt: str | None = None
    response: str | None = None
    usage: dict[str, Any] | None = None
    detect_injection: bool = False


class TraceIn(BaseModel):
    trace_id: str
    config_id: str | None = None
    prompt_hash: str | None = None
    model: str | None = None
    rag_index_version: str | None = None
    status: str = "ok"
    spans: list[SpanIn]


class IngestIn(BaseModel):
    traces: list[TraceIn] = Field(min_length=1, max_length=500)


# Frozen SDK contract: one span per SDK call. The batch shape above remains
# supported for efficient exporters and the PRD endpoint contract.
class SdkSpanIn(BaseModel):
    span_id: str | None = None
    parent_span_id: str | None = None
    span_type: str = "llm_call"
    name: str
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_actual: float | None = None
    capture_prompt: bool = False
    prompt_text: str | None = None
    response_text: str | None = None
    metadata: dict[str, Any] = {}
    detect_injection: bool = False


class SdkIngestIn(BaseModel):
    trace_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    status: str = "pending"
    metadata: dict[str, Any] = {}
    span: SdkSpanIn


class EvalCase(BaseModel):
    prompt: str
    response: str


class EvalIn(BaseModel):
    dataset_version: str
    config_id: str
    model: str | None = Field(default=None, max_length=120)
    baseline_score: float = Field(ge=0, le=100)
    variance: float = Field(ge=0, le=100)
    cases: list[EvalCase] = Field(min_length=1, max_length=500)


def project_auth(
    x_api_key: str | None = Header(default=None), db: Session = Depends(db_session)
) -> Project:
    project = authenticate(db, x_api_key)
    if not project:
        raise HTTPException(status_code=401, detail="valid X-API-Key required")
    return project


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(db_session)):
    """Read-only readiness check so a database fault is visible from outside."""
    try:
        db.execute(text("SELECT 1"))
    except DBAPIError as exc:
        logger.exception("database health check failed")
        return JSONResponse(
            {"database": "unavailable", "kind": type(exc.orig).__name__},
            status_code=503,
        )
    return {"database": "ok"}


@app.post("/v1/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectIn,
    x_admin_token: str | None = Header(default=None),
    db: Session = Depends(db_session),
):
    if ADMIN_TOKEN and x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "admin token required")
    if body.tier == "free" and body.retention_days > 7:
        raise HTTPException(422, "free tier is limited to 7-day retention")
    for pattern in body.redact_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(422, f"invalid redact pattern: {exc}")
    if db.scalar(select(Project.id).where(Project.name == body.name)):
        raise HTTPException(409, f"a project named {body.name!r} already exists")
    project = Project(**body.model_dump())
    db.add(project)
    try:
        db.flush()
        secret = make_api_key(db, project.id)
        db.commit()
    except IntegrityError:
        # Covers the race where another request inserted the same name between
        # the check above and this insert.
        db.rollback()
        raise HTTPException(409, f"a project named {body.name!r} already exists")
    return {
        "project_id": project.id,
        "api_key": secret,
        "retention_days": project.retention_days,
    }


@app.post("/v1/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: ApiKeyIn,
    project: Project = Depends(project_auth),
    db: Session = Depends(db_session),
):
    secret = make_api_key(db, project.id, body.name)
    db.commit()
    return {"api_key": secret, "project_id": project.id}


@app.post("/v1/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest(
    body: IngestIn | SdkIngestIn,
    project: Project = Depends(project_auth),
    db: Session = Depends(db_session),
):
    if isinstance(body, SdkIngestIn):
        span = body.span
        body = IngestIn(
            traces=[
                TraceIn(
                    trace_id=body.trace_id or str(uuid.uuid4()),
                    status=body.status,
                    spans=[
                        SpanIn(
                            span_id=span.span_id or str(uuid.uuid4()),
                            parent_span_id=span.parent_span_id,
                            type=span.span_type,
                            name=span.name,
                            started_at=span.started_at,
                            ended_at=span.ended_at,
                            model=span.model,
                            tokens_in=span.prompt_tokens,
                            tokens_out=span.completion_tokens,
                            cost_actual=span.cost_actual,
                            prompt=span.prompt_text if span.capture_prompt else None,
                            response=span.response_text
                            if span.capture_prompt
                            else None,
                            detect_injection=span.detect_injection,
                        )
                    ],
                )
            ]
        )
    job = Job(
        kind="ingest",
        payload={
            "project_id": project.id,
            "traces": [t.model_dump(mode="json") for t in body.traces],
        },
    )
    db.add(job)
    db.commit()
    return {"accepted": True, "job_id": job.id}


@app.get("/v1/traces/{project_id}")
def traces(
    project_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    project: Project = Depends(project_auth),
    db: Session = Depends(db_session),
):
    if project.id != project_id:
        raise HTTPException(403, "project mismatch")
    rows = db.scalars(
        select(Trace)
        .where(Trace.project_id == project_id)
        .order_by(Trace.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    items = []
    for trace in rows:
        risk = max(
            (
                span.risk_score
                for span in db.scalars(select(Span).where(Span.trace_id == trace.id))
            ),
            default=0.0,
        )
        items.append(
            {
                "trace_id": trace.id,
                "status": trace.status,
                "model": trace.model,
                "cost_actual": trace.total_cost_actual,
                "cost_estimated": trace.total_cost_estimated,
                "risk_score": risk,
            }
        )
    return {"items": items, "offset": offset, "limit": limit}


@app.post("/v1/eval/run", status_code=status.HTTP_202_ACCEPTED)
def eval_run(
    body: EvalIn,
    project: Project = Depends(project_auth),
    db: Session = Depends(db_session),
):
    run = EvalRun(
        project_id=project.id,
        dataset_version=body.dataset_version,
        config_id=body.config_id,
        model=body.model,
        baseline_score=body.baseline_score,
        variance=body.variance,
    )
    db.add(run)
    db.flush()
    db.add(
        Job(
            kind="eval",
            payload={
                "eval_run_id": run.id,
                "cases": [c.model_dump() for c in body.cases],
            },
        )
    )
    db.commit()
    return {"accepted": True, "eval_run_id": run.id}


@app.get("/v1/eval/runs/{project_id}")
def eval_runs(
    project_id: str,
    project: Project = Depends(project_auth),
    db: Session = Depends(db_session),
):
    if project.id != project_id:
        raise HTTPException(403, "project mismatch")
    rows = db.scalars(
        select(EvalRun)
        .where(EvalRun.project_id == project_id)
        .order_by(EvalRun.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "eval_run_id": r.id,
                "dataset_version": r.dataset_version,
                "config_id": r.config_id,
                "model": r.model,
                "baseline_score": r.baseline_score,
                "variance": r.variance,
                "result_score": r.result_score,
                "passed": r.passed,
                "status": r.status,
                "worst_cases": r.worst_cases,
            }
            for r in rows
        ]
    }


@app.get("/v1/alerts/{project_id}")
def alerts(
    project_id: str,
    project: Project = Depends(project_auth),
    db: Session = Depends(db_session),
):
    if project.id != project_id:
        raise HTTPException(403, "project mismatch")
    return {
        "items": [
            {
                "alert_id": a.id,
                "eval_run_id": a.eval_run_id,
                "kind": a.kind,
                "message": a.message,
            }
            for a in db.scalars(select(Alert).where(Alert.project_id == project_id))
        ]
    }


@app.post("/internal/maintenance/purge")
def purge(
    x_admin_token: str | None = Header(default=None), db: Session = Depends(db_session)
):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "admin token required")
    return {"purged_traces": purge_expired(db)}
