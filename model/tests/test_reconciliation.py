import pytest
from decimal import Decimal
from ..ingestion.normalizer import NormalizedRecord
from ..reconciliation.engine import score_record_pair, ReconciliationEngine

def test_exact_match_scoring():
    rec_a = NormalizedRecord(
        record_id="TXN-101",
        source="ledger",
        raw_reference_id="INV-2026-9001",
        clean_reference_id="20269001",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=1500.00,
        amount_decimal="1500.00",
        raw_entity="Acme Cloud Corp",
        clean_entity="acme cloud corp"
    )
    rec_b = NormalizedRecord(
        record_id="BNK-501",
        source="bank",
        raw_reference_id="INV-2026-9001",
        clean_reference_id="20269001",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=1500.00,
        amount_decimal="1500.00",
        raw_entity="Acme Cloud Services",
        clean_entity="acme cloud services"
    )

    score, breakdown, category, amt_diff, days_diff = score_record_pair(rec_a, rec_b)
    assert score >= 85.0
    assert breakdown["reference_score"] == 40.0
    assert breakdown["amount_score"] == 30.0
    assert breakdown["date_score"] == 15.0
    assert category in ["EXACT_MATCH", "FUZZY_MATCH"]
    assert amt_diff == 0.0

def test_amount_mismatch_exception():
    rec_a = NormalizedRecord(
        record_id="TXN-102",
        source="ledger",
        raw_reference_id="INV-2026-9002",
        clean_reference_id="20269002",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=1000.00,
        amount_decimal="1000.00",
        raw_entity="Stripe Payments",
        clean_entity="stripe payments"
    )
    rec_b = NormalizedRecord(
        record_id="BNK-502",
        source="bank",
        raw_reference_id="INV-2026-9002",
        clean_reference_id="20269002",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=975.00,  # $25 fee
        amount_decimal="975.00",
        raw_entity="Stripe Inc",
        clean_entity="stripe inc"
    )

    engine = ReconciliationEngine(confidence_threshold=80.0)
    matches, exceptions, summary = engine.run_reconciliation([rec_a, rec_b])

    assert len(matches) == 0
    assert len(exceptions) >= 1
    mismatch_exc = [e for e in exceptions if e.reason_code == "AMOUNT_MISMATCH"]
    assert len(mismatch_exc) == 1
    assert mismatch_exc[0].amount_discrepancy == 25.0

def test_date_lag_match():
    """Test that records with same reference and amount but date lag still match."""
    rec_a = NormalizedRecord(
        record_id="TXN-103",
        source="ledger",
        raw_reference_id="INV-2026-9003",
        clean_reference_id="20269003",
        raw_date="2026-08-01",
        iso_date="2026-08-01",
        amount=2000.00,
        amount_decimal="2000.00",
        raw_entity="AWS Cloud Services",
        clean_entity="aws cloud services"
    )
    rec_b = NormalizedRecord(
        record_id="BNK-503",
        source="bank",
        raw_reference_id="INV-2026-9003",
        clean_reference_id="20269003",
        raw_date="2026-08-04",
        iso_date="2026-08-04",  # 3-day lag
        amount=2000.00,
        amount_decimal="2000.00",
        raw_entity="AWS Cloud",
        clean_entity="aws cloud"
    )

    engine = ReconciliationEngine(confidence_threshold=80.0)
    matches, exceptions, summary = engine.run_reconciliation([rec_a, rec_b])

    assert len(matches) == 1
    assert matches[0].match_category in ["EXACT_MATCH", "FUZZY_MATCH", "DATE_LAG"]

def test_missing_counterpart():
    """Test that a record with no counterpart creates an exception."""
    rec_a = NormalizedRecord(
        record_id="TXN-104",
        source="ledger",
        raw_reference_id="INV-ORPHAN-001",
        clean_reference_id="ORPHAN001",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=500.00,
        amount_decimal="500.00",
        raw_entity="Unknown Vendor",
        clean_entity="unknown vendor"
    )
    rec_b = NormalizedRecord(
        record_id="BNK-999",
        source="bank",
        raw_reference_id="COMPLETELY-DIFFERENT-REF",
        clean_reference_id="DIFFERENT",
        raw_date="2026-07-01",
        iso_date="2026-07-01",
        amount=99999.00,
        amount_decimal="99999.00",
        raw_entity="Totally Different Entity",
        clean_entity="totally different entity"
    )

    engine = ReconciliationEngine(confidence_threshold=80.0)
    matches, exceptions, summary = engine.run_reconciliation([rec_a, rec_b])

    assert len(matches) == 0
    missing = [e for e in exceptions if e.reason_code == "MISSING_COUNTERPART"]
    assert len(missing) >= 1

def test_duplicate_detection():
    """Test that duplicate records in the same source are flagged."""
    rec_a1 = NormalizedRecord(
        record_id="TXN-DUP-1",
        source="ledger",
        raw_reference_id="INV-DUP-001",
        clean_reference_id="DUP001",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=750.00,
        amount_decimal="750.00",
        raw_entity="Duplicate Corp",
        clean_entity="duplicate corp"
    )
    rec_a2 = NormalizedRecord(
        record_id="TXN-DUP-2",
        source="ledger",
        raw_reference_id="INV-DUP-001",
        clean_reference_id="DUP001",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=750.00,
        amount_decimal="750.00",
        raw_entity="Duplicate Corp",
        clean_entity="duplicate corp"
    )
    rec_b = NormalizedRecord(
        record_id="BNK-DUP",
        source="bank",
        raw_reference_id="INV-DUP-001",
        clean_reference_id="DUP001",
        raw_date="2026-08-15",
        iso_date="2026-08-15",
        amount=750.00,
        amount_decimal="750.00",
        raw_entity="Duplicate Corp",
        clean_entity="duplicate corp"
    )

    engine = ReconciliationEngine(confidence_threshold=80.0)
    matches, exceptions, summary = engine.run_reconciliation([rec_a1, rec_a2, rec_b])

    dup_exc = [e for e in exceptions if e.reason_code == "DUPLICATE"]
    assert len(dup_exc) >= 1
