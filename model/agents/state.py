"""
LangGraph state definitions for Reconciliation and QA agents.
Scoped with thread_id and evidence structures.
"""

from typing import List, Dict, Any, Optional, TypedDict


class ReconciliationState(TypedDict):
    thread_id: str
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
    db_session: Optional[Any]
    ground_truth: Optional[Any]  # explicit, authorized ground truth (dict or path) for benchmark runs only
    document_tables: Optional[List[Any]]
    schema_result: Optional[Any]
    recon_output: Optional[Any]


class QAState(TypedDict):
    thread_id: str
    run_id: Optional[str]
    question: str
    guardrail_passed: bool
    guardrail_refusal: Optional[str]
    guardrail_layer: Optional[str]
    query_type: str  # SPECIFIC_RECORD, METRIC_QUERY, DISCREPANCY_QUERY, EXCEPTION_QUERY, MATERIAL_EXCEPTIONS, SUMMARY_QUERY, DOCUMENT_QUERY, AMBIGUOUS_QUERY, GENERAL, OFF_TOPIC
    extracted_entities: List[str]
    extracted_record_ids: List[str]
    retrieved_records: List[Dict[str, Any]]
    retrieved_exceptions: List[Dict[str, Any]]
    retrieved_metrics: Dict[str, Any]
    retrieved_documents: List[Dict[str, Any]]
    evidence: Dict[str, Any]
    tools_called: List[str]
    answer: str
    answer_source: str  # "deterministic" | "llm_validated" | "refusal"
    db_session: Optional[Any]
