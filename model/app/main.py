"""
FastAPI Server for AI Finance Controller.
Complete thread-based conversational financial workspace.

Endpoints:
- Threads CRUD (/api/threads)
- Document Registry with hardened ingestion & 2-level duplicate detection (/api/threads/{thread_id}/documents)
- Thread-scoped reconciliation via the canonical service (/api/threads/{thread_id}/reconcile)
- Structured results & exceptions (/api/threads/{thread_id}/results, /exceptions, /metrics)
- Guardrailed financial QA copilot (/api/threads/{thread_id}/messages)
- Suggested questions grounded in actual thread state (/api/threads/{thread_id}/suggestions)
- Append-only audit trail (/api/threads/{thread_id}/audit)
- Observability status (/api/observability/langsmith)

Security invariants enforced here:
- every route is scoped to thread_id; cross-thread access 404s
- uploads are validated (traversal/size/type/mime) and stored under UUID names
- reconciliation NEVER falls back to synthetic data implicitly
- metrics endpoint reports evaluated=false instead of fabricating benchmarks
- legacy endpoints never create threads with caller-controlled ids
"""

import os
import uuid
import json
import secrets
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from ..database.db import get_db, init_db
from ..database.models import (
    Thread,
    Document,
    DocumentRecord,
    ProcessingRun,
    ReconciliationResult,
    ExceptionItemResult,
    AuditLog,
    Message,
)
from ..database.repositories import (
    create_thread,
    get_thread,
    list_threads,
    update_thread_title,
    delete_thread,
    add_message,
    get_thread_messages,
    get_thread_documents,
    get_thread_matches,
    get_thread_exceptions,
    get_latest_run,
    get_audit_trail,
    log_audit,
)
from ..ingestion.registry import DocumentRegistryService, MAX_UPLOAD_BYTES, SUPPORTED_EXTENSIONS
from ..agents.orchestrator import orchestrator
from ..services.reconciliation_service import run_reconciliation, ReconciliationError
from ..observability import langsmith as langsmith_obs
from ..agents.groq_client import groq_client
from ..services.cash_forecaster import cash_forecaster, forecast_data_context
from ..services.tax_matcher import tax_matcher
from ..database.models import CashForecastResult, TaxMatchResult
from ..reconciliation.pandas_reconciler import clean_for_json

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI Finance Controller API",
    description="Agentic finance operations platform with thread isolation, duplicate detection, and deterministic reconciliation.",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS for the Next.js frontend. Never fall back to a wildcard origin while
# credentials are enabled — default to the local dev origin instead.
_configured_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
_allowed_origins = _configured_origins or ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# REQUEST / RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────

class CreateThreadRequest(BaseModel):
    title: Optional[str] = "New Financial Investigation"


class UpdateThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    run_id: Optional[str] = None


class ReconcileRequest(BaseModel):
    user_prompt: Optional[str] = "Reconcile these financial records and isolate discrepancies."
    demo_batch: Optional[bool] = False
    document_ids: Optional[List[str]] = None


class ForecastRequest(BaseModel):
    horizon_days: int = 7
    current_cash_balance: Optional[float] = None


class TaxMatchRequest(BaseModel):
    tax_rate: Optional[float] = 0.18
    tolerance: Optional[float] = 0.05


def _require_thread(db: Session, thread_id: str) -> Thread:
    thread = get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


def _doc_brief(d: Document) -> Dict[str, Any]:
    return {
        "id": d.id,
        "filename": d.filename,
        "file_type": d.file_type,
        "record_count": d.record_count,
        "document_type": d.document_type,
        "document_role": d.document_role,
        "role_confidence": d.role_confidence,
        "role_reason": d.role_reason,
        "processing_status": d.processing_status,
        "sha256": d.content_hash_sha256,
        "dataset_fingerprint": d.dataset_fingerprint,
        "size_bytes": d.size_bytes,
        "duplicate": d.processing_status == "DUPLICATE",
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
    }


# ─────────────────────────────────────────────────────────────
# 0. HEALTH & OBSERVABILITY
# ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "AI Finance Controller API",
        "version": "2.1.0",
        "llm_provider": groq_client.provider_name,
        "llm_model": groq_client.model_name,
        "llm_configured": groq_client.is_available,
    }


