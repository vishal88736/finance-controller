"""
LangGraph state definitions for Reconciliation and QA agents.
"""

from typing import List, Dict, Any, Optional, TypedDict

class ReconciliationState(TypedDict):
    run_id: str
    user_request: str
    uploaded_files: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]
    normalized_records: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    matches: List[Dict[str, Any]]
    exceptions: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    final_report: Dict[str, Any]
    current_step: str
    step_progress: List[str]
    error: Optional[str]

class QAState(TypedDict):
    run_id: Optional[str]
    question: str
    query_type: str  # SPECIFIC_RECORD, METRIC_QUERY, DISCREPANCY_QUERY, SUMMARY_QUERY, GENERAL
    extracted_entities: List[str]
    extracted_record_ids: List[str]
    retrieved_records: List[Dict[str, Any]]
    retrieved_exceptions: List[Dict[str, Any]]
    retrieved_metrics: Dict[str, Any]
    answer: str
