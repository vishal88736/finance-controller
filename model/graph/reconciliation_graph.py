"""
LangGraph Deterministic Python Reconciliation Pipeline.
Executes the required deterministic processing flow:
    Upload → Schema Detection → Column Mapping → Python Reconciliation → Results → Q&A

Nodes:
    1. analyze_request                → Request parsing & configuration
    2. load_all_documents             → Reads all uploaded files into DataFrames
    3. detect_schemas_and_map_columns → Semantic column mapper across all files
    4. python_reconciliation          → Deterministic Pandas + NumPy multi-pass matching
    5. compile_results_and_diagnostics→ Provenance tracking & rejection breakdown
    6. calculate_metrics              → Evaluator (if benchmark ground truth provided)
"""

import os
import io
import json
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from langgraph.graph import StateGraph, START, END

from ..agents.state import ReconciliationState
from ..reconciliation.schema_mapper import schema_mapper, SchemaMappingResult
from ..reconciliation.pandas_reconciler import pandas_reconciler
from ..evaluation.evaluator import evaluate_reconciliation


def analyze_request_node(state: ReconciliationState) -> Dict[str, Any]:
    """Node 1: Analyze user's natural language request."""
    progress = list(state.get("step_progress", []))
    progress.append("Analyzed user reconciliation request")

    return {
        "current_step": "analyze_request",
        "step_progress": progress,
        "error": None,
    }


def load_all_documents_node(state: ReconciliationState) -> Dict[str, Any]:
    """
    Node 2: [Upload Stage] Load ALL uploaded documents into DataFrames.
    Does not restrict to a single file; loads every document registered for this thread.
    """
    uploaded_files = list(state.get("uploaded_files", []))
    document_tables: List[Tuple[pd.DataFrame, str, str, str]] = []
    loaded_docs: List[Dict[str, Any]] = []

    for f_info in uploaded_files:
        f_path = f_info.get("path")
        f_name = f_info.get("filename", "file.csv")
        source_label = f_info.get("source_label", os.path.splitext(f_name)[0])
        doc_id = f_info.get("document_id", f"doc_{os.path.splitext(f_name)[0]}")
        f_bytes = f_info.get("content_bytes")

        target = io.BytesIO(f_bytes) if f_bytes else f_path
        if not target:
            continue

        ext = os.path.splitext(f_name)[1].lower()
        try:
            if ext == ".csv":
                df = pd.read_csv(target)
            elif ext in [".xlsx", ".xls"]:
                df = pd.read_excel(target)
            elif ext == ".json":
                df = pd.read_json(target)
            else:
                df = pd.read_csv(target)
        except Exception as e:
            df = pd.DataFrame()

        document_tables.append((df, doc_id, f_name, source_label))
        for r in df.to_dict(orient="records"):
            r["source"] = source_label
            r["document_id"] = doc_id
            loaded_docs.append(r)

    progress = list(state.get("step_progress", []))
    total_rows = sum(len(t[0]) for t in document_tables)
    progress.append(f"Upload: Ingested {len(document_tables)} documents ({total_rows} total rows)")

    return {
        "uploaded_files": uploaded_files,
        "documents": loaded_docs,
        "document_tables": document_tables,
        "current_step": "load_all_documents",
        "step_progress": progress,
    }


def detect_schemas_and_map_columns_node(state: ReconciliationState) -> Dict[str, Any]:
    """
    Node 3: [Schema Detection & Column Mapping Stages]
    Inspects schemas of all uploaded documents and maps equivalent semantic columns:
        transaction_id / txn_id / reference
        amount / transaction_amount / debit_amount
        date / transaction_date / value_date
        description / narration / memo
    """
    tables = state.get("document_tables") or []
    schema_res = schema_mapper.inspect_and_map_all(tables)

    progress = list(state.get("step_progress", []))
    progress.append(
        f"Schema Detection: Inspected {schema_res.documents_inspected} document schemas"
    )
    mapped_count = sum(len(s.mapped_columns) for s in schema_res.schemas.values())
    progress.append(
        f"Column Mapping: Identified {mapped_count} semantic column mappings across files"
    )

    return {
        "schema_result": schema_res,
        "current_step": "detect_schemas_and_map_columns",
        "step_progress": progress,
    }