@app.get("/api/observability/langsmith")
def langsmith_status():
    """Truthful tracing status — never claims active when unconfigured."""
    return {
        "tracing_active": langsmith_obs.is_tracing_active(),
        "project": langsmith_obs.PROJECT_NAME,
        "endpoint": langsmith_obs.ENDPOINT,
    }


# ─────────────────────────────────────────────────────────────
# 1. THREAD MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.post("/api/threads", status_code=201)
def api_create_thread(req: CreateThreadRequest, db: Session = Depends(get_db)):
    """Create a new conversational financial thread."""
    thread = create_thread(db, title=req.title or "New Financial Investigation")
    return {
        "id": thread.id,
        "title": thread.title,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
    }


@app.get("/api/threads")
def api_list_threads(limit: int = 50, db: Session = Depends(get_db)):
    """List all threads ordered by recent activity."""
    threads = list_threads(db, limit=limit)
    result = []
    for t in threads:
        latest_run = get_latest_run(db, t.id)
        latest_status = None
        if latest_run:
            latest_status = {
                "status": latest_run.status,
                "exceptions_count": latest_run.exceptions_count,
            }
        result.append({
            "id": t.id,
            "title": t.title,
            "document_count": len(t.documents),
            "message_count": len(t.messages),
            "latest_run_status": latest_status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })
    return result


@app.get("/api/threads/{thread_id}")
def api_get_thread(thread_id: str, db: Session = Depends(get_db)):
    """Get thread overview, documents, latest run summary."""
    thread = _require_thread(db, thread_id)

    latest_run = get_latest_run(db, thread_id)
    summary_data = json.loads(latest_run.summary_json) if latest_run and latest_run.summary_json else {}
    evaluated = bool(summary_data.get("evaluated", False))

    return {
        "id": thread.id,
        "title": thread.title,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        "documents": [_doc_brief(d) for d in thread.documents],
        "latest_run": {
            "id": latest_run.id,
            "status": latest_run.status,
            "total_records": latest_run.total_records,
            "source_population": summary_data.get("source_population", latest_run.total_records),
            "counterpart_population": summary_data.get("counterpart_population", 0),
            "matched_count": latest_run.matched_count,
            "exceptions_count": latest_run.exceptions_count,
            "match_rate": latest_run.match_rate,
            "evaluated": evaluated,
            "accuracy": latest_run.accuracy if evaluated else None,
            "precision": latest_run.precision_rate if evaluated else None,
            "recall": latest_run.recall_rate if evaluated else None,
            "f1_score": latest_run.f1_score if evaluated else None,
            "processing_time_sec": latest_run.processing_time_sec,
            "throughput_records_sec": latest_run.throughput_rec_sec,
            "detected_schemas": summary_data.get("detected_schemas", {}),
            "mapped_columns": summary_data.get("mapped_columns", {}),
            "diagnostics": summary_data.get("diagnostics", {}),
            "documents_processed": summary_data.get("documents_processed", []),
            "created_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
        } if latest_run else None,
    }


@app.patch("/api/threads/{thread_id}")
def api_update_thread_title(thread_id: str, req: UpdateThreadRequest, db: Session = Depends(get_db)):
    """Rename thread title."""
    thread = update_thread_title(db, thread_id, req.title)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"id": thread.id, "title": thread.title}


@app.delete("/api/threads/{thread_id}")
def api_delete_thread(thread_id: str, db: Session = Depends(get_db)):
    """Delete thread and all associated documents, matches, and messages."""
    success = delete_thread(db, thread_id)
    if not success:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "success", "message": f"Thread '{thread_id}' deleted."}


# ─────────────────────────────────────────────────────────────
# 2. DOCUMENT REGISTRY & UPLOAD (SECURE, DUPLICATE DETECTION)
# ─────────────────────────────────────────────────────────────

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads"))


