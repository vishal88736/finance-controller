"""
Document Registry & Two-Level Duplicate Detection Engine.
- Level 1: Exact File Duplicate (SHA-256 of raw bytes)
- Level 2: Logical Dataset Duplicate (SHA-256 of canonical normalized records)

Pure deterministic Python functions without LLM dependency.
"""

import hashlib
import json
import os
import uuid
from typing import Dict, Any, List, Optional, Tuple, Union
from sqlalchemy.orm import Session

from ..database.models import Document, DocumentRecord, Thread
from ..database.repositories import (
    find_document_by_hash,
    find_document_by_fingerprint,
    register_document,
    log_audit
)
from .parser import parse_file
from .normalizer import NormalizedRecord


def compute_sha256_bytes(content: bytes) -> str:
    """Level 1: Compute cryptographic SHA-256 hash of raw file bytes."""
    return hashlib.sha256(content).hexdigest()


def compute_sha256_file(file_path: str) -> str:
    """Compute SHA-256 hash directly from file path."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_dataset_fingerprint(records: List[NormalizedRecord]) -> str:
    """
    Level 2: Compute deterministic dataset fingerprint based on sorted canonical records.
    Catches identical datasets uploaded with different filenames (e.g. settlement_01.csv vs settlement_final.csv).
    """
    if not records:
        return ""

    # Build canonical representation of each record
    canonical_items = []
    for r in records:
        canonical_items.append({
            "id": r.record_id or "",
            "amount": f"{r.amount:.2f}",
            "ref": r.clean_reference_id or "",
            "date": r.iso_date or "",
            "entity": r.clean_entity or "",
            "desc": r.clean_description or ""
        })

    # Sort deterministically by id, amount, ref, date
    canonical_items.sort(key=lambda x: (x["id"], x["amount"], x["ref"], x["date"]))
    
    # Serialize to deterministic JSON string
    serialized = json.dumps(canonical_items, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def detect_document_type(filename: str, records: List[NormalizedRecord]) -> str:
    """
    Determine semantic financial document type from filename tokens and column patterns.
    """
    fn = filename.lower()
    if any(kw in fn for kw in ["ledger", "journal", "general_ledger", "source_a", "erp"]):
        return "TRANSACTIONS"
    elif any(kw in fn for kw in ["invoice", "bill", "ar_", "ap_"]):
        return "INVOICES"
    elif any(kw in fn for kw in ["settlement", "payout", "gateway", "stripe", "razorpay", "source_c"]):
        return "SETTLEMENTS"
    elif any(kw in fn for kw in ["bank", "statement", "source_b", "feed"]):
        return "BANK_STATEMENTS"

    # Inspect record entities/descriptions
    for r in records[:5]:
        desc = (r.clean_description or "").lower()
        if "payout" in desc or "fee" in desc or "settlement" in desc:
            return "SETTLEMENTS"
        if "invoice" in desc:
            return "INVOICES"

    return "TRANSACTIONS"


class DocumentRegistryService:
    """
    Service handling file ingestion, duplicate detection, parsing, and database persistence.
    """

    @staticmethod
    def process_and_register_file(
        db: Session,
        thread_id: str,
        filename: str,
        content_bytes: bytes,
        upload_dir: str = "uploads"
    ) -> Tuple[Optional[Document], Dict[str, Any]]:
        """
        Ingest a file into the thread with two-level duplicate detection:
        1. Exact byte duplicate check (SHA-256).
        2. Parsing & normalization.
        3. Logical dataset duplicate check (Dataset Fingerprint).
        4. Storage & Registration.
        """
        os.makedirs(upload_dir, exist_ok=True)

        size_bytes = len(content_bytes)
        ext = os.path.splitext(filename)[1].lower().replace(".", "") or "csv"
        sha256_hash = compute_sha256_bytes(content_bytes)

        # ── LEVEL 1: Exact File Duplicate Check ──
        exact_dup = find_document_by_hash(db, thread_id=thread_id, content_hash=sha256_hash)
        if exact_dup:
            log_audit(db, thread_id=thread_id, action="DUPLICATE_FILE_DETECTED", details={
                "filename": filename,
                "existing_doc_id": exact_dup.id,
                "sha256": sha256_hash[:12]
            })
            return exact_dup, {
                "status": "DUPLICATE_EXACT",
                "message": f"Exact duplicate file detected. '{filename}' has already been uploaded to this thread as '{exact_dup.filename}'.",
                "duplicate_type": "EXACT_FILE",
                "document": {
                    "id": exact_dup.id,
                    "filename": exact_dup.filename,
                    "record_count": exact_dup.record_count,
                    "document_type": exact_dup.document_type,
                    "uploaded_at": exact_dup.uploaded_at.isoformat() if exact_dup.uploaded_at else None,
                    "sha256": exact_dup.content_hash_sha256
                }
            }

        # ── Parse and Normalize ──
        try:
            normalized_records = parse_file(content_bytes, filename=filename)
        except Exception as e:
            return None, {
                "status": "ERROR",
                "message": f"Failed to parse file '{filename}': {str(e)}",
                "duplicate_type": None
            }

        # ── LEVEL 2: Logical Dataset Duplicate Check ──
        dataset_fp = compute_dataset_fingerprint(normalized_records)
        logical_dup = find_document_by_fingerprint(db, thread_id=thread_id, fingerprint=dataset_fp)
        if logical_dup and len(normalized_records) > 0:
            log_audit(db, thread_id=thread_id, action="LOGICAL_DUPLICATE_DETECTED", details={
                "filename": filename,
                "existing_doc_id": logical_dup.id,
                "existing_filename": logical_dup.filename,
                "fingerprint": dataset_fp[:12]
            })
            return logical_dup, {
                "status": "DUPLICATE_LOGICAL",
                "message": f"Logical duplicate dataset detected. The contents of '{filename}' match existing document '{logical_dup.filename}' in this thread.",
                "duplicate_type": "LOGICAL_DATASET",
                "document": {
                    "id": logical_dup.id,
                    "filename": logical_dup.filename,
                    "record_count": logical_dup.record_count,
                    "document_type": logical_dup.document_type,
                    "uploaded_at": logical_dup.uploaded_at.isoformat() if logical_dup.uploaded_at else None,
                    "dataset_fingerprint": dataset_fp
                }
            }

        # ── Save File to Disk ──
        doc_type = detect_document_type(filename, normalized_records)
        safe_filename = f"{thread_id}_{sha256_hash[:8]}_{filename}"
        file_path = os.path.join(upload_dir, safe_filename)
        with open(file_path, "wb") as f:
            f.write(content_bytes)

        # ── Register in DB ──
        doc = register_document(
            db=db,
            thread_id=thread_id,
            filename=filename,
            file_type=ext,
            content_hash=sha256_hash,
            size_bytes=size_bytes,
            file_path=file_path,
            document_type=doc_type,
            dataset_fingerprint=dataset_fp,
            record_count=len(normalized_records),
            processing_status="PROCESSED"
        )

        # ── Store Document Records ──
        for r in normalized_records:
            dr = DocumentRecord(
                id=f"dr_{uuid.uuid4().hex[:12]}",
                document_id=doc.id,
                thread_id=thread_id,
                record_id=r.record_id,
                source=r.source,
                amount=r.amount,
                amount_decimal=r.amount_decimal,
                currency=r.currency,
                iso_date=r.iso_date,
                reference_id=r.raw_reference_id,
                clean_reference_id=r.clean_reference_id,
                entity=r.raw_entity,
                clean_entity=r.clean_entity,
                description=r.raw_description,
                raw_data_json=json.dumps(r.raw_data) if r.raw_data else None
            )
            db.add(dr)
        db.commit()

        return doc, {
            "status": "SUCCESS",
            "message": f"Successfully ingested '{filename}' with {len(normalized_records)} records.",
            "duplicate_type": None,
            "document": {
                "id": doc.id,
                "filename": doc.filename,
                "record_count": doc.record_count,
                "document_type": doc.document_type,
                "sha256": doc.content_hash_sha256,
                "dataset_fingerprint": doc.dataset_fingerprint,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None
            }
        }