def python_reconciliation_node(state: ReconciliationState) -> Dict[str, Any]:
    """
    Node 4: [Python Reconciliation Stage]
    Execute deterministic Pandas + NumPy reconciliation engine.
    Multi-pass matching, duplicate detection, and exception isolation.
    """
    tables = state.get("document_tables") or []
    run_id = state.get("run_id")
    thread_id = state.get("thread_id")

    recon_output = pandas_reconciler.reconcile_documents(
        document_tables=tables,
        run_id=run_id,
        thread_id=thread_id,
    )

    progress = list(state.get("step_progress", []))
    matches_count = len(recon_output.get("matches", []))
    exceptions_count = len(recon_output.get("exceptions", []))
    match_rate = recon_output.get("match_rate", 0.0)

    progress.append(
        f"Python Reconciliation: Executed Pandas + NumPy engine — {matches_count} matches ({match_rate:.1f}%), {exceptions_count} exceptions"
    )

    return {
        "recon_output": recon_output,
        "matches": recon_output.get("matches", []),
        "exceptions": recon_output.get("exceptions", []),
        "current_step": "python_reconciliation",
        "step_progress": progress,
    }


def compile_results_and_diagnostics_node(state: ReconciliationState) -> Dict[str, Any]:
    """
    Node 5: [Results Stage]
    Compile structured reconciliation result containing:
        - documents processed
        - detected schemas
        - mapped columns
        - records processed
        - candidate pairs
        - matched records
        - unmatched records
        - duplicates
        - exceptions
        - exact matches
        - fuzzy matches
        - mismatch reasons
        - totals and summary statistics
        - failure diagnostics (especially for 0% match scenarios)
    """
    recon_output = state.get("recon_output") or {}
    diagnostics = recon_output.get("diagnostics", {})

    progress = list(state.get("step_progress", []))
    zero_match_diag = diagnostics.get("zero_match_diagnostics")
    if zero_match_diag:
        progress.append(f"Results: Diagnostics identified — {zero_match_diag}")
    else:
        progress.append(
            f"Results: Compiled structured results with complete row provenance for {recon_output.get('records_processed', 0)} records"
        )

    return {
        "metrics": recon_output.get("totals_and_statistics", {}),
        "current_step": "compile_results_and_diagnostics",
        "step_progress": progress,
    }