@app.post("/api/threads/{thread_id}/documents")
async def api_upload_thread_documents(
    thread_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload documents into a thread. Hardened ingestion:
    - filename validation (traversal/absolute paths/control chars rejected)
    - size limit (25 MB), extension + content sniffing, empty/zero-record rejection
    - two-level duplicate detection (SHA-256 + dataset fingerprint)
    - files stored under server-generated UUID names
    """
    _require_thread(db, thread_id)

    results = []
    for f in files:
        try:
            content = await f.read()
        except Exception:
            results.append({
                "status": "REJECTED",
                "reason_code": "READ_ERROR",
                "message": "Could not read uploaded file.",
                "duplicate_type": None,
            })
            continue

        doc, outcome = DocumentRegistryService.process_and_register_file(
            db=db,
            thread_id=thread_id,
            filename=f.filename,
            content_bytes=content,
            upload_dir=UPLOAD_DIR,
        )
        results.append(outcome)

    ok_count = sum(1 for r in results if r.get("status") == "SUCCESS")
    dup_count = sum(1 for r in results if str(r.get("status", "")).startswith("DUPLICATE"))
    rejected_count = sum(1 for r in results if r.get("status") == "REJECTED")

    return {
        "status": "success",
        "thread_id": thread_id,
        "uploaded_count": ok_count,
        "duplicate_count": dup_count,
        "rejected_count": rejected_count,
        "results": results,
    }


@app.get("/api/threads/{thread_id}/documents")
def api_get_thread_documents(thread_id: str, db: Session = Depends(get_db)):
    """Get all documents in the thread registry."""
    _require_thread(db, thread_id)
    docs = get_thread_documents(db, thread_id)
    return [_doc_brief(d) for d in docs]


# ─────────────────────────────────────────────────────────────
# 3. RECONCILIATION EXECUTION (THREAD SCOPED, CANONICAL SERVICE)
# ─────────────────────────────────────────────────────────────

@app.post("/api/threads/{thread_id}/reconcile")
def api_reconcile_thread(
    thread_id: str,
    req: ReconcileRequest,
    db: Session = Depends(get_db),
):
    """
    Execute deterministic reconciliation on documents uploaded to this thread.

    Never falls back to synthetic data: an empty thread returns a 400 with an
    actionable message. The explicit `demo_batch=True` flag (development/demo
    mechanism) runs the bundled benchmark batch against its ground truth.
    """
    _require_thread(db, thread_id)

    try:
        result = run_reconciliation(
            db=db,
            thread_id=thread_id,
            user_prompt=req.user_prompt,
            document_ids=req.document_ids,
            demo=bool(req.demo_batch),
        )
    except ReconciliationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


# ─────────────────────────────────────────────────────────────
# 4. STRUCTURED RESULTS & EVIDENCE ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.get("/api/threads/{thread_id}/results")
def api_get_thread_results(
    thread_id: str,
    run_id: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=250, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve reconciled pairs with complete evidence scoped to thread."""
    _require_thread(db, thread_id)
    matches, total = get_thread_matches(
        db=db,
        thread_id=thread_id,
        run_id=run_id,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "matches": [{
            "match_id": m.id,
            "record_id_a": m.record_id_a,
            "record_id_b": m.record_id_b,
            "source_a": m.source_a,
            "source_b": m.source_b,
            "amount_a": m.amount_a,
            "amount_b": m.amount_b,
            "date_a": m.date_a,
            "date_b": m.date_b,
            "entity_a": m.entity_a,
            "entity_b": m.entity_b,
            "confidence_score": m.confidence_score,
            "match_category": m.match_category,
            "status": m.status,
            "evidence": clean_for_json(json.loads(m.evidence_json)) if m.evidence_json else {},
            "score_breakdown": clean_for_json(json.loads(m.score_breakdown_json)) if m.score_breakdown_json else {},
        } for m in matches]
    }


@app.get("/api/threads/{thread_id}/exceptions")
def api_get_thread_exceptions(
    thread_id: str,
    run_id: Optional[str] = None,
    reason: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = Query(default="discrepancy", pattern="^(discrepancy|recent|amount)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve exceptions with evidence scoped to thread."""
    _require_thread(db, thread_id)
    exceptions, total = get_thread_exceptions(
        db=db,
        thread_id=thread_id,
        run_id=run_id,
        reason=reason,
        category=category,
        search=search,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "exceptions": [{
            "exception_id": e.id,
            "record_id": e.record_id,
            "source": e.source,
            "amount": e.amount,
            "entity": e.entity,
            "date": e.date,
            "reason_code": e.reason_code,
            "discrepancy_category": e.discrepancy_category,
            "confidence": e.confidence,
            "decision": e.decision,
            "explanation": e.explanation,
            "amount_discrepancy": e.amount_discrepancy,
            "candidates": clean_for_json(json.loads(e.candidates_json)) if e.candidates_json else [],
            "evidence": clean_for_json(json.loads(e.evidence_json)) if e.evidence_json else {},
        } for e in exceptions]
    }


@app.get("/api/threads/{thread_id}/metrics")
def api_get_thread_metrics(
    thread_id: str,
    run_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Get metrics for the latest run in this thread.

    Evaluation metrics (precision/recall/f1/accuracy/confusion matrix) are
    returned ONLY when the run was explicitly evaluated against an authorized
    ground truth. Otherwise evaluated=false and eval fields are null —
    never fabricated.
    """
    _require_thread(db, thread_id)

    if run_id:
        run = db.query(ProcessingRun).filter(
            ProcessingRun.thread_id == thread_id, ProcessingRun.id == run_id
        ).first()
    else:
        run = get_latest_run(db, thread_id)

    if not run:
        raise HTTPException(status_code=404, detail="No reconciliation run exists for this thread yet.")

    summary_data = json.loads(run.summary_json) if run.summary_json else {}
    eval_metrics = summary_data.get("evaluation_metrics", {}) if summary_data else {}
    evaluated = bool(summary_data.get("evaluated", False))

    return {
        "run_id": run.id,
        "thread_id": thread_id,
        "evaluated": evaluated,
        "total_ground_truth_cases": eval_metrics.get("total_ground_truth_cases") if evaluated else None,
        "true_positives": eval_metrics.get("true_positives") if evaluated else None,
        "false_positives": eval_metrics.get("false_positives") if evaluated else None,
        "false_negatives": eval_metrics.get("false_negatives") if evaluated else None,
        "true_negatives": eval_metrics.get("true_negatives") if evaluated else None,
        "precision": run.precision_rate if evaluated else None,
        "recall": run.recall_rate if evaluated else None,
        "f1_score": run.f1_score if evaluated else None,
        "accuracy": run.accuracy if evaluated else None,
        "match_rate": run.match_rate,
        "total_records": run.total_records,
        "source_population": summary_data.get("source_population", run.total_records),
        "counterpart_population": summary_data.get("counterpart_population", 0),
        "matched_count": run.matched_count,
        "exceptions_count": run.exceptions_count,
        "processing_time_sec": run.processing_time_sec,
        "throughput_records_sec": run.throughput_rec_sec,
        "confusion_matrix": eval_metrics.get("detailed_metrics_json", {}).get("confusion_matrix", {}) if evaluated else {},
    }


# ─────────────────────────────────────────────────────────────
# 4.5 CASH FORECASTING & TAX-LINE MATCHING ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.post("/api/threads/{thread_id}/forecast")
def api_run_forecast(
    thread_id: str,
    req: ForecastRequest = ForecastRequest(),
    db: Session = Depends(get_db),
):
    """Run deterministic forward cash forecasting for 7, 14, or 30 days."""
    _require_thread(db, thread_id)
    return cash_forecaster.run_forecast(
        db=db,
        thread_id=thread_id,
        horizon_days=req.horizon_days,
        current_cash_balance=req.current_cash_balance,
    )


@app.get("/api/threads/{thread_id}/forecast")
def api_get_forecast(
    thread_id: str,
    horizon_days: int = 7,
    db: Session = Depends(get_db),
):
    """Get latest cash forecast or generate fresh projection."""
    _require_thread(db, thread_id)
    latest = (
        db.query(CashForecastResult)
        .filter(CashForecastResult.thread_id == thread_id)
        .order_by(CashForecastResult.created_at.desc())
        .first()
    )
    if latest and latest.horizon_days == horizon_days:
        daily = json.loads(latest.daily_forecast_json) if latest.daily_forecast_json else []
        context = forecast_data_context(daily)
        return {
            "status": "COMPLETED",
            "forecast_id": latest.id,
            "thread_id": latest.thread_id,
            "horizon_days": latest.horizon_days,
            "current_cash_balance": latest.current_cash_balance,
            "baseline_source": latest.baseline_source,
            "projected_inflows": latest.projected_inflows,
            "projected_outflows": latest.projected_outflows,
            "net_projected_change": latest.net_projected_change,
            "projected_ending_cash": latest.projected_ending_cash,
            "confidence_level": latest.confidence_level,
            "methodology": latest.methodology,
            "assumptions": json.loads(latest.assumptions_json) if latest.assumptions_json else [],
            "analysis_date": context["analysis_date"],
            "historical_window_end": context["historical_window_end"],
            "dataset_is_stale": context["dataset_is_stale"],
            "stale_note": context["stale_note"],
            "outflows_observed": bool(latest.projected_outflows and latest.projected_outflows > 0),
            "daily_projections": daily,
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
        }
    return cash_forecaster.run_forecast(db=db, thread_id=thread_id, horizon_days=horizon_days)


@app.post("/api/threads/{thread_id}/tax-match")
def api_run_tax_match(
    thread_id: str,
    req: TaxMatchRequest = TaxMatchRequest(),
    db: Session = Depends(get_db),
):
    """Run deterministic tax-line matching on thread records."""
    _require_thread(db, thread_id)
    return tax_matcher.run_tax_matching(
        db=db,
        thread_id=thread_id,
        tax_rate=req.tax_rate,
        tolerance=req.tolerance,
    )


@app.get("/api/threads/{thread_id}/tax-match")
def api_get_tax_match(
    thread_id: str,
    db: Session = Depends(get_db),
):
    """Get latest tax-line matching results for thread."""
    _require_thread(db, thread_id)
    lines = (
        db.query(TaxMatchResult)
        .filter(TaxMatchResult.thread_id == thread_id)
        .order_by(TaxMatchResult.created_at.asc())
        .all()
    )
    if lines:
        matched_count = sum(1 for l in lines if l.status == "MATCH")
        mismatched_count = sum(1 for l in lines if l.status == "MISMATCH")
        missing_count = sum(1 for l in lines if l.status == "MISSING")
        ambiguous_count = sum(1 for l in lines if l.status == "AMBIGUOUS")
        not_applicable_count = sum(1 for l in lines if l.status == "NOT_TAX_APPLICABLE")
        unavailable_count = sum(1 for l in lines if l.status == "TAX_DATA_UNAVAILABLE")
        eligible_count = matched_count + mismatched_count + missing_count + ambiguous_count + unavailable_count
        total = len(lines)
        rate = (matched_count / eligible_count * 100.0) if eligible_count > 0 else 0.0
        return {
            "status": "COMPLETED",
            "thread_id": thread_id,
            "total_records": total,
            "tax_eligible_count": eligible_count,
            "matched_count": matched_count,
            "mismatched_count": mismatched_count,
            "missing_count": missing_count,
            "ambiguous_count": ambiguous_count,
            "not_applicable_count": not_applicable_count,
            "unavailable_count": unavailable_count,
            "tax_match_rate": round(rate, 2),
            "total_tax_expected": sum(l.expected_tax for l in lines),
            "total_tax_reported": sum(l.reported_tax for l in lines),
            "total_tax_discrepancy": sum(l.tax_difference for l in lines),
            "net_tax_variance": sum(l.reported_tax - l.expected_tax for l in lines),
            "tax_lines": [{
                "id": l.id,
                "record_id": l.record_id,
                "source": l.source,
                "taxable_amount": l.taxable_amount,
                "tax_rate": l.tax_rate if l.tax_rate else None,
                "expected_tax": l.expected_tax,
                "reported_tax": l.reported_tax,
                "tax_difference": l.tax_difference,
                "status": l.status,
                "explanation": l.explanation,
                "evidence": json.loads(l.evidence_json) if l.evidence_json else {},
            } for l in lines],
        }
    return tax_matcher.run_tax_matching(db=db, thread_id=thread_id)


# ─────────────────────────────────────────────────────────────
# 5. CHAT / Q&A ENDPOINTS (THREAD SCOPED & GUARDRAILED)
# ─────────────────────────────────────────────────────────────

@app.get("/api/threads/{thread_id}/messages")
def api_get_thread_messages(thread_id: str, limit: int = 100, db: Session = Depends(get_db)):
    """Retrieve chat history for this thread."""
    _require_thread(db, thread_id)
    msgs = get_thread_messages(db, thread_id, limit=limit)
    return [{
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "metadata": json.loads(m.metadata_json) if m.metadata_json else {},
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in msgs]


@app.post("/api/threads/{thread_id}/messages")
def api_send_thread_message(
    thread_id: str,
    req: SendMessageRequest,
    db: Session = Depends(get_db),
):
    """
    Send a message to the thread. Orchestrator executes:
    - six-layer guardrails (safety, domain, thread scope, tool permission,
      evidence validation, output safety)
    - intent routing (QA vs Reconciliation — both thread-scoped & persisted)
    - deterministic tool queries over structured results
    """
    _require_thread(db, thread_id)

    # 1. Record user message
    user_msg = add_message(db=db, thread_id=thread_id, role="user", content=req.content)

    # 2. Invoke orchestrator (chat reconciliation persists everything, same as REST)
    result = orchestrator.handle_request(
        db=db,
        thread_id=thread_id,
        user_prompt=req.content,
        run_id=req.run_id,
    )

    answer = result.get("answer", "")
    if result.get("intent") == "RECONCILIATION" and result.get("status") == "COMPLETED":
        # The canonical service already appended a detailed summary message;
        # surface a short pointer in the chat response.
        answer = answer or "Reconciliation completed — see the summary above and the Results tabs."

    # 3. Record assistant response
    asst_msg = add_message(
        db=db,
        thread_id=thread_id,
        role="assistant",
        content=answer,
        metadata={
            "intent": result.get("intent"),
            "answer_source": result.get("answer_source"),
            "tools_called": result.get("tools_called", []),
            "query_type": result.get("query_type"),
            "retrieved_records_count": len(result.get("retrieved_records", [])),
            "retrieved_exceptions_count": len(result.get("retrieved_exceptions", [])),
        },
    )

    def _clean_items(items):
        out = []
        for it in items or []:
            if isinstance(it, dict):
                out.append({k: v for k, v in it.items() if k != "_meta"})
        return out

    return {
        "user_message": {
            "id": user_msg.id,
            "role": user_msg.role,
            "content": user_msg.content,
            "created_at": user_msg.created_at.isoformat() if user_msg.created_at else None,
        },
        "assistant_message": {
            "id": asst_msg.id,
            "role": asst_msg.role,
            "content": asst_msg.content,
            "metadata": json.loads(asst_msg.metadata_json) if asst_msg.metadata_json else {},
            "created_at": asst_msg.created_at.isoformat() if asst_msg.created_at else None,
        },
        "intent": result.get("intent"),
        "answer_source": result.get("answer_source"),
        "retrieved_records": _clean_items(result.get("retrieved_records")),
        "retrieved_exceptions": _clean_items(result.get("retrieved_exceptions")),
        "retrieved_metrics": {k: v for k, v in (result.get("retrieved_metrics") or {}).items() if k != "_meta"},
    }


# ─────────────────────────────────────────────────────────────
# 6. SUGGESTED QUESTIONS (grounded in actual thread state)
# ─────────────────────────────────────────────────────────────

@app.get("/api/threads/{thread_id}/suggestions")
def api_get_thread_suggestions(thread_id: str, db: Session = Depends(get_db)):
    """
    Return question suggestions the backend can actually answer for THIS
    thread's current state. Suggested questions are therefore guardrail-safe.
    """
    thread = _require_thread(db, thread_id)
    docs = get_thread_documents(db, thread_id)
    run = get_latest_run(db, thread_id)

    suggestions: List[str] = []

    if len(docs) == 0:
        return {
            "thread_id": thread_id,
            "state": "NO_DOCUMENTS",
            "suggestions": [
                "Which documents have been uploaded to this thread?",
                "What can you help me with?",
            ],
        }

    if not run:
        return {
            "thread_id": thread_id,
            "state": "PENDING_RECONCILIATION",
            "suggestions": [
                "Which documents have been uploaded to this thread?",
                "How many records are in my documents?",
            ],
        }

    # Post-reconciliation suggestions grounded in real data
    suggestions.append("Summarize this thread's reconciliation results")
    if run.exceptions_count > 0:
        suggestions.append("Show me the material exceptions")
        suggestions.append("Why do we have unmatched transactions?")
    exc_sample = (
        db.query(ExceptionItemResult)
        .filter(
            ExceptionItemResult.thread_id == thread_id,
            ExceptionItemResult.reason_code == "AMOUNT_MISMATCH",
        )
        .order_by(ExceptionItemResult.amount_discrepancy.desc())
        .first()
    )
    if exc_sample:
        suggestions.append(f"Explain the largest amount mismatch ({exc_sample.record_id})")
    amb = (
        db.query(ExceptionItemResult)
        .filter(
            ExceptionItemResult.thread_id == thread_id,
            ExceptionItemResult.reason_code == "AMBIGUOUS_CANDIDATE_CONFLICT",
        )
        .count()
    )
    if amb > 0:
        suggestions.append("Which transactions have ambiguous matches?")
    match_sample = (
        db.query(ReconciliationResult)
        .filter(ReconciliationResult.thread_id == thread_id)
        .first()
    )
    if match_sample:
        suggestions.append(f"What is the match status of {match_sample.record_id_a}?")

    return {
        "thread_id": thread_id,
        "state": "READY",
        "suggestions": suggestions[:6],
    }


# ─────────────────────────────────────────────────────────────
# 7. AUDIT TRAIL
# ─────────────────────────────────────────────────────────────

@app.get("/api/threads/{thread_id}/audit")
def api_get_thread_audit(thread_id: str, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    """Retrieve the append-only audit log for this thread."""
    _require_thread(db, thread_id)
    trail = get_audit_trail(db, thread_id, limit=limit)
    return [{
        "id": a.id,
        "run_id": a.run_id,
        "action": a.action,
        "agent": a.agent,
        "tool": a.tool,
        "parameters": json.loads(a.parameters_json) if a.parameters_json else {},
        "result_summary": a.result_summary,
        "details": json.loads(a.details_json) if a.details_json else {},
        "timestamp": a.timestamp.isoformat() if a.timestamp else None,
    } for a in trail]


# ─────────────────────────────────────────────────────────────
# 8. LEGACY COMPATIBILITY ENDPOINTS
# ─────────────────────────────────────────────────────────────

class LegacyRunRequest(BaseModel):
    user_prompt: Optional[str] = "Reconcile these financial records and identify anything that doesn't match."
    demo_batch: bool = False
    file_ids: Optional[List[str]] = None


class LegacyChatRequest(BaseModel):
    question: str
    run_id: Optional[str] = None
    thread_id: Optional[str] = None


def _default_thread(db: Session) -> Thread:
    """Server-controlled default thread for legacy endpoints."""
    thread = db.query(Thread).filter(Thread.id == "thr_default").first()
    if not thread:
        thread = Thread(id="thr_default", title="Reconciliation Workspace")
        db.add(thread)
        db.commit()
        log_audit(db, thread_id="thr_default", action="THREAD_CREATED", details={"title": thread.title})
    return thread


@app.post("/api/reconciliation/run")
def legacy_run_reconciliation(req: LegacyRunRequest, db: Session = Depends(get_db)):
    """Backward-compatible endpoint routing to the server-managed default thread."""
    thread = _default_thread(db)
    try:
        return run_reconciliation(
            db=db,
            thread_id=thread.id,
            user_prompt=req.user_prompt,
            document_ids=req.file_ids,
            demo=bool(req.demo_batch),
        )
    except ReconciliationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/runs")
def legacy_get_all_runs(db: Session = Depends(get_db)):
    """Backward-compatible runs list."""
    runs = db.query(ProcessingRun).order_by(ProcessingRun.created_at.desc()).all()
    return [{
        "id": r.id,
        "thread_id": r.thread_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "status": r.status,
        "user_prompt": r.user_prompt,
        "total_records": r.total_records,
        "matched_records": r.matched_count,
        "exception_records": r.exceptions_count,
        "match_rate": r.match_rate,
        "throughput_rec_sec": r.throughput_rec_sec,
        "processing_time_sec": r.processing_time_sec,
    } for r in runs]


@app.get("/api/reconciliation/{run_id}/matches")
def legacy_get_matches(run_id: str, category: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ReconciliationResult).filter(ReconciliationResult.run_id == run_id)
    if category and category != "ALL":
        query = query.filter(ReconciliationResult.match_category == category)
    if search:
        s = f"%{search}%"
        query = query.filter(
            (ReconciliationResult.record_id_a.like(s)) |
            (ReconciliationResult.record_id_b.like(s)) |
            (ReconciliationResult.entity_a.like(s)) |
            (ReconciliationResult.entity_b.like(s))
        )
    matches = query.all()
    return {
        "total": len(matches),
        "matches": [{
            "match_id": m.id,
            "record_id_a": m.record_id_a,
            "record_id_b": m.record_id_b,
            "source_a": m.source_a,
            "source_b": m.source_b,
            "amount_a": m.amount_a,
            "amount_b": m.amount_b,
            "date_a": m.date_a,
            "date_b": m.date_b,
            "entity_a": m.entity_a,
            "entity_b": m.entity_b,
            "confidence_score": m.confidence_score,
            "match_category": m.match_category,
            "status": m.status,
            "evidence": json.loads(m.evidence_json) if m.evidence_json else {},
            "score_breakdown": json.loads(m.score_breakdown_json) if m.score_breakdown_json else {},
        } for m in matches]
    }


@app.get("/api/reconciliation/{run_id}/exceptions")
def legacy_get_exceptions(run_id: str, reason: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ExceptionItemResult).filter(ExceptionItemResult.run_id == run_id)
    if reason and reason != "ALL":
        query = query.filter(ExceptionItemResult.reason_code == reason)
    if search:
        s = f"%{search}%"
        query = query.filter(
            (ExceptionItemResult.record_id.like(s)) |
            (ExceptionItemResult.entity.like(s)) |
            (ExceptionItemResult.explanation.like(s))
        )
    exceptions = query.all()
    return {
        "total": len(exceptions),
        "exceptions": [{
            "exception_id": e.id,
            "record_id": e.record_id,
            "source": e.source,
            "amount": e.amount,
            "entity": e.entity,
            "date": e.date,
            "reason_code": e.reason_code,
            "discrepancy_category": e.discrepancy_category,
            "confidence": e.confidence,
            "decision": e.decision,
            "explanation": e.explanation,
            "amount_discrepancy": e.amount_discrepancy,
            "candidates": json.loads(e.candidates_json) if e.candidates_json else [],
            "evidence": json.loads(e.evidence_json) if e.evidence_json else {},
        } for e in exceptions]
    }


@app.get("/api/reconciliation/{run_id}/metrics")
def legacy_get_metrics(run_id: str, db: Session = Depends(get_db)):
    run = db.query(ProcessingRun).filter(ProcessingRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    summary_data = json.loads(run.summary_json) if run.summary_json else {}
    eval_metrics = summary_data.get("evaluation_metrics", {}) if summary_data else {}
    evaluated = bool(summary_data.get("evaluated", False))

    return {
        "run_id": run.id,
        "evaluated": evaluated,
        "total_ground_truth_cases": eval_metrics.get("total_ground_truth_cases") if evaluated else None,
        "true_positives": eval_metrics.get("true_positives") if evaluated else None,
        "false_positives": eval_metrics.get("false_positives") if evaluated else None,
        "false_negatives": eval_metrics.get("false_negatives") if evaluated else None,
        "true_negatives": eval_metrics.get("true_negatives") if evaluated else None,
        "precision": run.precision_rate if evaluated else None,
        "recall": run.recall_rate if evaluated else None,
        "f1_score": run.f1_score if evaluated else None,
        "accuracy": run.accuracy if evaluated else None,
        "match_rate": run.match_rate,
        "processing_time_sec": run.processing_time_sec,
        "throughput_records_sec": run.throughput_rec_sec,
        "confusion_matrix": eval_metrics.get("detailed_metrics_json", {}).get("confusion_matrix", {}) if evaluated else {},
    }


@app.post("/api/chat")
def legacy_chat_endpoint(req: LegacyChatRequest, db: Session = Depends(get_db)):
    """Legacy chat — thread must exist (server-created only); no id fabrication."""
    thread_id = req.thread_id
    if thread_id:
        thread = get_thread(db, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
    else:
        thread = _default_thread(db)

    return api_send_thread_message(
        thread_id=thread.id,
        req=SendMessageRequest(content=req.question, run_id=req.run_id),
        db=db,
    )
