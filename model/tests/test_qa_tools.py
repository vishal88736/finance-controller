"""
Tests for Deterministic QA Copilot Tools.
Verifies:
- get_transaction_result_tool (match & exception retrieval with evidence)
- get_unmatched_transactions_tool
- get_material_exceptions_tool
- get_reconciliation_summary_tool
"""

import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from model.database.models import Base, Thread, ProcessingRun, ReconciliationResult, ExceptionItemResult
from model.tools.qa_tools import (
    get_transaction_result_tool,
    get_unmatched_transactions_tool,
    get_material_exceptions_tool,
    get_reconciliation_summary_tool
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed test thread
    thread = Thread(id="thr_qa_test", title="QA Test Thread")
    session.add(thread)

    # Seed processing run
    run = ProcessingRun(
        id="run_qa_01",
        thread_id="thr_qa_test",
        total_records=100,
        matched_count=85,
        exceptions_count=15,
        match_rate=85.0,
        accuracy=97.0,
        precision_rate=100.0,
        recall_rate=96.0,
        f1_score=98.0
    )
    session.add(run)

    # Seed matched pair with evidence
    match = ReconciliationResult(
        id="match_01",
        thread_id="thr_qa_test",
        run_id="run_qa_01",
        record_id_a="TXN-LEDGER-101",
        record_id_b="BNK-STATEMENT-501",
        source_a="ledger",
        source_b="bank",
        amount_a=1500.0,
        amount_b=1500.0,
        confidence_score=98.0,
        match_category="EXACT_MATCH",
        status="MATCHED",
        evidence_json=json.dumps({"amount_diff": 0.0, "days_diff": 0, "reference_matched": True})
    )
    session.add(match)

    # Seed exception with evidence
    exc = ExceptionItemResult(
        id="exc_01",
        thread_id="thr_qa_test",
        run_id="run_qa_01",
        record_id="TXN-LEDGER-999",
        source="ledger",
        amount=250.0,
        reason_code="AMOUNT_MISMATCH",
        discrepancy_category="MATERIAL",
        confidence=75.0,
        decision="UNRESOLVED",
        explanation="Amount mismatch: $250.00 vs $243.75 ($6.25 gateway fee delta).",
        amount_discrepancy=6.25,
        evidence_json=json.dumps({"fee_percentage": 2.5, "delta": 6.25})
    )
    session.add(exc)
    session.commit()

    yield session
    session.close()


def test_get_transaction_result_matched(test_db):
    res = get_transaction_result_tool(test_db, thread_id="thr_qa_test", record_id="TXN-LEDGER-101")
    assert res["type"] == "MATCHED"
    assert res["record_id_b"] == "BNK-STATEMENT-501"
    assert res["confidence_score"] == 98.0
    assert res["evidence"]["reference_matched"] is True


def test_get_transaction_result_exception(test_db):
    res = get_transaction_result_tool(test_db, thread_id="thr_qa_test", record_id="TXN-LEDGER-999")
    assert res["type"] == "EXCEPTION"
    assert res["reason_code"] == "AMOUNT_MISMATCH"
    assert res["amount_discrepancy"] == 6.25
    assert res["discrepancy_category"] == "MATERIAL"


def test_get_material_exceptions(test_db):
    excs = get_material_exceptions_tool(test_db, thread_id="thr_qa_test")
    assert len(excs) == 1
    assert excs[0]["record_id"] == "TXN-LEDGER-999"
    assert excs[0]["fee_delta"] == 6.25


def test_get_reconciliation_summary(test_db):
    summary = get_reconciliation_summary_tool(test_db, thread_id="thr_qa_test")
    assert summary["matched_count"] == 85
    assert summary["match_rate"] == 85.0
    assert summary["precision"] == 100.0
