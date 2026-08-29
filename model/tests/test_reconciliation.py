import pytest
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
