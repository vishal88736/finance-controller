"""
FastAPI Server for AI Finance Controller.
Provides endpoints for:
- File Upload & Synthetic Batch Ingestion
- LangGraph Reconciliation Execution
- Matches, Exceptions, & Ground-Truth Metrics Retrieval
- Context-Aware QA Copilot Chat
"""

import os
import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from ..database.db import get_db, init_db
from ..database.models import (
    ReconciliationRun,
    FileMetadata,
    MatchResult,
    ExceptionResult,
    EvaluationMetric,
    ChatHistory
)
from ..synthetic.generator import generate_synthetic_dataset
from ..agents.reconciliation_graph import reconciliation_graph
from ..agents.qa_graph import qa_graph
from ..agents.orchestrator import orchestrator
from ..reconciliation.models import ReconciliationMatch, ReconciliationException

app = FastAPI(
    title="AI Finance Controller API",
    description="Agentic finance operations platform for multi-source reconciliation, exception management, and evaluation.",
    version="1.0.0"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()
    # Generate initial synthetic data if not present
    synth_dir = os.path.join(os.path.dirname(__file__), "..", "synthetic")
    gt_file = os.path.join(synth_dir, "ground_truth.json")
    if not os.path.exists(gt_file):
        generate_synthetic_dataset(synth_dir, total_records=200)

# Request / Response Schemas
class RunReconciliationRequest(BaseModel):
    user_prompt: Optional[str] = "Reconcile these financial records and identify anything that doesn't match."
    use_synthetic_batch: bool = True
    file_ids: Optional[List[str]] = None

class ChatRequest(BaseModel):
    question: str
    run_id: Optional[str] = None

# ----------------- API ROUTES ----------------- #

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "AI Finance Controller API", "version": "1.0.0"}

@app.post("/api/synthetic/generate")
def generate_synthetic():
    synth_dir = os.path.join(os.path.dirname(__file__), "..", "synthetic")
    result = generate_synthetic_dataset(synth_dir, total_records=200)
    return {
        "status": "success",
        "message": "Generated 200+ multi-source records and ground truth",
        "data": result
    }

@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    saved_files = []
    upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    for f in files:
        file_id = f"FILE-{uuid.uuid4().hex[:8].upper()}"
        file_path = os.path.join(upload_dir, f"{file_id}_{f.filename}")
        content = await f.read()
        with open(file_path, "wb") as out:
            out.write(content)

        saved_files.append({
            "file_id": file_id,
            "filename": f.filename,
            "path": file_path,
            "size_bytes": len(content),
            "source_label": os.path.splitext(f.filename)[0]
        })

    return {
        "status": "success",
        "uploaded_count": len(saved_files),
        "files": saved_files
    }

