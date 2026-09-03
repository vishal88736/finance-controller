"""
Document Registry & Two-Level Duplicate Detection Engine.
- Level 1: Exact File Duplicate (SHA-256 of raw bytes)
- Level 2: Logical Dataset Duplicate (SHA-256 of canonical normalized records)

Ingestion hardening:
- Server-generated UUID storage names (user filenames never touch the filesystem path)
- Path traversal / absolute path / control-character rejection
- Extension + MIME sniffing + size limits
- Empty, zero-record, and malformed files rejected with explicit errors

Pure deterministic Python functions without LLM dependency.
"""

import hashlib
import json
import mimetypes
import os
import re
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


# ─────────────────────────────────────────────────────────────
# INGESTION SECURITY POLICY
# ─────────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
SUPPORTED_EXTENSIONS = {"csv", "xlsx", "xls", "json"}

# Content we allow per extension (primary sniff)
_MAGIC_SIGNATURES = {
    "xlsx": b"PK\x03\x04",       # ZIP container (xlsx)
    "xls": b"\xd0\x11\xa6",      # OLE2 container (xls)
}

_DANGEROUS_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class UploadRejected(Exception):
    """Raised when an uploaded file violates the ingestion security policy."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


def validate_upload_filename(filename: str) -> str:
    """
    Validate a user-supplied filename and return a safe display name.

    Rejects: empty names, path separators, traversal (../), absolute paths,
    control characters, and names that are too long. Returns the basename so a
    hostile client cannot influence storage paths. The returned value is used
    for display only — storage uses a server-side UUID name.
    """
    if not filename or not str(filename).strip():
        raise UploadRejected("INVALID_FILENAME", "Filename is empty.")

    raw = str(filename)

    if _DANGEROUS_NAME_CHARS.search(raw):
        raise UploadRejected("INVALID_FILENAME", "Filename contains control characters.")

    # Reject Windows and POSIX separators *and* traversal anywhere in the name
    if "\\" in raw or "/" in raw:
        raise UploadRejected(
            "PATH_TRAVERSAL", "Filename must not contain path separators."
        )
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/"):
        raise UploadRejected("PATH_TRAVERSAL", "Absolute paths are not allowed.")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise UploadRejected("PATH_TRAVERSAL", "Path traversal is not allowed.")

    # Basename defense in depth
    base = os.path.basename(normalized)
    if base in ("", ".", ".."):
        raise UploadRejected("INVALID_FILENAME", "Invalid filename.")
    if base != raw:
        # Something attempted to smuggle a path
        raise UploadRejected(
            "PATH_TRAVERSAL", "Filename must not contain path separators."
        )

    # Reject reserved device-ish names (windows) and overly long names
    stem = os.path.splitext(base)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
                "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}:
        raise UploadRejected("INVALID_FILENAME", "Reserved filename.")

    if len(base) > 255:
        raise UploadRejected("INVALID_FILENAME", "Filename exceeds 255 characters.")

    return base


def validate_upload_bytes(content: bytes, filename: str) -> str:
    """
    Validate upload bytes and extension. Returns the normalized extension.

    Checks: non-empty, size limit, supported extension, content sniffing for
    binary formats (xlsx/xls), textual sanity for csv/json.
    """
    if content is None or len(content) == 0:
        raise UploadRejected("EMPTY_FILE", "File is empty.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            "OVERSIZED_FILE",
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
        )

    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if not ext or ext not in SUPPORTED_EXTENSIONS:
        raise UploadRejected(
            "UNSUPPORTED_TYPE",
            f"Unsupported file type '{ext or '(none)'}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
        )

    # Binary container sniffing
    if ext in _MAGIC_SIGNATURES:
        sig = _MAGIC_SIGNATURES[ext]
        if not content.startswith(sig):
            # xlsx files are zip containers; a raw .xls is OLE2
            if ext == "xls" and content.startswith(b"PK\x03\x04"):
                # xlsx renamed to .xls — treat as malformed for its claimed type
                raise UploadRejected(
                    "MALFORMED_FILE",
                    "File claims to be .xls but has an XLSX (ZIP) container.",
                )
            raise UploadRejected(
                "MALFORMED_FILE",
                f"File content does not match its .{ext} extension.",
            )

    # Textual sanity for csv/json
    if ext in ("csv", "json"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadRejected("MALFORMED_FILE", "File is not valid UTF-8 text.")

    return ext


def generate_storage_name(thread_id: str, doc_uuid: str, ext: str) -> str:
    """
    Server-side storage filename. Composed entirely of trusted server values:
    thread id (validated pattern), a fresh UUID, and a validated extension.
    The user-supplied filename NEVER influences the storage path.
    """
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", thread_id or ""):
        # defensive: thread ids are generated server-side (thr_hex)
        thread_id = "thr_invalid"
    return f"{thread_id}_{doc_uuid}.{ext}"


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
    Uses generic domain keywords only — never dataset-specific filenames.
    """
    fn = filename.lower()
    if any(kw in fn for kw in ["ledger", "journal", "general_ledger", "erp"]):
        return "TRANSACTIONS"
    elif any(kw in fn for kw in ["invoice", "bill", "ar_", "ap_"]):
        return "INVOICES"
    elif any(kw in fn for kw in ["settlement", "payout", "gateway", "stripe", "razorpay"]):
        return "SETTLEMENTS"
    elif any(kw in fn for kw in ["bank", "statement", "feed"]):
        return "BANK_STATEMENTS"

    # Inspect record entities/descriptions
    for r in records[:5]:
        desc = (r.clean_description or "").lower()
        if "payout" in desc or "fee" in desc or "settlement" in desc:
            return "SETTLEMENTS"
        if "invoice" in desc:
            return "INVOICES"

    return "TRANSACTIONS"


