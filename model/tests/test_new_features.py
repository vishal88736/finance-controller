import pandas as pd
from model.reconciliation.pandas_reconciler import pandas_reconciler

def test_feature_a_fee_netting():
    """
    Test Fee Netting (Feature A): 
    Ledger has Net Amount 95.
    Bank has Gross Amount 100, Fee 5. -> Net Amount 95.
    They should match successfully since net_amount_a (95) and net_amount_b (95) match exactly.
    """
    df_ledger = pd.DataFrame({
        "transaction_id": ["REC-100"],
        "amount": [95.0],  # Already net
        "date": ["2026-08-01"],
        "entity": ["Vendor"],
    })

    df_bank = pd.DataFrame({
        "txn_id": ["REC-100"],
        "amount": [100.0],  # Gross
        "processing_fee": [5.0], 
        "value_date": ["2026-08-01"],
        "payee": ["Vendor"],
    })

    docs = [
        (df_ledger, "doc_ledger", "ledger.csv", "ledger"),
        (df_bank, "doc_bank", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    
    # Evidence should break down fees and net amounts
    assert match["evidence"]["fee_amount_b"] == 5.0
    assert match["evidence"]["net_amount_b"] == 95.0


def test_feature_c_fx_handling():
    """
    Test FX Handling (Feature C):
    Same transaction ID, but currencies differ.
    Should produce a CURRENCY_MISMATCH exception instead of an amount match.
    """
    df_ledger = pd.DataFrame({
        "transaction_id": ["FX-200"],
        "amount": [100.0],
        "currency": ["USD"],
        "date": ["2026-08-01"],
        "entity": ["Vendor"],
    })

    df_bank = pd.DataFrame({
        "txn_id": ["FX-200"],
        "amount": [85.0],
        "currency": ["EUR"],  # Mismatch!
        "value_date": ["2026-08-01"],
        "payee": ["Vendor"],
    })

    docs = [
        (df_ledger, "doc_ledger", "ledger.csv", "ledger"),
        (df_bank, "doc_bank", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    
    assert len(result["matches"]) == 0
    assert len(result["exceptions"]) > 0
    
    # Check for CURRENCY_MISMATCH
    has_fx_exception = any(exc["reason_code"] == "CURRENCY_MISMATCH" for exc in result["exceptions"])
    assert has_fx_exception

def test_feature_phase3_multi_way():
    df_ledger = pd.DataFrame({
        "transaction_id": ["REC-100", "REC-101", "REC-102"],
        "amount": [100.0, 200.0, 300.0],
        "date": ["2026-08-01", "2026-08-01", "2026-08-01"],
        "entity": ["Vendor", "Vendor", "Vendor"],
    })

    df_bank = pd.DataFrame({
        "txn_id": ["REC-100", "REC-101"],
        "amount": [100.0, 200.0],
        "value_date": ["2026-08-01", "2026-08-01"],
        "payee": ["Vendor", "Vendor"],
    })

    df_processor = pd.DataFrame({
        "payout_id": ["REC-100", "REC-101", "REC-102"],
        "amount": [100.0, 190.0, 300.0],
        "date": ["2026-08-01", "2026-08-01", "2026-08-01"],
        "merchant": ["Vendor", "Vendor", "Vendor"],
    })

    docs = [
        (df_ledger, "doc_ledger", "ledger.csv", "ledger"),
        (df_bank, "doc_bank", "bank.csv", "bank"),
        (df_processor, "doc_processor", "processor.csv", "processor"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    
    assert result["reconciliation_plan"]["relationship"] == "MULTI_SOURCE_RECONCILIATION"
    msr = result["multi_source_reconciliation"]
    assert msr["summary"]["total_groups"] == 3
    
    # REC-100: All 3 sources present and agree (100.0) -> ALL_AGREE
    g1 = next(g for g in msr["groups"] if g["canonical_transaction_id"] == "REC-100")
    assert g1["status"] == "ALL_AGREE"

    # REC-101: 3 sources, but processor disagrees (190.0 vs 200.0) -> ONE_DISAGREES
    g2 = next(g for g in msr["groups"] if g["canonical_transaction_id"] == "REC-101")
    assert g2["status"] == "ONE_DISAGREES"

    # REC-102: Ledger & Processor present, Bank missing -> MISSING_SOURCE
    g3 = next(g for g in msr["groups"] if g["canonical_transaction_id"] == "REC-102")
    assert g3["status"] == "MISSING_SOURCE"


def test_missing_amount_handling():
    """
    Test Phase 2: Missing Amount handling.
    Ensure missing/null amounts don't get converted to 0.0 but rather skipped/marked INVALID.
    """
    from model.verification.normalizers import parse_optional_amount
    assert parse_optional_amount(None) is None
    assert parse_optional_amount("") is None
    assert parse_optional_amount("N/A") is None
    assert parse_optional_amount("-") is None
    assert parse_optional_amount(0) is not None
    assert parse_optional_amount(0.0) is not None
    assert parse_optional_amount("0.00") is not None


def test_cash_forecaster_horizons():
    """
    Test Phase 6: Cash forecaster validates horizons.
    """
    from model.services.cash_forecaster import cash_forecaster, CashForecastingError
    from sqlalchemy.orm import Session
    from unittest.mock import MagicMock
    import pytest
    
    db = MagicMock(spec=Session)
    
    # Invalid horizons should raise CashForecastingError
    with pytest.raises(CashForecastingError):
        cash_forecaster.run_forecast(db=db, thread_id="t1", horizon_days=0)
        
    with pytest.raises(CashForecastingError):
        cash_forecaster.run_forecast(db=db, thread_id="t1", horizon_days=95)
        
    with pytest.raises(CashForecastingError):
        cash_forecaster.run_forecast(db=db, thread_id="t1", horizon_days="invalid")
