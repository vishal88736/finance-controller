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
import math
import re
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
        "document_role": d.document_role,
        "role_confidence": d.role_confidence,
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
        "detected_schemas": summary_data.get("detected_schemas", {}),
        "mapped_columns": summary_data.get("mapped_columns", {}),
        "candidate_pairs_evaluated": summary_data.get("candidate_pairs_evaluated", 0),
        "mismatch_reasons": summary_data.get("mismatch_reasons", {}),
        "diagnostics": summary_data.get("diagnostics", {}),
        "documents_processed": summary_data.get("documents_processed", []),
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
            ExceptionItemResult.reason_code == "AMBIGUOUS_CANDIDATE_CONFLICT"
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
        (m,) = matches
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


def run_cash_forecast_tool(
    db: Session,
    thread_id: str,
    horizon_days: int = 7,
    current_cash: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute deterministic forward cash forecasting for 7, 14, or 30 days.
    Calculates expected inflows, outflows, and projected closing cash position.
    """
    from ..services.cash_forecaster import cash_forecaster
    result = cash_forecaster.run_forecast(
        db=db,
        thread_id=thread_id,
        horizon_days=horizon_days,
        current_cash_balance=current_cash,
    )
    result["_meta"] = _tool_meta("run_cash_forecast_tool", thread_id, horizon_days=horizon_days)
    return result


def run_tax_match_tool(
    db: Session,
    thread_id: str,
    tax_rate: Optional[float] = None,
    tolerance: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute deterministic tax-line matching comparing taxable amounts against
    reported tax lines and statutory deductions (GST/VAT/sales tax).
    """
    from ..services.tax_matcher import tax_matcher
    result = tax_matcher.run_tax_matching(
        db=db,
        thread_id=thread_id,
        tax_rate=tax_rate,
        tolerance=tolerance,
    )
    result["_meta"] = _tool_meta("run_tax_match_tool", thread_id, tax_rate=tax_rate)
    return result


def run_working_capital_tool(
    db: Session,
    thread_id: str,
    days: int = 365,
) -> Dict[str, Any]:
    """
    Execute deterministic working-capital analysis (DSO / DIO / DPO / CCC) over
    the thread's records. Every number is computed in Python — never by an LLM.
    """
    from ..services.working_capital import working_capital
    result = working_capital.run_analysis(db=db, thread_id=thread_id, days=days)
    result["_meta"] = _tool_meta("run_working_capital_tool", thread_id, days=days)
    return result


def get_settlement_status_tool(db: Session, thread_id: str, limit: int = 50) -> Dict[str, Any]:
    """Retrieve settlement records and payout statuses for the thread."""
    limit = _sanitize_limit(limit)
    settlements = (
        db.query(DocumentRecord)
        .join(Document, DocumentRecord.document_id == Document.id)
        .filter(DocumentRecord.thread_id == thread_id)
        .filter(Document.document_type.in_(["SETTLEMENTS", "PAYMENTS"]))
        .order_by(DocumentRecord.iso_date.desc())
        .limit(limit)
        .all()
    )
    
    # Also surface unresolved exceptions that may indicate pending settlements/payouts.
    exceptions = (
        db.query(ExceptionItemResult)
        .filter(ExceptionItemResult.thread_id == thread_id)
        .filter(ExceptionItemResult.decision == "UNRESOLVED")
        .order_by(ExceptionItemResult.amount_discrepancy.desc())
        .limit(limit)
        .all()
    )

    return {
        "settlements": [json.loads(s.raw_data_json) for s in settlements if s.raw_data_json],
        "pending_exceptions": [{
            "record_id": e.record_id,
            "reason_code": e.reason_code,
            "explanation": e.explanation
        } for e in exceptions],
        "_meta": _tool_meta("get_settlement_status_tool", thread_id, limit=limit)
    }


# ─────────────────────────────────────────────────────────────
# Deterministic keyword record search (adopted from rag-document-qa's
# IDF-weighted relevance + refusal gate, dependency-free, no embeddings).
# ─────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def search_records_tool(db: Session, thread_id: str, query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Search thread-wide document records by free text, returning cited results.

    Uses inverse-document-frequency (IDF) weighted term overlap over the record's
    description/entity/reference/source fields — a cheap, deterministic, local
    alternative to embeddings. When no query term matches, it refuses (returns
    NO_MATCH) rather than guessing: identical to rag-document-qa's IDF-weighted
    refusal gate that catches "fluent-but-wrong" lookups.
    """
    if not thread_id or not (query or "").strip():
        return {"status": "NO_QUERY", "message": "Provide a search term or phrase.", "results": []}

    records = db.query(DocumentRecord).filter(DocumentRecord.thread_id == thread_id).all()
    if not records:
        return {"status": "NO_DATA", "message": "No records exist in this thread to search.", "results": []}

    qterms = _tokenize(query)
    if not qterms:
        return {"status": "NO_QUERY", "message": "Provide a search term or phrase.", "results": []}

    def _fields(r: DocumentRecord) -> str:
        return " ".join(filter(None, [r.description, r.clean_entity, r.entity, r.source, r.record_id, r.reference_id]))

    field_tokens = [set(_tokenize(_fields(r))) for r in records]
    N = len(records)
    df: Dict[str, int] = {}
    for toks in field_tokens:
        for t in toks:
            df[t] = df.get(t, 0) + 1

    def _idf(t: str) -> float:
        return math.log((N + 1) / (df.get(t, 0) + 1)) + 1.0

    scored: List[tuple] = []
    for r, toks in zip(records, field_tokens):
        matched = [t for t in qterms if t in toks]
        if not matched:
            continue
        score = sum(_idf(t) for t in matched)
        scored.append((score, len(matched), r, matched))

    if not scored:
        return {
            "status": "NO_MATCH",
            "message": "I could not find any records matching that search in this thread.",
            "query": query,
            "results": [],
        }

    scored.sort(key=lambda x: (-x[0], -x[1], x[2].record_id))
    limit = _sanitize_limit(limit, default=10)
    results = []
    for score, nmatch, r, matched in scored[:limit]:
        results.append({
            "record_id": r.record_id,
            "source": r.source,
            "amount": r.amount,
            "date": r.iso_date,
            "entity": r.entity,
            "description": r.description,
            "reference_id": r.reference_id,
            "relevance_score": round(score, 4),
            "matched_terms": sorted(set(matched)),
        })

    return {
        "status": "OK",
        "query": query,
        "result_count": len(results),
        "results": results,
        "_meta": _tool_meta("search_records_tool", thread_id, query=query[:120]),
    }
