"""
Tests for Two-Level Duplicate Detection in Document Registry.
Verifies:
- Level 1: Exact byte duplicate detection (same bytes -> DUPLICATE_EXACT)
- Level 2: Logical dataset duplicate detection (different filename, same normalized records -> DUPLICATE_LOGICAL)
- Valid new files get processed without false positives
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from model.database.models import Base
from model.database.repositories import create_thread
from model.ingestion.registry import (
    DocumentRegistryService,
    compute_sha256_bytes,
    compute_dataset_fingerprint
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_exact_duplicate_detection(test_db, tmp_path):
    """Level 1: Uploading the exact same file twice into a thread triggers DUPLICATE_EXACT."""
    thread = create_thread(test_db, title="Upload Thread")
    csv_content = b"record_id,reference,amount,date,entity\nTX01,REF100,1500.00,2026-08-10,Acme Corp\n"

    # First upload
    doc1, res1 = DocumentRegistryService.process_and_register_file(
        db=test_db,
        thread_id=thread.id,
        filename="transactions.csv",
        content_bytes=csv_content,
        upload_dir=str(tmp_path)
    )
    assert res1["status"] == "SUCCESS"
    assert doc1 is not None
    assert doc1.record_count == 1

    # Second upload of identical file
    doc2, res2 = DocumentRegistryService.process_and_register_file(
        db=test_db,
        thread_id=thread.id,
        filename="transactions.csv",
        content_bytes=csv_content,
        upload_dir=str(tmp_path)
    )
    assert res2["status"] == "DUPLICATE_EXACT"
    assert "Exact duplicate file detected" in res2["message"]
    assert doc2.id == doc1.id


def test_logical_duplicate_detection(test_db, tmp_path):
    """Level 2: Uploading same records under a different filename triggers DUPLICATE_LOGICAL."""
    thread = create_thread(test_db, title="Logical Duplicate Thread")
    
    # File 1: settlement_v1.csv
    content1 = b"record_id,reference,amount,date,entity\nTX01,REF100,2500.00,2026-08-15,Razorpay\nTX02,REF101,1200.00,2026-08-16,Stripe\n"
    doc1, res1 = DocumentRegistryService.process_and_register_file(
        db=test_db,
        thread_id=thread.id,
        filename="settlement_v1.csv",
        content_bytes=content1,
        upload_dir=str(tmp_path)
    )
    assert res1["status"] == "SUCCESS"

    # File 2: settlement_final_renamed.csv (different bytes due to whitespace/headers, but identical normalized records)
    content2 = b"txn_id,ref_no,net_amount,txn_date,vendor\nTX01,REF100,2500.00,2026-08-15,Razorpay\nTX02,REF101,1200.00,2026-08-16,Stripe\n"
    doc2, res2 = DocumentRegistryService.process_and_register_file(
        db=test_db,
        thread_id=thread.id,
        filename="settlement_final_renamed.csv",
        content_bytes=content2,
        upload_dir=str(tmp_path)
    )
    assert res2["status"] == "DUPLICATE_LOGICAL"
    assert "Logical duplicate dataset detected" in res2["message"]


def test_distinct_files_allowed(test_db, tmp_path):
    """Different files in the same thread are successfully registered."""
    thread = create_thread(test_db, title="Multi-file Thread")
    
    content_ledger = b"record_id,amount,reference,date\nL01,500.00,REF_A,2026-08-01\n"
    content_bank = b"record_id,amount,reference,date\nB01,500.00,REF_A,2026-08-01\n"

    doc_a, res_a = DocumentRegistryService.process_and_register_file(
        db=test_db, thread_id=thread.id, filename="ledger.csv", content_bytes=content_ledger, upload_dir=str(tmp_path)
    )
    doc_b, res_b = DocumentRegistryService.process_and_register_file(
        db=test_db, thread_id=thread.id, filename="bank.csv", content_bytes=content_bank, upload_dir=str(tmp_path)
    )

    assert res_a["status"] == "SUCCESS"
    assert res_b["status"] == "SUCCESS"
    assert doc_a.id != doc_b.id
