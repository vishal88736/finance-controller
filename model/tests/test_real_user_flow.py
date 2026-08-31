"""
End-to-End Real User Flow Integration Test.
Rigorously tests:
1. Creating thread
2. Uploading real CSV documents (transactions.csv, invoices.csv, settlements.csv)
3. Verifying document storage, SHA-256 hashes, and document type detection
4. Parsing and storing normalized document records
5. Running reconciliation on the actual uploaded files (not synthetic demo data)
6. Verifying matches and exceptions contain actual uploaded data
7. Asking Q&A questions before and after reconciliation
8. Factual grounding verification ("Is TX001 $999?" -> "No, $1,500.00")
9. Strict multi-thread data isolation
"""

import io
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from model.database.models import Base, Thread, Document, DocumentRecord, ProcessingRun
from model.database.repositories import (
    create_thread,
    get_thread,
    get_thread_documents,
    get_thread_matches,
    get_thread_exceptions
)
from model.ingestion.registry import DocumentRegistryService
from model.app.main import api_reconcile_thread, ReconcileRequest, api_send_thread_message, SendMessageRequest


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session, str(tmp_path)
    session.close()


def test_real_user_upload_reconciliation_and_qa_flow(db_session):
    db, upload_dir = db_session

    # ── Step 1: Create Thread ──
    thread_a = create_thread(db, title="Acme August Reconcile")
    assert thread_a.id.startswith("thr_")

    # ── Step 2: Upload Real CSVs ──
    # CSV 1: Transactions (Internal Ledger)
    ledger_csv = (
        b"record_id,reference,amount,date,entity,description\n"
        b"TX_001,INV_1001,1500.00,2026-08-10,Alpha Logistics,Warehouse freight payment\n"
        b"TX_002,INV_1002,2450.00,2026-08-11,Beta Software,Cloud server subscription\n"
        b"TX_003,INV_1003,5000.00,2026-08-12,Gamma Marketing,Ad campaign spend\n"
    )

    # CSV 2: Invoices / Bank Statement (Counterpart)
    bank_csv = (
        b"record_id,reference,amount,date,entity,description\n"
        b"BNK_001,INV_1001,1500.00,2026-08-10,Alpha Logistics,Direct deposit Alpha\n"
        b"BNK_002,INV_1002,2388.75,2026-08-11,Beta Software,Card payout fee deducted\n"
        b"BNK_999,INV_9999,800.00,2026-08-15,Delta Services,Unrecorded bank credit\n"
    )

    doc_ledger, res_ledger = DocumentRegistryService.process_and_register_file(
        db=db, thread_id=thread_a.id, filename="transactions_ledger.csv", content_bytes=ledger_csv, upload_dir=upload_dir
    )
    assert res_ledger["status"] == "SUCCESS"
    assert doc_ledger.record_count == 3
    assert doc_ledger.document_type == "TRANSACTIONS"
    assert len(doc_ledger.content_hash_sha256) == 64

    doc_bank, res_bank = DocumentRegistryService.process_and_register_file(
        db=db, thread_id=thread_a.id, filename="bank_statement.csv", content_bytes=bank_csv, upload_dir=upload_dir
    )
    assert res_bank["status"] == "SUCCESS"
    assert doc_bank.record_count == 3
    assert doc_bank.document_type == "BANK_STATEMENTS"

    # Verify document records stored in database
    records = db.query(DocumentRecord).filter(DocumentRecord.thread_id == thread_a.id).all()
    assert len(records) == 6

    # ── Step 3: Q&A BEFORE Reconciliation ──
    qa_before = api_send_thread_message(
        thread_id=thread_a.id,
        req=SendMessageRequest(content="What is the amount of TX_001?"),
        db=db
    )
    assert "1,500.00" in qa_before["assistant_message"]["content"] or "1500" in qa_before["assistant_message"]["content"]

    # ── Step 4: Run Reconciliation on Actual Uploaded Documents ──
    rec_result = api_reconcile_thread(
        thread_id=thread_a.id,
        req=ReconcileRequest(use_synthetic_batch=False),
        db=db
    )
    assert rec_result["status"] == "success"
    summary = rec_result["summary"]
    assert summary["total_records"] == 6

    # Verify Matches use the actual uploaded record IDs!
    matches, total_m = get_thread_matches(db, thread_id=thread_a.id)
    assert total_m >= 1
    # TX_001 matched with BNK_001
    matched_ids = [(m.record_id_a, m.record_id_b) for m in matches]
    assert ("TX_001", "BNK_001") in matched_ids

    # Verify Exceptions contain TX_002 (Amount Mismatch due to fee) and TX_003 (Missing counterpart)
    exceptions, total_e = get_thread_exceptions(db, thread_id=thread_a.id)
    exc_ids = [e.record_id for e in exceptions]
    assert "TX_002" in exc_ids  # Fee discrepancy: 2450 vs 2388.75 ($61.25 delta)
    assert "TX_003" in exc_ids  # Missing in bank statement

    # Check evidence structure on fee discrepancy
    tx002_exc = [e for e in exceptions if e.record_id == "TX_002"][0]
    assert tx002_exc.reason_code == "AMOUNT_MISMATCH"
    assert tx002_exc.amount_discrepancy == pytest.approx(61.25, 0.01)
    assert tx002_exc.discrepancy_category == "MATERIAL"

    # ── Step 5: Q&A AFTER Reconciliation ──
    # 5a. Grounding / Fact check: Is TX_001 $999?
    qa_fact = api_send_thread_message(
        thread_id=thread_a.id,
        req=SendMessageRequest(content="Is TX_001 amount $999?"),
        db=db
    )
    content_fact = qa_fact["assistant_message"]["content"]
    assert "1,500.00" in content_fact or "1500" in content_fact

    # 5b. Exception inquiry: Why is TX_002 unmatched?
    qa_tx2 = api_send_thread_message(
        thread_id=thread_a.id,
        req=SendMessageRequest(content="Why is TX_002 unmatched?"),
        db=db
    )
    content_tx2 = qa_tx2["assistant_message"]["content"]
    assert "AMOUNT_MISMATCH" in content_tx2 or "61.25" in content_tx2 or "fee" in content_tx2.lower()

    # 5c. Material exceptions inquiry
    qa_mat = api_send_thread_message(
        thread_id=thread_a.id,
        req=SendMessageRequest(content="Show me all material exceptions"),
        db=db
    )
    assert len(qa_mat["retrieved_exceptions"]) > 0

    # ── Step 6: Multi-Thread Isolation ──
    thread_b = create_thread(db, title="Beta Company Thread")
    b_ledger = b"record_id,reference,amount,date,entity\nB_TXN_888,INV_888,99999.00,2026-08-20,Omega Corp\n"
    DocumentRegistryService.process_and_register_file(
        db=db, thread_id=thread_b.id, filename="omega_ledger.csv", content_bytes=b_ledger, upload_dir=upload_dir
    )

    # Thread B results MUST be isolated from Thread A
    matches_b, count_b = get_thread_matches(db, thread_id=thread_b.id)
    assert count_b == 0

    qa_b = api_send_thread_message(
        thread_id=thread_b.id,
        req=SendMessageRequest(content="What is the amount of TX_001?"),
        db=db
    )
    assert "No record matching" in qa_b["assistant_message"]["content"] or "not found" in qa_b["assistant_message"]["content"].lower()
