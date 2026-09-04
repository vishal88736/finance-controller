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
