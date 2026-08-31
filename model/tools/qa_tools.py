"""
Deterministic Python tools for the QA Copilot.
All queries strictly require and enforce `thread_id` scope.
Input validated and returns structured dictionaries/lists — no arbitrary SQL execution.
"""

import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..database.models import (
    Thread,
    Document,
    ProcessingRun,
    ReconciliationResult,
    ExceptionItemResult,
    DocumentRecord
)
from ..database.repositories import log_audit


def _sanitize_limit(limit: int, default: int = 50, max_limit: int = 500) -> int:
    """Validate and constrain integer limit parameters."""
    if not isinstance(limit, int) or limit <= 0:
        return default
    return min(limit, max_limit)


def get_thread_documents_tool(db: Session, thread_id: str) -> List[Dict[str, Any]]:
    """Retrieve all uploaded documents in the thread."""
    if not thread_id:
        return []
    docs = (
        db.query(Document)
        .filter(Document.thread_id == thread_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return [{
        "document_id": d.id,
        "filename": d.filename,
        "file_type": d.file_type,
        "record_count": d.record_count,
        "document_type": d.document_type,
        "processing_status": d.processing_status,
        "sha256": d.content_hash_sha256[:12] + "...",
        "dataset_fingerprint": d.dataset_fingerprint[:12] + "..." if d.dataset_fingerprint else None,
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None
    } for d in docs]


def get_reconciliation_summary_tool(db: Session, thread_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve the latest reconciliation KPI summary for the thread."""
    if not thread_id:
        return {"status": "INVALID_THREAD", "message": "Thread ID required."}

    query = db.query(ProcessingRun).filter(ProcessingRun.thread_id == thread_id)
    if run_id:
        run = query.filter(ProcessingRun.id == run_id).first()
    else:
        run = query.order_by(ProcessingRun.created_at.desc()).first()

    if not run:
        # Check if documents are uploaded
        docs = db.query(Document).filter(Document.thread_id == thread_id).all()
        if docs:
            return {
                "status": "PENDING_RECONCILIATION",
                "message": f"{len(docs)} document(s) are uploaded in this thread, but reconciliation has not been executed yet."
            }
        return {"status": "NO_DATA", "message": "No documents or reconciliation runs found for this thread."}

    return {
        "run_id": run.id,
        "status": run.status,
        "total_records": run.total_records,
        "matched_count": run.matched_count,
        "unmatched_count": run.unmatched_count,
        "exceptions_count": run.exceptions_count,
        "match_rate": run.match_rate,
        "accuracy": run.accuracy,
        "precision": run.precision_rate,
        "recall": run.recall_rate,
        "f1_score": run.f1_score,
        "processing_time_sec": run.processing_time_sec,
        "throughput_records_sec": run.throughput_rec_sec,
        "total_amount_processed": run.total_amount_processed,
        "total_amount_matched": run.total_amount_matched,
        "total_amount_discrepancy": run.total_amount_discrepancy,
        "created_at": run.created_at.isoformat() if run.created_at else None
    }


def get_unmatched_transactions_tool(
    db: Session, thread_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieve all unmatched / exception transactions in this thread."""
    if not thread_id:
        return []
    safe_limit = _sanitize_limit(limit, default=50)
    exceptions = (
        db.query(ExceptionItemResult)
        .filter(ExceptionItemResult.thread_id == thread_id)
        .order_by(ExceptionItemResult.amount_discrepancy.desc())
        .limit(safe_limit)
        .all()
    )
    return [{
        "exception_id": e.id,
        "record_id": e.record_id,
        "source": e.source,
        "amount": e.amount,
        "date": e.date,
        "reason_code": e.reason_code,
        "discrepancy_category": e.discrepancy_category,
        "amount_discrepancy": e.amount_discrepancy,
        "explanation": e.explanation,
        "decision": e.decision,
        "evidence": json.loads(e.evidence_json) if e.evidence_json else {}
    } for e in exceptions]


def get_ambiguous_transactions_tool(
    db: Session, thread_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieve ambiguous multi-candidate transactions held for human review."""
    if not thread_id:
        return []
    safe_limit = _sanitize_limit(limit, default=50)
    exceptions = (
        db.query(ExceptionItemResult)
        .filter(
            ExceptionItemResult.thread_id == thread_id,
            ExceptionItemResult.reason_code == "AMBIGUOUS_CANDIDATES"
        )
        .limit(safe_limit)
        .all()
    )
    return [{
        "exception_id": e.id,
        "record_id": e.record_id,
        "source": e.source,
        "amount": e.amount,
        "reason_code": e.reason_code,
        "explanation": e.explanation,
        "candidates": json.loads(e.candidates_json) if e.candidates_json else [],
        "evidence": json.loads(e.evidence_json) if e.evidence_json else {}
    } for e in exceptions]


def get_transaction_result_tool(
    db: Session, thread_id: str, record_id: str
) -> Dict[str, Any]:
    """
    Retrieve match, exception, or document record evidence for a specific transaction ID.
    Strictly scoped to thread_id.
    """
    if not thread_id or not record_id:
        return {"type": "NOT_FOUND", "message": "Thread ID and Record ID are required."}

    clean_id = record_id.strip()

    # 1. Search in Reconciliation Results (Matches)
    matches = (
        db.query(ReconciliationResult)
        .filter(
            ReconciliationResult.thread_id == thread_id,
            (ReconciliationResult.record_id_a == clean_id) |
            (ReconciliationResult.record_id_b == clean_id) |
            (ReconciliationResult.record_id_a.contains(clean_id)) |
            (ReconciliationResult.record_id_b.contains(clean_id))
        )
        .all()
    )
    if matches:
        m = matches[0]
        return {
            "type": "MATCHED",
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
            "category": m.match_category,
            "status": m.status,
            "evidence": json.loads(m.evidence_json) if m.evidence_json else {},
            "score_breakdown": json.loads(m.score_breakdown_json) if m.score_breakdown_json else {}
        }

    # 2. Search in Reconciliation Exceptions
    exceptions = (
        db.query(ExceptionItemResult)
        .filter(
            ExceptionItemResult.thread_id == thread_id,
            (ExceptionItemResult.record_id == clean_id) |
            (ExceptionItemResult.record_id.contains(clean_id))
        )
        .all()
    )
    if exceptions:
        e = exceptions[0]
        return {
            "type": "EXCEPTION",
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
            "evidence": json.loads(e.evidence_json) if e.evidence_json else {}
        }

    # 3. Fallback: Search in Document Records (Uploaded files before reconciliation)
    doc_records = (
        db.query(DocumentRecord)
        .filter(
            DocumentRecord.thread_id == thread_id,
            (DocumentRecord.record_id == clean_id) |
            (DocumentRecord.record_id.contains(clean_id)) |
            (DocumentRecord.reference_id == clean_id) |
            (DocumentRecord.clean_reference_id == clean_id)
        )
        .all()
    )
    if doc_records:
        dr = doc_records[0]
        return {
            "type": "DOCUMENT_RECORD",
            "record_id": dr.record_id,
            "source": dr.source,
            "amount": dr.amount,
            "currency": dr.currency,
            "date": dr.iso_date,
            "entity": dr.entity,
            "reference_id": dr.reference_id,
            "description": dr.description,
            "status": "UNPROCESSED",
            "message": f"Record '{dr.record_id}' is recorded in thread documents with amount ${dr.amount:,.2f}."
        }

    return {
        "type": "NOT_FOUND",
        "message": f"Record '{record_id}' not found in thread {thread_id}."
    }


def get_material_exceptions_tool(
    db: Session, thread_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieve high-priority material discrepancies requiring finance controller action."""
    if not thread_id:
        return []
    safe_limit = _sanitize_limit(limit, default=50)
    exceptions = (
        db.query(ExceptionItemResult)
        .filter(
            ExceptionItemResult.thread_id == thread_id,
            ExceptionItemResult.discrepancy_category == "MATERIAL"
        )
        .order_by(ExceptionItemResult.amount_discrepancy.desc())
        .limit(safe_limit)
        .all()
    )
    return [{
        "record_id": e.record_id,
        "source": e.source,
        "amount": e.amount,
        "reason_code": e.reason_code,
        "fee_delta": e.amount_discrepancy,
        "explanation": e.explanation,
        "decision": e.decision
    } for e in exceptions]


def get_metrics_tool(db: Session, thread_id: str) -> Dict[str, Any]:
    """Retrieve benchmark metrics for the active thread."""
    return get_reconciliation_summary_tool(db, thread_id)
