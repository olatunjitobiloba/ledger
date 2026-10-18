from __future__ import annotations

import hashlib
import json
import re
import secrets
import datetime as dt
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from judge import judge_output

from .config import BLOB_DIR, MODEL_PRICING
from .models import Alert, ApiKey, EvalRun, Job, Project, Span, Trace, utcnow


INJECTION_PATTERNS = (
    r"ignore (all|any|previous|prior) instructions",
    r"(reveal|show|print) (the )?(system prompt|hidden prompt)",
    r"you are now (dan|jailbroken)",
    r"disregard .* rules",
)


def hash_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def make_api_key(db: Session, project_id: str, name: str = "default") -> str:
    secret = "ldg_" + secrets.token_urlsafe(32)
    db.add(ApiKey(project_id=project_id, name=name, key_hash=hash_key(secret), prefix=secret[:12]))
    return secret


def authenticate(db: Session, token: str | None) -> Project | None:
    if not token:
        return None
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(token), ApiKey.active.is_(True)))
    return db.get(Project, key.project_id) if key else None


def estimated_cost(model: str | None, tokens_in: int, tokens_out: int) -> float:
    price = MODEL_PRICING.get(model or "", {})
    return round(tokens_in * float(price.get("input", 0)) + tokens_out * float(price.get("output", 0)), 10)


def injection_risk(text: str) -> tuple[float, list[str]]:
    hits = [pattern for pattern in INJECTION_PATTERNS if re.search(pattern, text, re.I)]
    return (min(1.0, len(hits) * 0.35), ["possible_prompt_injection"] if hits else [])


def redact(value: str, patterns: list[str]) -> str:
    for pattern in patterns:
        try:
            value = re.sub(pattern, "[REDACTED]", value, flags=re.I)
        except re.error:
            # Rejecting an invalid pattern belongs at project creation; never
            # let one bad configuration crash background ingestion.
            continue
    return value


def parse_timestamp(value: Any) -> dt.datetime | None:
    if value is None or isinstance(value, dt.datetime):
        return value
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def write_blob(project_id: str, trace_id: str, span_id: str, payload: dict[str, Any]) -> str:
    target = BLOB_DIR / project_id / trace_id
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{span_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def process_ingest(db: Session, payload: dict[str, Any]) -> None:
    project = db.get(Project, payload["project_id"])
    if not project:
        raise ValueError("project no longer exists")
    for raw_trace in payload["traces"]:
        trace = db.get(Trace, raw_trace["trace_id"])
        if not trace:
            trace_prompt = "\n".join(str(span.get("prompt", "")) for span in raw_trace.get("spans", []))
            trace = Trace(
                id=raw_trace["trace_id"], project_id=project.id,
                config_id=raw_trace.get("config_id"), prompt_hash=raw_trace.get("prompt_hash") or (hashlib.sha256(trace_prompt.encode()).hexdigest() if trace_prompt else None),
                model=raw_trace.get("model"), rag_index_version=raw_trace.get("rag_index_version"),
                status=raw_trace.get("status", "ok"),
                started_at=raw_trace.get("started_at", utcnow()), ended_at=raw_trace.get("ended_at"),
                total_cost_actual=0.0, total_cost_estimated=0.0,
            )
            db.add(trace)
        total_actual = total_estimated = 0.0
        for raw in raw_trace.get("spans", []):
            if db.get(Span, raw["span_id"]):
                continue  # idempotency for an SDK retry
            token_in, token_out = int(raw.get("tokens_in", 0)), int(raw.get("tokens_out", 0))
            usage = raw.get("usage") or {}
            actual = raw.get("cost_actual", usage.get("cost"))
            estimate = estimated_cost(raw.get("model") or trace.model, token_in, token_out)
            text = f"{raw.get('prompt', '')}\n{raw.get('response', '')}"
            risk, tags = injection_risk(text) if raw.get("detect_injection", False) else (0.0, [])
            payload_ref = None
            if project.capture_prompt and (raw.get("prompt") is not None or raw.get("response") is not None):
                private = {"prompt": redact(str(raw.get("prompt", "")), project.redact_patterns),
                           "response": redact(str(raw.get("response", "")), project.redact_patterns)}
                payload_ref = write_blob(project.id, trace.id, raw["span_id"], private)
            db.add(Span(id=raw["span_id"], trace_id=trace.id, parent_span_id=raw.get("parent_span_id"),
                type=raw.get("type", "llm_call"), name=raw.get("name", raw.get("type", "llm_call")),
                started_at=parse_timestamp(raw.get("started_at")) or utcnow(),
                ended_at=parse_timestamp(raw.get("ended_at")),
                model=raw.get("model") or trace.model,
                tokens_in=token_in, tokens_out=token_out, cost_actual=actual, cost_estimated=estimate,
                risk_score=risk, risk_tags=tags, latency_ms=raw.get("latency_ms"), payload_ref=payload_ref))
            total_actual += float(actual or 0)
            total_estimated += estimate
        trace.total_cost_actual += total_actual
        trace.total_cost_estimated += total_estimated


def process_eval(db: Session, payload: dict[str, Any]) -> None:
    run = db.get(EvalRun, payload["eval_run_id"])
    if not run:
        raise ValueError("eval run no longer exists")
    run.status = "running"
    results = []
    for index, case in enumerate(payload["cases"]):
        # The caller provides the candidate output: Ledger judges it, but never
        # runs untrusted application code or sends a live request synchronously.
        outcome = judge_output(case["prompt"], case["response"])
        if outcome["score"] is not None:
            results.append({"index": index, "score": outcome["score"], "reasoning": outcome["reasoning"], "flags": outcome["flags"]})
    if not results:
        run.status = "failed"
        run.completed_at = utcnow()
        return
    run.result_score = round(sum(item["score"] for item in results) / len(results) * 100, 2)
    run.passed = run.result_score >= run.baseline_score - run.variance
    run.worst_cases = sorted(results, key=lambda item: item["score"])[:3]
    run.status, run.completed_at = "completed", utcnow()
    if not run.passed:
        db.add(Alert(project_id=run.project_id, eval_run_id=run.id,
               message=f"Config {run.config_id} scored {run.result_score}, below gate {run.baseline_score - run.variance:.2f}."))


def process_one_job(db: Session) -> bool:
    job = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1))
    if not job:
        return False
    job.status, job.attempts, job.updated_at = "running", job.attempts + 1, utcnow()
    db.commit()
    try:
        if job.kind == "ingest":
            process_ingest(db, job.payload)
        elif job.kind == "eval":
            process_eval(db, job.payload)
        else:
            raise ValueError(f"unknown job kind {job.kind}")
        job.status, job.updated_at = "done", utcnow()
    except Exception as exc:
        job.error, job.updated_at = str(exc), utcnow()
        job.status = "dead_letter" if job.attempts >= 3 else "queued"
    db.commit()
    return True


def purge_expired(db: Session) -> int:
    count = 0
    for project in db.scalars(select(Project)):
        cutoff = utcnow().timestamp() - project.retention_days * 86400
        old = db.scalars(select(Trace).where(Trace.project_id == project.id)).all()
        for trace in old:
            if trace.created_at.timestamp() < cutoff:
                for span in db.scalars(select(Span).where(Span.trace_id == trace.id)):
                    if span.payload_ref:
                        Path(span.payload_ref).unlink(missing_ok=True)
                    db.delete(span)
                db.delete(trace); count += 1
    db.commit()
    return count
