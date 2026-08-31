"""
Repository layer providing thread-isolated database operations for:
- Threads (Create, List, Get, Update title, Delete)
- Messages (Add, List by thread)
- Documents (Registry query, find by SHA-256 / dataset fingerprint)
- Processing Runs & Results (Thread-scoped reconciliation results & exceptions)
- Audit Logs (Append-only logging)
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import (
    Thread,
    Document,
    DocumentRecord,
    ProcessingRun,
    ReconciliationResult,
    ExceptionItemResult,
    AuditLog,
    Message
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────
# THREAD REPOSITORY
# ─────────────────────────────────────────────────────────────

def create_thread(db: Session, title: str = "New Conversation") -> Thread:
    """Create a new thread with unique ID."""
    thread_id = f"thr_{uuid.uuid4().hex[:12]}"
    thread = Thread(
        id=thread_id,
        title=title,
        created_at=utc_now(),
        updated_at=utc_now()
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    log_audit(db, thread_id=thread_id, action="CREATE_THREAD", details={"title": title})
    return thread


def get_thread(db: Session, thread_id: str) -> Optional[Thread]:
    """Retrieve a single thread by ID."""
    return db.query(Thread).filter(Thread.id == thread_id).first()


def list_threads(db: Session, limit: int = 50) -> List[Thread]:
    """List threads ordered by recent activity."""
    return db.query(Thread).order_by(Thread.updated_at.desc()).limit(limit).all()


def update_thread_title(db: Session, thread_id: str, title: str) -> Optional[Thread]:
    """Update title of a thread."""
    thread = get_thread(db, thread_id)
    if thread:
        thread.title = title
        thread.updated_at = utc_now()
        db.commit()
        db.refresh(thread)
    return thread


def delete_thread(db: Session, thread_id: str) -> bool:
    """Delete a thread and all cascading records."""
    thread = get_thread(db, thread_id)
    if thread:
        db.delete(thread)
        db.commit()
        return True
    return False


# ─────────────────────────────────────────────────────────────
# MESSAGE REPOSITORY
# ─────────────────────────────────────────────────────────────

def add_message(
    db: Session,
    thread_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Message:
    """Add a message to a thread and update thread timestamp."""
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    msg = Message(
        id=msg_id,
        thread_id=thread_id,
        role=role,
        content=content,
        metadata_json=json.dumps(metadata) if metadata else None,
        created_at=utc_now()
    )
    db.add(msg)
    
    # Touch thread updated_at
    thread = get_thread(db, thread_id)
    if thread:
        thread.updated_at = utc_now()
    
    db.commit()
    db.refresh(msg)
    return msg


def get_thread_messages(db: Session, thread_id: str, limit: int = 100) -> List[Message]:
    """Get all messages for a specific thread."""
    return (
        db.query(Message)
        .filter(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .all()
    )


# ─────────────────────────────────────────────────────────────
# DOCUMENT REGISTRY REPOSITORY
# ─────────────────────────────────────────────────────────────

def find_document_by_hash(db: Session, thread_id: str, content_hash: str) -> Optional[Document]:
    """Exact byte duplicate check (Level 1) within the thread."""
    return (
        db.query(Document)
        .filter(
            Document.thread_id == thread_id,
            Document.content_hash_sha256 == content_hash
        )
        .first()
    )


def find_document_by_fingerprint(db: Session, thread_id: str, fingerprint: str) -> Optional[Document]:
    """Logical dataset duplicate check (Level 2) within the thread."""
    if not fingerprint:
        return None
    return (
        db.query(Document)
        .filter(
            Document.thread_id == thread_id,
            Document.dataset_fingerprint == fingerprint
        )
        .first()
    )


def register_document(
    db: Session,
    thread_id: str,
    filename: str,
    file_type: str,
    content_hash: str,
    size_bytes: int,
    file_path: Optional[str] = None,
    document_type: str = "UNKNOWN",
    dataset_fingerprint: Optional[str] = None,
    record_count: int = 0,
    processing_status: str = "PENDING"
) -> Document:
    """Register a new document in the thread registry."""
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    doc = Document(
        id=doc_id,
        thread_id=thread_id,
        filename=filename,
        file_type=file_type,
        content_hash_sha256=content_hash,
        dataset_fingerprint=dataset_fingerprint,
        size_bytes=size_bytes,
        record_count=record_count,
        document_type=document_type,
        processing_status=processing_status,
        file_path=file_path,
        uploaded_at=utc_now()
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log_audit(db, thread_id=thread_id, action="REGISTER_DOCUMENT", details={
        "document_id": doc_id, "filename": filename, "sha256": content_hash[:12]
    })
    return doc


def get_thread_documents(db: Session, thread_id: str) -> List[Document]:
    """Get all documents registered in a thread."""
    return (
        db.query(Document)
        .filter(Document.thread_id == thread_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


# ─────────────────────────────────────────────────────────────
# PROCESSING RUN & RESULTS REPOSITORY (THREAD SCOPED)
# ─────────────────────────────────────────────────────────────

def get_latest_run(db: Session, thread_id: str) -> Optional[ProcessingRun]:
    """Get latest processing run for a thread."""
    return (
        db.query(ProcessingRun)
        .filter(ProcessingRun.thread_id == thread_id)
        .order_by(ProcessingRun.created_at.desc())
        .first()
    )


def get_thread_matches(
    db: Session,
    thread_id: str,
    run_id: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 250,
    offset: int = 0
) -> Tuple[List[ReconciliationResult], int]:
    """Get reconciliation matched pairs scoped strictly to thread."""
    query = db.query(ReconciliationResult).filter(ReconciliationResult.thread_id == thread_id)
    if run_id:
        query = query.filter(ReconciliationResult.run_id == run_id)
    if category and category != "ALL":
        query = query.filter(ReconciliationResult.match_category == category)
    if search:
        s = f"%{search}%"
        query = query.filter(
            (ReconciliationResult.record_id_a.like(s)) |
            (ReconciliationResult.record_id_b.like(s)) |
            (ReconciliationResult.entity_a.like(s)) |
            (ReconciliationResult.entity_b.like(s))
        )
    total = query.count()
    items = query.order_by(ReconciliationResult.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def get_thread_exceptions(
    db: Session,
    thread_id: str,
    run_id: Optional[str] = None,
    reason: Optional[str] = None,
    category: Optional[str] = None,  # NORMAL vs MATERIAL
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0
) -> Tuple[List[ExceptionItemResult], int]:
    """Get unresolved exceptions scoped strictly to thread."""
    query = db.query(ExceptionItemResult).filter(ExceptionItemResult.thread_id == thread_id)
    if run_id:
        query = query.filter(ExceptionItemResult.run_id == run_id)
    if reason and reason != "ALL":
        query = query.filter(ExceptionItemResult.reason_code == reason)
    if category and category != "ALL":
        query = query.filter(ExceptionItemResult.discrepancy_category == category)
    if search:
        s = f"%{search}%"
        query = query.filter(
            (ExceptionItemResult.record_id.like(s)) |
            (ExceptionItemResult.entity.like(s)) |
            (ExceptionItemResult.explanation.like(s))
        )
    total = query.count()
    items = query.order_by(ExceptionItemResult.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


# ─────────────────────────────────────────────────────────────
# AUDIT LOG REPOSITORY (APPEND-ONLY)
# ─────────────────────────────────────────────────────────────

def log_audit(
    db: Session,
    thread_id: str,
    action: str,
    agent: Optional[str] = None,
    tool: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    result_summary: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None
) -> AuditLog:
    """Append a new immutable entry to the audit log."""
    log_id = f"aud_{uuid.uuid4().hex[:12]}"
    audit_entry = AuditLog(
        id=log_id,
        thread_id=thread_id,
        run_id=run_id,
        action=action,
        agent=agent,
        tool=tool,
        parameters_json=json.dumps(parameters) if parameters else None,
        result_summary=result_summary,
        details_json=json.dumps(details) if details else None,
        timestamp=utc_now()
    )
    db.add(audit_entry)
    try:
        db.commit()
    except Exception:
        db.rollback()
    return audit_entry


def get_audit_trail(db: Session, thread_id: str, limit: int = 50) -> List[AuditLog]:
    """Retrieve audit history for a thread."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.thread_id == thread_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
