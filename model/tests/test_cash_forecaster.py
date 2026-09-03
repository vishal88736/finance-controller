"""
Unit tests for deterministic Cash Forecaster service.
Validates:
- 7-day and 30-day horizons
- Insufficient historical data handling
- Starting cash balance derivation
- Reproducibility (deterministic output)
- Thread isolation
"""

import uuid
import pytest
from datetime import datetime, timedelta
from model.database.models import Thread, Document, DocumentRecord, CashForecastResult, AuditLog
from model.services.cash_forecaster import cash_forecaster


def test_forecast_empty_thread(db_session):
    """Empty thread must return INSUFFICIENT_DATA without crashing."""
    th_id = f"thr_fct_mt_{uuid.uuid4().hex[:8]}"
    th = Thread(id=th_id, title="Empty Test")
    db_session.add(th)
    db_session.commit()

    res = cash_forecaster.run_forecast(db_session, th.id, horizon_days=7)
    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["forecast"] is None
    assert "No transaction or settlement records" in res["message"]


def test_forecast_reproducibility_and_horizons(db_session):
    """Deterministic forecast must produce identical outputs given identical inputs."""
    thread_id = f"thr_fct_real_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Forecast Test")
    db_session.add(th)

    doc = Document(
        id=f"doc_fct_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="test_ledger.csv",
        file_type="csv",
        content_hash_sha256=f"hash_fct_{uuid.uuid4().hex[:8]}",
        record_count=5,
    )
    db_session.add(doc)

    base_date = datetime(2026, 8, 1)
    # Add 5 days of transactions
    for i in range(5):
        d_str = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        rec = DocumentRecord(
            id=f"dr_fct_{uuid.uuid4().hex[:8]}",
            document_id=doc.id,
            thread_id=thread_id,
            record_id=f"TXN_{i}",
            source="source_a",
            amount=1000.0 * (i + 1),
            iso_date=d_str,
        )
        db_session.add(rec)
    db_session.commit()

    # Run 7-day forecast twice
    run1 = cash_forecaster.run_forecast(db_session, thread_id, horizon_days=7, current_cash_balance=5000.0)
    run2 = cash_forecaster.run_forecast(db_session, thread_id, horizon_days=7, current_cash_balance=5000.0)

    assert run1["status"] == "COMPLETED"
    assert run2["status"] == "COMPLETED"
    assert run1["projected_ending_cash"] == run2["projected_ending_cash"]
    assert run1["projected_inflows"] == run2["projected_inflows"]
    assert len(run1["daily_projections"]) == 7

    # Run 30-day forecast
    run30 = cash_forecaster.run_forecast(db_session, thread_id, horizon_days=30, current_cash_balance=5000.0)
    assert run30["status"] == "COMPLETED"
    assert len(run30["daily_projections"]) == 30
    assert run30["projected_inflows"] > run1["projected_inflows"]


def test_forecast_thread_isolation(db_session):
    """Thread A forecast must never read Thread B data."""
    th_a = Thread(id=f"thr_fct_a_{uuid.uuid4().hex[:8]}", title="Thread A")
    th_b = Thread(id=f"thr_fct_b_{uuid.uuid4().hex[:8]}", title="Thread B")
    db_session.add_all([th_a, th_b])

    doc_a = Document(id=f"doc_fct_a_{uuid.uuid4().hex[:8]}", thread_id=th_a.id, filename="a.csv", file_type="csv", content_hash_sha256="h_a")
    db_session.add(doc_a)
    rec_a = DocumentRecord(
        id=f"dr_iso_a_{uuid.uuid4().hex[:8]}", document_id=doc_a.id, thread_id=th_a.id,
        record_id="TX_A", source="ledger", amount=50000.0, iso_date="2026-08-05"
    )
    db_session.add(rec_a)
    db_session.commit()

    # Thread B is empty
    res_b = cash_forecaster.run_forecast(db_session, th_b.id, horizon_days=7)
    assert res_b["status"] == "INSUFFICIENT_DATA"

    # Thread A has data
    res_a = cash_forecaster.run_forecast(db_session, th_a.id, horizon_days=7)
    assert res_a["status"] == "COMPLETED"
    assert res_a["projected_inflows"] > 0


def test_forecast_does_not_fabricate_baseline(db_session):
    """Without an explicit balance, baseline comes from observed history — never $10,000."""
    thread_id = f"thr_fct_base_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Baseline Test")
    db_session.add(th)
    doc = Document(
        id=f"doc_fct_base_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="ledger.csv",
        file_type="csv",
        content_hash_sha256=f"base_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)
    for i, amt in enumerate([1000.0, 2000.0]):
        db_session.add(DocumentRecord(
            id=f"dr_base_{uuid.uuid4().hex[:8]}",
            document_id=doc.id,
            thread_id=thread_id,
            record_id=f"TXN_B{i}",
            source="ledger",
            amount=amt,
            iso_date=f"2026-08-0{1+i}",
        ))
    db_session.commit()

    res = cash_forecaster.run_forecast(db_session, thread_id, horizon_days=7)
    assert res["status"] == "COMPLETED"
    assert res["baseline_source"] == "HISTORY_DERIVED"
    assert res["current_cash_balance"] == 3000.0  # derived, not $10,000


def test_forecast_negative_baseline_not_clamped(db_session):
    """A negative historical net position must remain negative, not be clamped."""
    thread_id = f"thr_fct_neg_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Negative Test")
    db_session.add(th)
    doc = Document(
        id=f"doc_fct_neg_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="ledger.csv",
        file_type="csv",
        content_hash_sha256=f"neg_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)
    db_session.add(DocumentRecord(
        id=f"dr_neg_in_{uuid.uuid4().hex[:8]}", document_id=doc.id, thread_id=thread_id,
        record_id="TXN_IN", source="ledger", amount=1000.0, iso_date="2026-08-01"
    ))
    db_session.add(DocumentRecord(
        id=f"dr_neg_out_{uuid.uuid4().hex[:8]}", document_id=doc.id, thread_id=thread_id,
        record_id="TXN_OUT", source="ledger", amount=-3000.0, iso_date="2026-08-02"
    ))
    db_session.commit()

    res = cash_forecaster.run_forecast(db_session, thread_id, horizon_days=7)
    assert res["status"] == "COMPLETED"
    assert res["baseline_source"] == "HISTORY_DERIVED"
    assert res["current_cash_balance"] == -2000.0