def classify_document_role(filename: str, records: List[NormalizedRecord]):
    """
    Determine a document's domain role using the deterministic role classifier.
    Falls back to (UNKNOWN, 0.0, "") when classification is unavailable.
    """
    try:
        import pandas as pd
        from ..reconciliation.role_classifier import role_classifier

        raw_rows = [r.raw_data for r in records if r.raw_data]
        df = pd.DataFrame(raw_rows) if raw_rows else pd.DataFrame()
        cls = role_classifier.classify_document(
            df=df,
            document_id="pending",
            filename=filename,
            source_label=None,
        )
        return cls.document_role.value, cls.confidence, cls.reason
    except Exception:
        return "UNKNOWN", 0.0, ""


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
        Ingest a file into the thread with full validation and two-level
        duplicate detection:
        1. Filename & content security validation (traversal, size, type, MIME).
        2. Exact byte duplicate check (SHA-256).
        3. Parsing & normalization (zero-record files rejected).
        4. Logical dataset duplicate check (Dataset Fingerprint).
        5. Storage under a server-generated UUID name & DB registration.
        """
        # ── Security validation ──
        try:
            safe_display_name = validate_upload_filename(filename)
            ext = validate_upload_bytes(content_bytes, safe_display_name)
        except UploadRejected as rej:
            log_audit(db, thread_id=thread_id, action="DOCUMENT_UPLOAD_REJECTED", details={
                "filename": str(filename)[:128],
                "reason_code": rej.reason_code,
                "message": rej.message,
            })
            return None, {
                "status": "REJECTED",
                "reason_code": rej.reason_code,
                "message": rej.message,
                "duplicate_type": None,
            }

        os.makedirs(upload_dir, exist_ok=True)

        size_bytes = len(content_bytes)
        sha256_hash = compute_sha256_bytes(content_bytes)

        # ── LEVEL 1: Exact File Duplicate Check ──
        exact_dup = find_document_by_hash(db, thread_id=thread_id, content_hash=sha256_hash)
        if exact_dup:
            log_audit(db, thread_id=thread_id, action="DUPLICATE_FILE_DETECTED", details={
                "filename": safe_display_name,
                "existing_doc_id": exact_dup.id,
                "sha256": sha256_hash[:12]
            })
            return exact_dup, {
                "status": "DUPLICATE_EXACT",
                "message": f"Exact duplicate file detected. '{safe_display_name}' has already been uploaded to this thread as '{exact_dup.filename}'.",
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
            normalized_records = parse_file(content_bytes, filename=safe_display_name)
        except Exception as e:
            log_audit(db, thread_id=thread_id, action="DOCUMENT_UPLOAD_REJECTED", details={
                "filename": safe_display_name,
                "reason_code": "MALFORMED_FILE",
                "message": f"Parse failure: {type(e).__name__}",
            })
            return None, {
                "status": "REJECTED",
                "reason_code": "MALFORMED_FILE",
                "message": f"Failed to parse file '{safe_display_name}': {str(e)}",
                "duplicate_type": None,
            }

        if len(normalized_records) == 0:
            log_audit(db, thread_id=thread_id, action="DOCUMENT_UPLOAD_REJECTED", details={
                "filename": safe_display_name,
                "reason_code": "ZERO_RECORDS",
                "message": "File parsed to zero data records.",
            })
            return None, {
                "status": "REJECTED",
                "reason_code": "ZERO_RECORDS",
                "message": f"File '{safe_display_name}' contains no parseable data records.",
                "duplicate_type": None,
            }

        # ── LEVEL 2: Logical Dataset Duplicate Check ──
        dataset_fp = compute_dataset_fingerprint(normalized_records)
        logical_dup = find_document_by_fingerprint(db, thread_id=thread_id, fingerprint=dataset_fp)
        if logical_dup:
            log_audit(db, thread_id=thread_id, action="LOGICAL_DUPLICATE_DETECTED", details={
                "filename": safe_display_name,
                "existing_doc_id": logical_dup.id,
                "existing_filename": logical_dup.filename,
                "fingerprint": dataset_fp[:12]
            })
            return logical_dup, {
                "status": "DUPLICATE_LOGICAL",
                "message": f"Logical duplicate dataset detected. The contents of '{safe_display_name}' match existing document '{logical_dup.filename}' in this thread.",
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

        # ── Save File to Disk (server-generated UUID name; user filename never touches disk) ──
        doc_type = detect_document_type(safe_display_name, normalized_records)
        role, role_conf, role_reason = classify_document_role(safe_display_name, normalized_records)
        storage_name = generate_storage_name(thread_id, uuid.uuid4().hex[:16], ext)
        file_path = os.path.join(upload_dir, storage_name)
        with open(file_path, "wb") as f:
            f.write(content_bytes)

        # ── Register in DB ──
        doc = register_document(
            db=db,
            thread_id=thread_id,
            filename=safe_display_name,
            file_type=ext,
            content_hash=sha256_hash,
            size_bytes=size_bytes,
            file_path=file_path,
            document_type=doc_type,
            document_role=role,
            role_confidence=role_conf,
            role_reason=role_reason,
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
            "message": f"Successfully ingested '{safe_display_name}' with {len(normalized_records)} records.",
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
