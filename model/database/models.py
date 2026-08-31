"""
SQLAlchemy database models for AI Finance Controller.
Complete thread-based schema with:
- Thread
- Document (Registry)
- DocumentRecord
- ProcessingRun
- ReconciliationResult
- ExceptionItemResult
- AuditLog
- Message
"""

import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class Thread(Base):
    __tablename__ = "threads"

    id = Column(String, primary_key=True)  # e.g., thr_8f3a91...
    title = Column(String, nullable=False, default="New Conversation")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    documents = relationship("Document", back_populates="thread", cascade="all, delete-orphan", order_by="Document.uploaded_at.desc()")
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at.asc()")
    processing_runs = relationship("ProcessingRun", back_populates="thread", cascade="all, delete-orphan", order_by="ProcessingRun.created_at.desc()")
    reconciliation_results = relationship("ReconciliationResult", back_populates="thread", cascade="all, delete-orphan")
    exceptions = relationship("ExceptionItemResult", back_populates="thread", cascade="all, delete-orphan")


class Document(Base):
    """
    Document Registry entry. Every uploaded document gets a unique document_id,
    content SHA-256 hash for exact duplicate detection, and canonical dataset fingerprint.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True)  # e.g., doc_92ab31...
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # csv, xlsx, json, pdf
    content_hash_sha256 = Column(String, nullable=False, index=True)
    dataset_fingerprint = Column(String, nullable=True, index=True)  # Normalized canonical fingerprint
    size_bytes = Column(Integer, default=0)
    record_count = Column(Integer, default=0)
    document_type = Column(String, default="UNKNOWN")  # TRANSACTIONS, INVOICES, SETTLEMENTS, PAYMENTS
    processing_status = Column(String, default="PENDING")  # PENDING, PROCESSED, DUPLICATE, FAILED
    file_path = Column(String, nullable=True)
    metadata_json = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=utc_now)

    thread = relationship("Thread", back_populates="documents")
    records = relationship("DocumentRecord", back_populates="document", cascade="all, delete-orphan")


class DocumentRecord(Base):
    """
    Individual parsed and normalized financial record stored per document and thread.
    """
    __tablename__ = "document_records"

    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    record_id = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    amount_decimal = Column(String, nullable=True)
    currency = Column(String, default="USD")
    iso_date = Column(String, nullable=True)
    reference_id = Column(String, nullable=True, index=True)
    clean_reference_id = Column(String, nullable=True)
    entity = Column(String, nullable=True)
    clean_entity = Column(String, nullable=True)
    description = Column(String, nullable=True)
    raw_data_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    document = relationship("Document", back_populates="records")


class ProcessingRun(Base):
    """
    Execution run of financial processing / reconciliation in a thread.
    """
    __tablename__ = "processing_runs"

    id = Column(String, primary_key=True)  # e.g., run_4b8f...
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    status = Column(String, default="COMPLETED")  # PENDING, RUNNING, COMPLETED, FAILED
    user_prompt = Column(Text, nullable=True)
    file_count = Column(Integer, default=0)
    total_records = Column(Integer, default=0)
    matched_count = Column(Integer, default=0)
    unmatched_count = Column(Integer, default=0)
    exceptions_count = Column(Integer, default=0)
    match_rate = Column(Float, default=0.0)
    accuracy = Column(Float, default=0.0)
    precision_rate = Column(Float, default=0.0)
    recall_rate = Column(Float, default=0.0)
    f1_score = Column(Float, default=0.0)
    processing_time_sec = Column(Float, default=0.0)
    throughput_rec_sec = Column(Float, default=0.0)
    total_amount_processed = Column(Float, default=0.0)
    total_amount_matched = Column(Float, default=0.0)
    total_amount_discrepancy = Column(Float, default=0.0)
    summary_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    thread = relationship("Thread", back_populates="processing_runs")
    matches = relationship("ReconciliationResult", back_populates="run", cascade="all, delete-orphan")
    exceptions = relationship("ExceptionItemResult", back_populates="run", cascade="all, delete-orphan")


class ReconciliationResult(Base):
    """
    Pairwise matched records with complete evidence and deterministic confidence score.
    """
    __tablename__ = "reconciliation_results"

    id = Column(String, primary_key=True)  # e.g., match_...
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("processing_runs.id"), nullable=False, index=True)
    record_id_a = Column(String, nullable=False, index=True)
    record_id_b = Column(String, nullable=False, index=True)
    source_a = Column(String, nullable=False)
    source_b = Column(String, nullable=False)
    amount_a = Column(Float, nullable=False)
    amount_b = Column(Float, nullable=False)
    date_a = Column(String, nullable=True)
    date_b = Column(String, nullable=True)
    entity_a = Column(String, nullable=True)
    entity_b = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=False)
    match_category = Column(String, nullable=False)  # EXACT_MATCH, FUZZY_MATCH, DATE_LAG
    status = Column(String, default="MATCHED")  # MATCHED, VERIFIED
    evidence_json = Column(Text, nullable=True)  # Detailed evidence breakdown
    score_breakdown_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    thread = relationship("Thread", back_populates="reconciliation_results")
    run = relationship("ProcessingRun", back_populates="matches")


class ExceptionItemResult(Base):
    """
    Unresolved financial exceptions with material vs normal categorization and audit explanation.
    """
    __tablename__ = "exceptions"

    id = Column(String, primary_key=True)  # e.g., exc_...
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("processing_runs.id"), nullable=False, index=True)
    record_id = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False)
    amount = Column(Float, nullable=True)
    entity = Column(String, nullable=True)
    date = Column(String, nullable=True)
    reason_code = Column(String, nullable=False)  # AMOUNT_MISMATCH, AMBIGUOUS_CANDIDATES, MISSING_COUNTERPART, DUPLICATE
    discrepancy_category = Column(String, default="MATERIAL")  # NORMAL (small lag, rounding), MATERIAL (fee delta, missing, dup)
    confidence = Column(Float, default=0.0)
    decision = Column(String, default="UNRESOLVED")  # UNRESOLVED, AUDITED, RESOLVED
    explanation = Column(Text, nullable=False)
    amount_discrepancy = Column(Float, default=0.0)
    candidates_json = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    thread = relationship("Thread", back_populates="exceptions")
    run = relationship("ProcessingRun", back_populates="exceptions")


class AuditLog(Base):
    """
    Append-only audit trail recording every agent action, tool invocation, and decision.
    """
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)  # e.g., aud_...
    thread_id = Column(String, nullable=False, index=True)
    run_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    agent = Column(String, nullable=True)
    tool = Column(String, nullable=True)
    parameters_json = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utc_now, index=True)


class Message(Base):
    """
    ChatGPT-style conversation messages scoped to threads.
    """
    __tablename__ = "messages"

    id = Column(String, primary_key=True)  # e.g., msg_...
    thread_id = Column(String, ForeignKey("threads.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)  # Citations, tool_calls, document_ids, run_id
    created_at = Column(DateTime, default=utc_now)

    thread = relationship("Thread", back_populates="messages")


# ── Backward-Compatibility Aliases ──
ReconciliationRun = ProcessingRun
FileMetadata = Document
MatchResult = ReconciliationResult
ExceptionResult = ExceptionItemResult
ChatHistory = Message
EvaluationMetric = ProcessingRun
