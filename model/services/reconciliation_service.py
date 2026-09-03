"""
Canonical Reconciliation Service.

Single deterministic execution path used by BOTH:
    - POST /api/threads/{thread_id}/reconcile   (REST)
    - chat messages with reconciliation intent   (Copilot)

Contract:
    thread_id
        → documents registered in THAT thread (never another thread's)
        → stored files on disk
        → parse/normalize (LangGraph reconciliation graph)
        → deterministic ReconciliationEngine
        → persist ProcessingRun, matches, exceptions, evidence, audit events
        → assistant message with the honest summary

It NEVER loads the synthetic benchmark dataset implicitly. Demo data is used
only when the caller explicitly sets demo=True (explicit demo mechanism).

Benchmark evaluation is performed only when explicitly requested AND the
bundled benchmark batch is used — regular user runs are recorded with
evaluated=false and null precision/recall/f1.
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..reconciliation.pandas_reconciler import clean_for_json

from ..database.models import (
    Document,
    ProcessingRun,
    ReconciliationResult,
    ExceptionItemResult,
)
from ..database.repositories import (
    get_thread_documents,
    get_thread,
    log_audit,
    add_message,
)
from ..agents.guardrails import guardrails
from ..graph.reconciliation_graph import reconciliation_graph
from ..observability.langsmith import get_langsmith_config, traced_operation

# Directory of the bundled benchmark batch (explicit demo use only)
_SYNTH_DIR = os.path.join(os.path.dirname(__file__), "..", "synthetic")


class ReconciliationError(Exception):
    """Raised when a reconciliation run cannot be completed."""


def _thread_document_files(db: Session, thread_id: str) -> List[Dict[str, Any]]:
    """Collect uploaded files belonging to this thread (existence-checked)."""
    files: List[Dict[str, Any]] = []
    docs = get_thread_documents(db, thread_id)
    for d in docs:
        if d.file_path and os.path.exists(d.file_path):
            files.append({
                "path": d.file_path,
                "filename": d.filename,
                "source_label": os.path.splitext(d.filename)[0],
                "document_id": d.id,
            })
        else:
            log_audit(
                db=db,
                thread_id=thread_id,
                action="DOCUMENT_FILE_MISSING",
                agent="Reconciliation_Agent",
                details={"document_id": d.id, "filename": d.filename},
            )
    return files


def _demo_batch_files(db: Session) -> List[Dict[str, Any]]:
    """
    Explicit demo mechanism: build the file list from the bundled benchmark
    dataset. Called ONLY when demo=True. Generates the dataset if missing.
    """
    from ..synthetic.generator import generate_synthetic_dataset

    fa = os.path.join(_SYNTH_DIR, "source_a_ledger.csv")
    fb = os.path.join(_SYNTH_DIR, "source_b_bank.csv")
    if not os.path.exists(fa):
        generate_synthetic_dataset(_SYNTH_DIR, total_records=200)

    files = [
        {"path": fa, "filename": "source_a_ledger.csv", "source_label": "source_a_ledger"},
        {"path": fb, "filename": "source_b_bank.csv", "source_label": "source_b_bank"},
    ]
    log_audit(
        db=db,
        thread_id="",
        action="DEMO_BATCH_LOADED",
        agent="Reconciliation_Agent",
        details={"files": [f["filename"] for f in files]},
    )
    return files


def run_reconciliation(
    db: Session,
    thread_id: str,
    user_prompt: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    demo: bool = False,
    run_id: Optional[str] = None,
    add_thread_message: bool = True,
) -> Dict[str, Any]:
    """
    Execute reconciliation for a thread over its own documents.

    Args:
        db:            request-scoped DB session (never a fresh SessionLocal)
        thread_id:     target thread (must exist)
        user_prompt:   natural-language request recorded on the run
        document_ids:  optional subset of thread document ids to reconcile
        demo:          EXPLICIT demo mode — use bundled benchmark batch and
                       evaluate against its ground truth
        run_id:        optional caller-provided run id
        add_thread_message: whether to append the assistant summary message

    Returns a dict with run_id, summary, step_progress, document_ids.
    Raises ReconciliationError on invalid thread / no usable documents.
    """
    thread = get_thread(db, thread_id)
    if not thread:
        raise ReconciliationError(f"Thread '{thread_id}' not found.")

    run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"

    log_audit(
        db=db,
        thread_id=thread_id,
        run_id=run_id,
        action="RECONCILIATION_STARTED",
        agent="Reconciliation_Agent",
        parameters={"user_prompt": (user_prompt or "")[:200], "demo": demo},
        result_summary="Reconciliation run started",
    )

    # ── Source files: thread documents, or explicit demo batch ──
    if demo:
        uploaded_files_data = _demo_batch_files(db)
        doc_ids = [f.get("document_id") for f in uploaded_files_data if f.get("document_id")]
        ground_truth: Optional[Any] = os.path.join(_SYNTH_DIR, "ground_truth.json")
        source_mode = "DEMO_BATCH"
    else:
        uploaded_files_data = _thread_document_files(db, thread_id)
        if document_ids is not None:
            wanted = set(document_ids)
            uploaded_files_data = [f for f in uploaded_files_data if f.get("document_id") in wanted]
            source_mode = "THREAD_DOCUMENTS_SUBSET"
        else:
            source_mode = "THREAD_DOCUMENTS"
        doc_ids = [f.get("document_id") for f in uploaded_files_data if f.get("document_id")]
        # User-document runs are never evaluated against the bundled benchmark.
        ground_truth = None

    if not uploaded_files_data:
        raise ReconciliationError(
            "No documents are available in this thread. Upload documents before running reconciliation."
        )

    # ── LangGraph state ──
    initial_state = {
        "thread_id": thread_id,
        "run_id": run_id,
        "user_request": user_prompt or "Reconcile these financial records.",
        "uploaded_files": uploaded_files_data,
        "documents": [],
        "normalized_records": [],
        "candidates": [],
        "matches": [],
        "exceptions": [],
        "metrics": {},
        "final_report": {},
        "current_step": "init",
        "step_progress": [],
        "error": None,
        "ground_truth": ground_truth,
    }

    config = get_langsmith_config(
        thread_id=thread_id,
        run_id=run_id,
        agent_name="Reconciliation_Agent",
        operation="reconcile",
        document_ids=doc_ids,
    )

    t0 = time.perf_counter()
    with traced_operation(
        f"reconcile:{source_mode}", thread_id=thread_id, run_id=run_id,
        operation="reconciliation", document_ids=doc_ids,
    ):
        output_state = reconciliation_graph.invoke(initial_state, config=config)
    elapsed = time.perf_counter() - t0

    final_report = output_state.get("final_report", {})
    matches_list = output_state.get("matches", [])
    exceptions_list = output_state.get("exceptions", [])
    step_progress = output_state.get("step_progress", [])

    # ── Persist run + matches + exceptions (same transaction) ──
    evaluated = bool(final_report.get("evaluated", False))
    try:
        run_record = ProcessingRun(
            id=run_id,
            thread_id=thread_id,
            user_prompt=user_prompt,
            status="COMPLETED",
            file_count=len(uploaded_files_data),
            total_records=final_report.get("total_records", 0),
            matched_count=final_report.get("matched_count", 0),
            unmatched_count=final_report.get("exceptions_count", 0),
            exceptions_count=final_report.get("exceptions_count", 0),
            match_rate=final_report.get("match_rate", 0.0),
            accuracy=final_report.get("accuracy") if evaluated else None,
            precision_rate=final_report.get("precision") if evaluated else None,
            recall_rate=final_report.get("recall") if evaluated else None,
            f1_score=final_report.get("f1_score") if evaluated else None,
            processing_time_sec=final_report.get("processing_time_sec", 0.0),
            throughput_rec_sec=final_report.get("throughput_records_sec", 0.0),
            total_amount_processed=final_report.get("total_amount_processed", 0.0),
            total_amount_matched=final_report.get("total_amount_matched", 0.0),
            total_amount_discrepancy=final_report.get("total_amount_discrepancy", 0.0),
            summary_json=json.dumps(clean_for_json(final_report)),
        )
        db.add(run_record)

        for m in matches_list:
            mr = ReconciliationResult(
                id=m.get("match_id", m.get("id", f"match_{uuid.uuid4().hex[:12]}")),
                thread_id=thread_id,
                run_id=run_id,
                record_id_a=m["record_id_a"],
                record_id_b=m["record_id_b"],
                source_a=m["source_a"],
                source_b=m["source_b"],
                amount_a=m["amount_a"],
                amount_b=m["amount_b"],
                date_a=m.get("date_a"),
                date_b=m.get("date_b"),
                entity_a=m.get("entity_a") or "Unknown",
                entity_b=m.get("entity_b") or "Unknown",
                confidence_score=m["confidence_score"],
                match_category=m.get("match_category", "EXACT_MATCH"),
                status=m.get("status", "MATCHED"),
                evidence_json=json.dumps(clean_for_json({
                    **m.get("evidence", {}),
                    "provenance_a": m.get("provenance_a", {}),
                    "provenance_b": m.get("provenance_b", {}),
                    "member_id_a": m.get("member_id_a"),
                    "member_id_b": m.get("member_id_b"),
                    "counterpart_document_id": m.get("counterpart_document_id"),
                    "counterpart_row_index": m.get("counterpart_row_index"),
                })),
                score_breakdown_json=json.dumps(clean_for_json(m.get("score_breakdown", m.get("provenance_a", {})))),
            )
            db.add(mr)

        for e in exceptions_list:
            er = ExceptionItemResult(
                id=e.get("exception_id", e.get("id", f"exc_{uuid.uuid4().hex[:12]}")),
                thread_id=thread_id,
                run_id=run_id,
                record_id=e["record_id"],
                source=e["source"],
                amount=e.get("amount", e.get("amount_discrepancy", 0.0)),
                entity=e.get("entity", "Unknown"),
                date=e.get("date"),
                reason_code=e["reason_code"],
                discrepancy_category=e.get("discrepancy_category", e.get("discrepancy_level", "MATERIAL")),
                confidence=e.get("confidence", 0.0),
                decision=e.get("decision", "UNRESOLVED"),
                explanation=e["explanation"],
                amount_discrepancy=e.get("amount_discrepancy", 0.0),
                candidates_json=json.dumps(clean_for_json(e.get("candidates", []))),
                evidence_json=json.dumps(clean_for_json(e.get("evidence", {}))),
            )
            db.add(er)

        db.commit()
    except Exception as e:
        db.rollback()
        log_audit(
            db=db,
            thread_id=thread_id,
            run_id=run_id,
            action="ERROR",
            agent="Reconciliation_Agent",
            result_summary=f"Database persist error: {type(e).__name__}",
        )
        raise ReconciliationError(f"Failed to persist reconciliation results: {e}") from e

    # ── Audit events for pipeline transparency ──
    schemas = final_report.get("detected_schemas", {})
    if schemas:
        log_audit(
            db=db,
            thread_id=thread_id,
            run_id=run_id,
            action="SCHEMA_DETECTED",
            agent="Reconciliation_Agent",
            parameters={"schemas": schemas},
            result_summary=f"Inspected schemas for {len(schemas)} document(s)",
        )

    mappings = final_report.get("mapped_columns", {})
    if mappings:
        log_audit(
            db=db,
            thread_id=thread_id,
            run_id=run_id,
            action="COLUMNS_MAPPED",
            agent="Reconciliation_Agent",
            parameters={"mapped_columns": mappings},
            result_summary=f"Mapped semantic columns across {len(mappings)} document(s)",
        )

    log_audit(
        db=db,
        thread_id=thread_id,
        run_id=run_id,
        action="PYTHON_RECONCILIATION_COMPLETED",
        agent="Reconciliation_Agent",
        parameters={
            "records_processed": final_report.get("total_records", 0),
            "matched_count": final_report.get("matched_count", 0),
            "exceptions_count": final_report.get("exceptions_count", 0),
        },
        result_summary=f"Deterministic Pandas engine matched {final_report.get('matched_count', 0)} pairs ({final_report.get('match_rate', 0.0):.1f}%)",
    )

    log_audit(
        db=db,
        thread_id=thread_id,
        run_id=run_id,
        action="RECONCILIATION_COMPLETED",
        agent="Reconciliation_Agent",
        parameters={"total_records": final_report.get("total_records")},
        result_summary=(
            f"Processed {final_report.get('total_records', 0)} records from "
            f"{len(uploaded_files_data)} documents: "
            f"{len(matches_list)} matched pairs, {len(exceptions_list)} exceptions"
        ),
    )

    # ── Assistant summary message (honest — evaluated only when evaluation ran) ──
    if add_thread_message:
        lines = [
            "✅ **Reconciliation Completed**",
            "",
            f"- **Documents**: {len(uploaded_files_data)}",
            f"- **Records Processed**: {final_report.get('total_records', 0):,}",
            f"- **Reconciled Pairs**: {final_report.get('matched_count', 0):,} ({final_report.get('match_rate', 0):.1f}%)",
            f"- **Exceptions**: {final_report.get('exceptions_count', 0):,}",
        ]
        if evaluated:
            lines.append(
                f"- **Benchmark Evaluation**: accuracy {final_report.get('accuracy', 0):.1f}%, "
                f"precision {final_report.get('precision', 0):.1f}%, recall {final_report.get('recall', 0):.1f}%"
            )
        else:
            lines.append("- **Evaluation**: not available (no authorized ground truth associated with this run)")
        lines.append(
            f"- **Throughput**: {final_report.get('throughput_records_sec', 0):.0f} rec/s "
            f"in {final_report.get('processing_time_sec', 0):.2f}s"
        )
        add_message(
            db=db,
            thread_id=thread_id,
            role="assistant",
            content=guardrails.validate_output("\n".join(lines)),
            metadata={"run_id": run_id, "summary": final_report, "event": "reconciliation_completed"},
        )

    return {
        "status": "success",
        "run_id": run_id,
        "thread_id": thread_id,
        "source_mode": source_mode,
        "document_ids": doc_ids,
        "summary": final_report,
        "step_progress": step_progress,
    }
