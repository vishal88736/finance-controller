"""
Data models for Reconciliation Engine with evidence-first design.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from ..ingestion.normalizer import NormalizedRecord


class CandidateMatch(BaseModel):
    target_record_id: str
    target_source: str
    target_amount: float
    target_date: Optional[str] = None
    target_entity: Optional[str] = None
    confidence_score: float
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    match_category: str  # EXACT_MATCH, FUZZY_MATCH, DATE_LAG, AMOUNT_MISMATCH, PARTIAL_MATCH
    amount_diff: float = 0.0
    date_diff_days: int = 0
    checks: Dict[str, bool] = Field(default_factory=dict)
    notes: Optional[str] = None


class ReconciliationMatch(BaseModel):
    match_id: str
    record_id_a: str
    record_id_b: str
    source_a: str
    source_b: str
    amount_a: float
    amount_b: float
    date_a: Optional[str] = None
    date_b: Optional[str] = None
    entity_a: Optional[str] = None
    entity_b: Optional[str] = None
    confidence_score: float
    match_category: str
    status: str = "MATCHED"
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    checks: Dict[str, bool] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    explanation: Optional[str] = None


class ReconciliationException(BaseModel):
    exception_id: str
    record_id: str
    source: str
    amount: Optional[float] = None
    entity: Optional[str] = None
    date: Optional[str] = None
    reason_code: str  # AMOUNT_MISMATCH, AMBIGUOUS_CANDIDATES, MISSING_COUNTERPART, DUPLICATE, etc.
    discrepancy_category: str = "MATERIAL"  # NORMAL vs MATERIAL
    confidence: float = 0.0
    decision: str = "UNRESOLVED"
    explanation: str
    amount_discrepancy: float = 0.0
    candidates: List[CandidateMatch] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationSummary(BaseModel):
    total_records_processed: int
    matched_count: int
    unmatched_count: int
    unresolved_exceptions_count: int
    match_rate: float
    total_amount_processed: float
    total_amount_matched: float
    total_amount_discrepancy: float
    processing_time_sec: float
    throughput_records_sec: float