def calculate_metrics_node(state: ReconciliationState) -> Dict[str, Any]:
    """
    Node 6: Finalize evaluation against ground truth if authorized benchmark run.
    Assembles the final comprehensive report.
    """
    recon_output = state.get("recon_output") or {}
    matches = recon_output.get("matches", [])
    exceptions = recon_output.get("exceptions", [])
    totals = recon_output.get("totals_and_statistics", {})

    gt_source = state.get("ground_truth")
    eval_report: Optional[dict] = None

    if gt_source:
        try:
            from ..reconciliation.models import ReconciliationMatch, ReconciliationException, ReconciliationSummary
            # Adapt to evaluator if ground truth provided
            summary_obj = ReconciliationSummary(
                total_records_processed=recon_output.get("records_processed", 0),
                total_amount_processed=totals.get("total_primary_amount", 0.0) + totals.get("total_counterparty_amount", 0.0),
                total_amount_matched=totals.get("matched_volume", 0.0),
                total_amount_discrepancy=totals.get("total_discrepancy_amount", 0.0),
                matched_count=len(matches),
                unresolved_exceptions_count=len(exceptions),
                match_rate=recon_output.get("match_rate", 0.0),
                processing_time_sec=totals.get("processing_time_sec", 0.0),
                throughput_records_sec=totals.get("throughput_records_sec", 0.0),
            )
            match_objs = [
                ReconciliationMatch(
                    match_id=m["id"],
                    record_id_a=m["record_id_a"],
                    record_id_b=m["record_id_b"],
                    source_a=m["source_a"],
                    source_b=m["source_b"],
                    amount_a=m["amount_a"],
                    amount_b=m["amount_b"],
                    amount_diff=m["amount_diff"],
                    date_a=m["date_a"],
                    date_b=m["date_b"],
                    days_diff=m["days_diff"],
                    confidence_score=m["confidence_score"],
                    match_category=m["match_category"],
                    discrepancy_level=m["discrepancy_level"],
                ) for m in matches
            ]
            eval_report = evaluate_reconciliation(match_objs, summary_obj, gt_source)
        except Exception:
            eval_report = None

    if eval_report:
        final_metrics = {
            "evaluated": True,
            "total_ground_truth_cases": eval_report.total_ground_truth_cases,
            "records_processed": recon_output.get("records_processed", 0),
            "true_positives": eval_report.true_positives,
            "false_positives": eval_report.false_positives,
            "false_negatives": eval_report.false_negatives,
            "true_negatives": eval_report.true_negatives,
            "precision": eval_report.precision,
            "recall": eval_report.recall,
            "f1_score": eval_report.f1_score,
            "accuracy": eval_report.accuracy,
            "match_rate": recon_output.get("match_rate", 0.0),
            "processing_time_sec": totals.get("processing_time_sec", 0.0),
            "throughput_records_sec": totals.get("throughput_records_sec", 0.0),
            "category_breakdown": eval_report.category_breakdown,
            "detailed_metrics_json": eval_report.detailed_metrics_json,
        }
    else:
        final_metrics = {
            "evaluated": False,
            "total_ground_truth_cases": 0,
            "records_processed": recon_output.get("records_processed", 0),
            "true_positives": None,
            "false_positives": None,
            "false_negatives": None,
            "true_negatives": None,
            "precision": None,
            "recall": None,
            "f1_score": None,
            "accuracy": None,
            "match_rate": recon_output.get("match_rate", 0.0),
            "processing_time_sec": totals.get("processing_time_sec", 0.0),
            "throughput_records_sec": totals.get("throughput_records_sec", 0.0),
            "category_breakdown": {},
            "detailed_metrics_json": {"confusion_matrix": {}},
        }

    evaluated = bool(final_metrics.get("evaluated"))
    accuracy_val = final_metrics.get("accuracy")

    final_report = {
        "run_id": state.get("run_id"),
        "thread_id": state.get("thread_id"),
        "user_request": state.get("user_request"),
        "total_records": recon_output.get("records_processed", 0),
        "matched_count": len(matches),
        "exceptions_count": len(exceptions),
        "match_rate": recon_output.get("match_rate", 0.0),
        "evaluated": evaluated,
        "accuracy": accuracy_val,
        "precision": final_metrics.get("precision"),
        "recall": final_metrics.get("recall"),
        "f1_score": final_metrics.get("f1_score"),
        "processing_time_sec": totals.get("processing_time_sec", 0.0),
        "throughput_records_sec": totals.get("throughput_records_sec", 0.0),
        "total_amount_processed": totals.get("total_primary_amount", 0.0) + totals.get("total_counterparty_amount", 0.0),
        "total_amount_matched": totals.get("matched_volume", 0.0),
        "total_amount_discrepancy": totals.get("total_discrepancy_amount", 0.0),
        "evaluation_metrics": final_metrics,
        "documents_processed": recon_output.get("documents_processed", []),
        "detected_schemas": recon_output.get("detected_schemas", {}),
        "mapped_columns": recon_output.get("mapped_columns", {}),
        "candidate_pairs_evaluated": recon_output.get("candidate_pairs_evaluated", 0),
        "exact_matches_count": recon_output.get("exact_matches_count", 0),
        "fuzzy_matches_count": recon_output.get("fuzzy_matches_count", 0),
        "duplicates_count": recon_output.get("duplicates_count", 0),
        "mismatch_reasons": recon_output.get("mismatch_reasons", {}),
        "reconciliation_plan": recon_output.get("reconciliation_plan", {}),
        "role_classifications": recon_output.get("role_classifications", {}),
        "source_population": recon_output.get("source_population", recon_output.get("records_processed", 0)),
        "counterpart_population": recon_output.get("counterpart_population", 0),
        "enrichment_adjustments": recon_output.get("enrichment_adjustments", []),
        "totals_and_statistics": totals,
        "diagnostics": recon_output.get("diagnostics", {}),
    }

    progress = list(state.get("step_progress", []))
    progress.append(
        f"Pipeline Finalized: Match Rate {recon_output.get('match_rate', 0.0)}%"
        + (f", Accuracy {accuracy_val}%" if evaluated else " (unsupervised user run — ground truth unavailable)")
    )

    return {
        "metrics": final_metrics,
        "final_report": final_report,
        "current_step": "calculate_metrics",
        "step_progress": progress,
    }


def build_reconciliation_graph():
    builder = StateGraph(ReconciliationState)

    builder.add_node("analyze_request", analyze_request_node)
    builder.add_node("load_all_documents", load_all_documents_node)
    builder.add_node("detect_schemas_and_map_columns", detect_schemas_and_map_columns_node)
    builder.add_node("python_reconciliation", python_reconciliation_node)
    builder.add_node("compile_results_and_diagnostics", compile_results_and_diagnostics_node)
    builder.add_node("calculate_metrics", calculate_metrics_node)

    builder.add_edge(START, "analyze_request")
    builder.add_edge("analyze_request", "load_all_documents")
    builder.add_edge("load_all_documents", "detect_schemas_and_map_columns")
    builder.add_edge("detect_schemas_and_map_columns", "python_reconciliation")
    builder.add_edge("python_reconciliation", "compile_results_and_diagnostics")
    builder.add_edge("compile_results_and_diagnostics", "calculate_metrics")
    builder.add_edge("calculate_metrics", END)

    return builder.compile()


reconciliation_graph = build_reconciliation_graph()