@app.post("/api/reconciliation/run")
def run_reconciliation_endpoint(
    req: RunReconciliationRequest,
    db: Session = Depends(get_db)
):
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
    synth_dir = os.path.join(os.path.dirname(__file__), "..", "synthetic")
    
    uploaded_files_data = []
    if req.use_synthetic_batch:
        fa = os.path.join(synth_dir, "source_a_ledger.csv")
        fb = os.path.join(synth_dir, "source_b_bank.csv")
        fc = os.path.join(synth_dir, "source_c_payouts.xlsx")
        
        if not os.path.exists(fa):
            generate_synthetic_dataset(synth_dir, total_records=200)

        uploaded_files_data = [
            {"path": fa, "filename": "source_a_ledger.csv", "source_label": "source_a_ledger"},
            {"path": fb, "filename": "source_b_bank.csv", "source_label": "source_b_bank"}
        ]
        if os.path.exists(fc):
            uploaded_files_data.append(
                {"path": fc, "filename": "source_c_payouts.xlsx", "source_label": "source_c_payouts"}
            )

    # Initial State for LangGraph
    initial_state = {
        "run_id": run_id,
        "user_request": req.user_prompt or "Reconcile these financial records.",
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
        "error": None
    }

    # Execute LangGraph StateGraph
    output_state = reconciliation_graph.invoke(initial_state)

    final_report = output_state.get("final_report", {})
    metrics = output_state.get("metrics", {})
    matches_list = output_state.get("matches", [])
    exceptions_list = output_state.get("exceptions", [])

    try:
        # Persist in SQLite
        run_record = ReconciliationRun(
            id=run_id,
            user_prompt=req.user_prompt,
            status="COMPLETED",
            file_count=len(uploaded_files_data),
            total_records=final_report.get("total_records", 0),
            matched_records=final_report.get("matched_count", 0),
            unmatched_records=final_report.get("exceptions_count", 0),
            exception_records=final_report.get("exceptions_count", 0),
            match_rate=final_report.get("match_rate", 0.0),
            accuracy=final_report.get("accuracy", 0.0),
            precision_rate=final_report.get("precision", 0.0),
            recall_rate=final_report.get("recall", 0.0),
            processing_time_sec=final_report.get("processing_time_sec", 0.0),
            throughput_rec_sec=final_report.get("throughput_records_sec", 0.0),
            summary_text=json.dumps(final_report)
        )
        db.add(run_record)

        # Persist File Metadata
        for f in uploaded_files_data:
            fm = FileMetadata(
                id=f"FILE-{uuid.uuid4().hex[:8].upper()}",
                run_id=run_id,
                filename=f["filename"],
                file_type=os.path.splitext(f["filename"])[1].replace(".", ""),
                file_size_bytes=os.path.getsize(f["path"]) if os.path.exists(f["path"]) else 0,
                record_count=final_report.get("total_records", 0) // len(uploaded_files_data),
                source_label=f["source_label"]
            )
            db.add(fm)

        # Persist Matches
        for m in matches_list:
            mr = MatchResult(
                id=m.get("match_id", f"MATCH-{uuid.uuid4().hex[:8].upper()}"),
                run_id=run_id,
                record_id_a=m["record_id_a"],
                record_id_b=m["record_id_b"],
                source_a=m["source_a"],
                source_b=m["source_b"],
                amount_a=m["amount_a"],
                amount_b=m["amount_b"],
                date_a=m.get("date_a"),
                date_b=m.get("date_b"),
                entity_a=m.get("entity_a"),
                entity_b=m.get("entity_b"),
                confidence_score=m["confidence_score"],
                match_category=m.get("match_category", "EXACT_MATCH"),
                status=m.get("status", "MATCHED"),
                score_breakdown_json=json.dumps(m.get("score_breakdown", {}))
            )
            db.add(mr)

        # Persist Exceptions
        for e in exceptions_list:
            er = ExceptionResult(
                id=e.get("exception_id", f"EXC-{uuid.uuid4().hex[:8].upper()}"),
                run_id=run_id,
                record_id=e["record_id"],
                source=e["source"],
                amount=e.get("amount"),
                entity=e.get("entity"),
                date=e.get("date"),
                reason_code=e["reason_code"],
                confidence=e.get("confidence", 0.0),
                decision=e.get("decision", "UNRESOLVED"),
                explanation=e["explanation"],
                candidates_json=json.dumps(e.get("candidates", [])),
                amount_discrepancy=e.get("amount_discrepancy", 0.0)
            )
            db.add(er)

        # Persist Metrics
        em = EvaluationMetric(
            id=f"METRIC-{uuid.uuid4().hex[:8].upper()}",
            run_id=run_id,
            total_ground_truth_cases=metrics.get("total_ground_truth_cases", 0),
            true_positives=metrics.get("true_positives", 0),
            false_positives=metrics.get("false_positives", 0),
            false_negatives=metrics.get("false_negatives", 0),
            true_negatives=metrics.get("true_negatives", 0),
            precision=metrics.get("precision", 0.0),
            recall=metrics.get("recall", 0.0),
            f1_score=metrics.get("f1_score", 0.0),
            accuracy=metrics.get("accuracy", 0.0),
            match_rate=metrics.get("match_rate", 0.0),
            processing_time_sec=metrics.get("processing_time_sec", 0.0),
            throughput_records_per_sec=metrics.get("throughput_records_sec", 0.0),
            confusion_matrix_json=json.dumps(metrics.get("detailed_metrics_json", {}))
        )
        db.add(em)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning: Database persist error: {e}")

    return {
        "status": "success",
        "run_id": run_id,
        "summary": final_report,
        "step_progress": output_state.get("step_progress", [])
    }

@app.get("/api/runs")
def get_all_runs(db: Session = Depends(get_db)):
    try:
        runs = db.query(ReconciliationRun).order_by(ReconciliationRun.created_at.desc()).all()
        return [{
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "status": r.status,
            "user_prompt": r.user_prompt,
            "total_records": r.total_records,
            "matched_records": r.matched_records,
            "exception_records": r.exception_records,
            "match_rate": r.match_rate,
            "accuracy": r.accuracy,
            "throughput_rec_sec": r.throughput_rec_sec,
            "processing_time_sec": r.processing_time_sec
        } for r in runs]
    except Exception as e:
        return []

