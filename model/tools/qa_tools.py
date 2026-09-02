"""
Deterministic Python tools for the QA Copilot.
All queries strictly require and enforce `thread_id` scope — every SQL filter
includes thread_id and lookups use exact identifier matching (never substring
matching). When multiple records could match an identifier, an explicit
ambiguity result is returned instead of silently choosing the first row.

Every tool result carries evidence metadata internally:
    source tool, thread_id, record ids, and the deterministic calculation.
"""

import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..database.models import (
    Thread,
    Document,
    DocumentRecord,
    ProcessingRun,
    ReconciliationResult,
    ExceptionItemResult,
)
from ..database.repositories import log_audit


def _sanitize_limit(limit: int, default: int = 50, max_limit: int = 500) -> int:
    """Validate and constrain integer limit parameters."""
    if not isinstance(limit, int) or limit <= 0:
        return default
    return min(limit, max_limit)


def _normalize_identifier(record_id: str) -> str:
    """
    Normalize an identifier for exact lookup: strip whitespace and outer
    punctuation commonly wrapped around ids (backticks, quotes).
    Does NOT truncate or fuzzy-match — exact match after normalization only.
    """
    return str(record_id or "").strip().strip("`\"'").strip()


def _tool_meta(tool: str, thread_id: str, **extra) -> Dict[str, Any]:
    """Evidence metadata attached to every tool result."""
    meta = {"tool": tool, "thread_id": thread_id}
    meta.update({k: v for k, v in extra.items() if v is not None})
    return meta


def get_thread_documents_tool(db: Session, thread_id: str) -> List[Dict[str, Any]]:
    """Retrieve all uploaded documents in the thread (thread-scoped)."""
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
        "sha256": d.content_hash_sha256,
        "dataset_fingerprint": d.dataset_fingerprint,
        "size_bytes": d.size_bytes,
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "_meta": _tool_meta("get_thread_documents_tool", thread_id, document_ids=[d.id for d in docs]),
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
                "message": f"{len(docs)} document(s) are uploaded in this thread, but reconciliation has not been executed yet.",
                "_meta": _tool_meta("get_reconciliation_summary_tool", thread_id, document_ids=[d.id for d in docs]),
            }
        return {
            "status": "NO_DATA",
            "message": "There is not enough processed data in this thread to answer that question. Please upload documents and run reconciliation.",
            "_meta": _tool_meta("get_reconciliation_summary_tool", thread_id),
        }

    # Evaluation metrics are only surfaced when the run was actually evaluated
    summary_data = json.loads(run.summary_json) if run.summary_json else {}
    evaluated = bool(summary_data.get("evaluated", False))

    return {
        "run_id": run.id,
        "status": run.status,
        "total_records": run.total_records,
        "matched_count": run.matched_count,
        "unmatched_count": run.unmatched_count,
        "exceptions_count": run.exceptions_count,
        "match_rate": run.match_rate,
        "evaluated": evaluated,
        "accuracy": run.accuracy if evaluated else None,
        "precision": run.precision_rate if evaluated else None,
        "recall": run.recall_rate if evaluated else None,
        "f1_score": run.f1_score if evaluated else None,
        "processing_time_sec": run.processing_time_sec,
        "throughput_records_sec": run.throughput_rec_sec,
        "total_amount_processed": run.total_amount_processed,
        "total_amount_matched": run.total_amount_matched,
        "total_amount_discrepancy": run.total_amount_discrepancy,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "_meta": _tool_meta("get_reconciliation_summary_tool", thread_id, run_id=run.id),
    }


