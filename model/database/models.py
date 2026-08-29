"""
SQLAlchemy database models for AI Finance Controller.
Stores:
- ReconciliationRun
- FileMetadata
- NormalizedRecord
- MatchResult
- ExceptionResult
- EvaluationMetric
- ChatHistory
"""

import json
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    user_prompt = Column(Text, nullable=True)
    file_count = Column(Integer, default=0)
    total_records = Column(Integer, default=0)
    matched_records = Column(Integer, default=0)
    unmatched_records = Column(Integer, default=0)
    exception_records = Column(Integer, default=0)
    match_rate = Column(Float, default=0.0)
    accuracy = Column(Float, default=0.0)
    precision_rate = Column(Float, default=0.0)
    recall_rate = Column(Float, default=0.0)
    processing_time_sec = Column(Float, default=0.0)
    throughput_rec_sec = Column(Float, default=0.0)
    summary_text = Column(Text, nullable=True)

    files = relationship("FileMetadata", back_populates="run", cascade="all, delete-orphan")
    matches = relationship("MatchResult", back_populates="run", cascade="all, delete-orphan")
    exceptions = relationship("ExceptionResult", back_populates="run", cascade="all, delete-orphan")
    metrics = relationship("EvaluationMetric", back_populates="run", uselist=False, cascade="all, delete-orphan")
    chats = relationship("ChatHistory", back_populates="run", cascade="all, delete-orphan")

class FileMetadata(Base):
    __tablename__ = "files_metadata"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("reconciliation_runs.id"))
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # csv, xlsx, pdf
    file_size_bytes = Column(Integer, default=0)
    record_count = Column(Integer, default=0)
    source_label = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ReconciliationRun", back_populates="files")

class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("reconciliation_runs.id"))
    record_id_a = Column(String, nullable=False)
    record_id_b = Column(String, nullable=False)
    source_a = Column(String, nullable=False)
    source_b = Column(String, nullable=False)
    amount_a = Column(Float, nullable=False)
    amount_b = Column(Float, nullable=False)
    date_a = Column(String, nullable=True)
    date_b = Column(String, nullable=True)
    entity_a = Column(String, nullable=True)
    entity_b = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=False)
    match_category = Column(String, nullable=False)  # EXACT, FUZZY, DATE_LAG
    status = Column(String, default="MATCHED")  # MATCHED, VERIFIED
    score_breakdown_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ReconciliationRun", back_populates="matches")

class ExceptionResult(Base):
    __tablename__ = "exception_results"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("reconciliation_runs.id"))
    record_id = Column(String, nullable=False)
    source = Column(String, nullable=False)
    amount = Column(Float, nullable=True)
    entity = Column(String, nullable=True)
    date = Column(String, nullable=True)
    reason_code = Column(String, nullable=False)  # AMOUNT_MISMATCH, AMBIGUOUS_CANDIDATES, MISSING_COUNTERPART, DUPLICATE
    confidence = Column(Float, default=0.0)
    decision = Column(String, default="UNRESOLVED")
    explanation = Column(Text, nullable=False)
    candidates_json = Column(Text, nullable=True)
    amount_discrepancy = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ReconciliationRun", back_populates="exceptions")

class EvaluationMetric(Base):
    __tablename__ = "evaluation_metrics"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("reconciliation_runs.id"))
    total_ground_truth_cases = Column(Integer, default=0)
    true_positives = Column(Integer, default=0)
    false_positives = Column(Integer, default=0)
    false_negatives = Column(Integer, default=0)
    true_negatives = Column(Integer, default=0)
    precision = Column(Float, default=0.0)
    recall = Column(Float, default=0.0)
    f1_score = Column(Float, default=0.0)
    accuracy = Column(Float, default=0.0)
    match_rate = Column(Float, default=0.0)
    processing_time_sec = Column(Float, default=0.0)
    throughput_records_per_sec = Column(Float, default=0.0)
    confusion_matrix_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ReconciliationRun", back_populates="metrics")

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("reconciliation_runs.id"), nullable=True)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    retrieved_data_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ReconciliationRun", back_populates="chats")