@app.get("/api/reconciliation/{run_id}")
def get_run_details(run_id: str, db: Session = Depends(get_db)):
    run = db.query(ReconciliationRun).filter(ReconciliationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    files = db.query(FileMetadata).filter(FileMetadata.run_id == run_id).all()
    
    return {
        "run_id": run.id,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "user_prompt": run.user_prompt,
        "summary": {
            "total_records": run.total_records,
            "matched_records": run.matched_records,
            "unmatched_records": run.unmatched_records,
            "exception_records": run.exception_records,
            "match_rate": run.match_rate,
            "accuracy": run.accuracy,
            "precision": run.precision_rate,
            "recall": run.recall_rate,
            "processing_time_sec": run.processing_time_sec,
            "throughput_records_sec": run.throughput_rec_sec
        },
        "files": [{
            "filename": f.filename,
            "file_type": f.file_type,
            "record_count": f.record_count,
            "source_label": f.source_label
        } for f in files]
    }

@app.get("/api/reconciliation/{run_id}/matches")
def get_run_matches(
    run_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 250,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(MatchResult).filter(MatchResult.run_id == run_id)
    if category and category != "ALL":
        query = query.filter(MatchResult.match_category == category)
    if search:
        s = f"%{search}%"
        query = query.filter(
            (MatchResult.record_id_a.like(s)) |
            (MatchResult.record_id_b.like(s)) |
            (MatchResult.entity_a.like(s)) |
            (MatchResult.entity_b.like(s))
        )
    
    total = query.count()
    matches = query.offset(offset).limit(limit).all()

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
            "score_breakdown": json.loads(m.score_breakdown_json) if m.score_breakdown_json else {}
        } for m in matches]
    }

@app.get("/api/reconciliation/{run_id}/exceptions")
def get_run_exceptions(
    run_id: str,
    reason: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(ExceptionResult).filter(ExceptionResult.run_id == run_id)
    if reason and reason != "ALL":
        query = query.filter(ExceptionResult.reason_code == reason)
    if search:
        s = f"%{search}%"
        query = query.filter(
            (ExceptionResult.record_id.like(s)) |
            (ExceptionResult.entity.like(s)) |
            (ExceptionResult.explanation.like(s))
        )
    
    total = query.count()
    exceptions = query.offset(offset).limit(limit).all()

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
            "confidence": e.confidence,
            "decision": e.decision,
            "explanation": e.explanation,
            "amount_discrepancy": e.amount_discrepancy,
            "candidates": json.loads(e.candidates_json) if e.candidates_json else []
        } for e in exceptions]
    }

@app.get("/api/reconciliation/{run_id}/metrics")
def get_run_metrics(run_id: str, db: Session = Depends(get_db)):
    metric = db.query(EvaluationMetric).filter(EvaluationMetric.run_id == run_id).first()
    if not metric:
        raise HTTPException(status_code=404, detail="Metrics not found")
    
    return {
        "run_id": run_id,
        "total_ground_truth_cases": metric.total_ground_truth_cases,
        "true_positives": metric.true_positives,
        "false_positives": metric.false_positives,
        "false_negatives": metric.false_negatives,
        "true_negatives": metric.true_negatives,
        "precision": metric.precision,
        "recall": metric.recall,
        "f1_score": metric.f1_score,
        "accuracy": metric.accuracy,
        "match_rate": metric.match_rate,
        "processing_time_sec": metric.processing_time_sec,
        "throughput_records_sec": metric.throughput_records_per_sec,
        "confusion_matrix": json.loads(metric.confusion_matrix_json) if metric.confusion_matrix_json else {}
    }

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    try:
        user_msg_id = f"MSG-{uuid.uuid4().hex[:8].upper()}"
        user_msg = ChatHistory(
            id=user_msg_id,
            run_id=req.run_id,
            role="user",
            content=req.question
        )
        db.add(user_msg)
        db.commit()
    except Exception:
        db.rollback()

    qa_input = {
        "run_id": req.run_id,
        "question": req.question,
        "query_type": "GENERAL",
        "extracted_entities": [],
        "extracted_record_ids": [],
        "retrieved_records": [],
        "retrieved_exceptions": [],
        "retrieved_metrics": {},
        "answer": ""
    }
    qa_output = qa_graph.invoke(qa_input)
    answer = qa_output.get("answer", "No relevant data retrieved.")

    try:
        asst_msg_id = f"MSG-{uuid.uuid4().hex[:8].upper()}"
        asst_msg = ChatHistory(
            id=asst_msg_id,
            run_id=req.run_id,
            role="assistant",
            content=answer,
            retrieved_data_json=json.dumps({
                "records": qa_output.get("retrieved_records", []),
                "exceptions": qa_output.get("retrieved_exceptions", []),
                "metrics": qa_output.get("retrieved_metrics", {})
            })
        )
        db.add(asst_msg)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "answer": answer,
        "query_type": qa_output.get("query_type"),
        "retrieved_records": qa_output.get("retrieved_records", []),
        "retrieved_exceptions": qa_output.get("retrieved_exceptions", []),
        "retrieved_metrics": qa_output.get("retrieved_metrics", {})
    }