def get_unmatched_transactions_tool(
    db: Session, thread_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieve unmatched / exception transactions in this thread (thread-scoped)."""
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
        "evidence": json.loads(e.evidence_json) if e.evidence_json else {},
        "_meta": _tool_meta("get_unmatched_transactions_tool", thread_id, exception_ids=[e.id for e in exceptions]),
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
        "evidence": json.loads(e.evidence_json) if e.evidence_json else {},
        "_meta": _tool_meta("get_ambiguous_transactions_tool", thread_id, exception_ids=[e.id for e in exceptions]),
    } for e in exceptions]


def get_transaction_result_tool(
    db: Session, thread_id: str, record_id: str
) -> Dict[str, Any]:
    """
    Retrieve match, exception, or document-record evidence for a specific
    transaction ID. Strictly scoped to thread_id with EXACT identifier matching.

    Resolution order:
      1. Reconciliation matches (exact id_a / id_b)
      2. Exceptions (exact record_id)
      3. Uploaded document records (exact record_id / reference_id)
    If an identifier matches multiple distinct rows, returns AMBIGUOUS with the
    candidate ids rather than silently selecting one.
    """
    if not thread_id or not record_id:
        return {"type": "NOT_FOUND", "message": "Thread ID and Record ID are required."}

    clean_id = _normalize_identifier(record_id)

    # ── 1. Reconciliation matches (EXACT match only) ──
    matches = (
        db.query(ReconciliationResult)
        .filter(
            ReconciliationResult.thread_id == thread_id,
            (ReconciliationResult.record_id_a == clean_id) |
            (ReconciliationResult.record_id_b == clean_id)
        )
        .all()
    )
    if matches:
        if len(matches) > 1:
            # Same id appearing on both sides of several pairs — ambiguous
            return {
                "type": "AMBIGUOUS",
                "message": (
                    f"'{clean_id}' appears in {len(matches)} matched pairs in this thread. "
                    f"Please specify one of the related pair ids: "
                    + ", ".join(sorted(({m.record_id_a for m in matches} | {m.record_id_b for m in matches}) - {clean_id}))
                ),
                "candidates": [
                    {"match_id": m.id, "record_id_a": m.record_id_a, "record_id_b": m.record_id_b}
                    for m in matches[:10]
                ],
                "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id),
            }
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
            "match_category": m.match_category,
            "status": m.status,
            "evidence": json.loads(m.evidence_json) if m.evidence_json else {},
            "score_breakdown": json.loads(m.score_breakdown_json) if m.score_breakdown_json else {},
            "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id, match_id=m.id),
        }

    # ── 2. Exceptions (EXACT match only) ──
    exceptions = (
        db.query(ExceptionItemResult)
        .filter(
            ExceptionItemResult.thread_id == thread_id,
            ExceptionItemResult.record_id == clean_id
        )
        .all()
    )
    if exceptions:
        if len(exceptions) > 1:
            return {
                "type": "AMBIGUOUS",
                "message": (
                    f"'{clean_id}' is associated with {len(exceptions)} exceptions in this thread: "
                    + ", ".join(e.id for e in exceptions[:10])
                ),
                "candidates": [{"exception_id": e.id, "reason_code": e.reason_code} for e in exceptions[:10]],
                "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id),
            }
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
            "evidence": json.loads(e.evidence_json) if e.evidence_json else {},
            "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id, exception_id=e.id),
        }

    # ── 3. Uploaded document records (EXACT record_id / reference_id) ──
    doc_records = (
        db.query(DocumentRecord)
        .filter(
            DocumentRecord.thread_id == thread_id,
            (DocumentRecord.record_id == clean_id) |
            (DocumentRecord.reference_id == clean_id) |
            (DocumentRecord.clean_reference_id == clean_id)
        )
        .all()
    )
    if doc_records:
        if len(doc_records) > 1:
            return {
                "type": "AMBIGUOUS",
                "message": (
                    f"'{clean_id}' matches {len(doc_records)} uploaded records in this thread. "
                    "Please provide a more specific identifier."
                ),
                "candidates": [
                    {"record_id": dr.record_id, "source": dr.source, "document_id": dr.document_id}
                    for dr in doc_records[:10]
                ],
                "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id),
            }
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
            "status": "UPLOADED_NOT_RECONCILED",
            "message": f"Record '{dr.record_id}' is recorded in thread documents with amount ${dr.amount:,.2f}.",
            "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id, document_id=dr.document_id),
        }

    return {
        "type": "NOT_FOUND",
        "message": f"No such transaction '{record_id}' exists in this thread.",
        "_meta": _tool_meta("get_transaction_result_tool", thread_id, record_id=clean_id),
    }


def get_material_exceptions_tool(
    db: Session, thread_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Retrieve high-priority material discrepancies requiring controller action."""
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
        "exception_id": e.id,
        "record_id": e.record_id,
        "source": e.source,
        "amount": e.amount,
        "reason_code": e.reason_code,
        "fee_delta": e.amount_discrepancy,
        "explanation": e.explanation,
        "decision": e.decision,
        "discrepancy_category": e.discrepancy_category,
        "evidence": json.loads(e.evidence_json) if e.evidence_json else {},
        "_meta": _tool_meta("get_material_exceptions_tool", thread_id, exception_ids=[e.id for e in exceptions]),
    } for e in exceptions]


def get_metrics_tool(db: Session, thread_id: str) -> Dict[str, Any]:
    """Retrieve reconciliation run metrics for the active thread (evaluated metrics only if evaluation ran)."""
    return get_reconciliation_summary_tool(db, thread_id)
