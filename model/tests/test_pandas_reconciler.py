"""
Unit tests for deterministic Pandas + NumPy Reconciliation Engine.
Validates:
    - Multi-document reconciliation across different column naming schemas
    - Exact matching, tolerance matching, and fuzzy matching
    - Duplicate detection via pandas grouping
    - Preservation of row and document provenance
    - Diagnostics for 0% match scenarios
"""

import pytest
import pandas as pd
from model.reconciliation.pandas_reconciler import pandas_reconciler, PandasReconciliationEngine


def test_pandas_reconciler_exact_match_different_schemas():
    """
    Test reconciliation between two files with completely different column names:
    File A: record_id, transaction_amount, transaction_date, vendor
    File B: txn_id, amount, value_date, merchant
    """
    df_a = pd.DataFrame({
        "record_id": ["LEDGER-101", "LEDGER-102"],
        "transaction_amount": [1500.00, 2750.50],
        "transaction_date": ["2026-08-01", "2026-08-02"],
        "vendor": ["Stripe Payments", "AWS Cloud"],
    })

    df_b = pd.DataFrame({
        "txn_id": ["LEDGER-101", "LEDGER-102"],
        "amount": [1500.00, 2750.50],
        "value_date": ["2026-08-01", "2026-08-02"],
        "merchant": ["Stripe Payments", "AWS Cloud"],
    })

    docs = [
        (df_a, "doc_ledger", "internal_ledger.csv", "ledger"),
        (df_b, "doc_bank", "bank_statement.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    assert result["status"] == "COMPLETED"
    assert result["records_processed"] == 4
    assert len(result["matches"]) == 2
    assert result["match_rate"] == 100.0
    assert result["exact_matches_count"] == 2

    # Verify provenance preservation
    m0 = result["matches"][0]
    assert m0["provenance_a"]["document_id"] == "doc_ledger"
    assert m0["provenance_a"]["row_index"] == 0
    assert m0["provenance_b"]["document_id"] == "doc_bank"
    assert m0["provenance_b"]["row_index"] == 0


def test_match_preserves_entity_provenance():
    """Each match must carry the counterparty names on both sides."""
    df_a = pd.DataFrame({
        "record_id": ["LEDGER-101"],
        "amount": [1500.00],
        "date": ["2026-08-01"],
        "entity": ["Stripe Payments"],
    })
    df_b = pd.DataFrame({
        "record_id": ["LEDGER-101"],
        "amount": [1500.00],
        "date": ["2026-08-01"],
        "entity": ["Stripe Inc"],
    })

    docs = [
        (df_a, "doc_ledger", "internal_ledger.csv", "ledger"),
        (df_b, "doc_bank", "bank_statement.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert len(result["matches"]) == 1
    m = result["matches"][0]
    assert m["entity_a"] == "Stripe Payments"
    assert m["entity_b"] == "Stripe Inc"
    assert m["counterpart_document_id"] == "doc_bank"
    assert m["counterpart_row_index"] == 0


def test_pandas_reconciler_tolerance_fee_delta():
    """
    Test matching where amount has a small fee variance ($1.25 fee deducted by gateway).
    """
    df_a = pd.DataFrame({
        "record_id": ["ORD-501"],
        "amount": [100.00],
        "date": ["2026-08-05"],
        "entity": ["Customer A"],
    })

    df_b = pd.DataFrame({
        "record_id": ["ORD-501"],
        "amount": [98.75],  # $1.25 gateway fee delta
        "date": ["2026-08-05"],
        "entity": ["Customer A"],
    })

    docs = [
        (df_a, "doc_a", "orders.csv", "orders"),
        (df_b, "doc_b", "settlements.csv", "settlements"),
    ]

    engine = PandasReconciliationEngine(amount_tolerance=0.05, fee_tolerance=2.50)
    result = engine.reconcile_documents(docs)

    assert len(result["matches"]) == 1
    m = result["matches"][0]
    assert m["amount_diff"] == 1.25
    assert m["match_category"] == "TOLERANCE_MATCH"


def test_pandas_reconciler_date_window_match():
    """
    Test amount match with a 2-day settlement delay (within 3-day window).
    """
    df_a = pd.DataFrame({
        "record_id": ["SALE-AAA"],
        "amount": [540.00],
        "date": ["2026-08-10"],
        "entity": ["Acme Wholesale"],
    })

    df_b = pd.DataFrame({
        "record_id": ["BNK-BBB"],  # Reference differs completely
        "amount": [540.00],
        "date": ["2026-08-12"],  # 2 days lag
        "entity": ["Acme Wholesale"],
    })

    docs = [
        (df_a, "doc_a", "sales.csv", "sales"),
        (df_b, "doc_b", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    assert len(result["matches"]) == 1
    m = result["matches"][0]
    assert m["match_category"] == "FUZZY_MATCH"
    assert m["days_diff"] == 2


def test_pandas_reconciler_duplicate_detection():
    """
    Test duplicate detection within a source file.
    """
    df_a = pd.DataFrame({
        "record_id": ["TXN-DUP-1", "TXN-DUP-2"],
        "reference": ["INV-DUPLICATE", "INV-DUPLICATE"],
        "amount": [300.00, 300.00],
        "date": ["2026-08-01", "2026-08-01"],
        "entity": ["Test Vendor", "Test Vendor"],
    })

    df_b = pd.DataFrame({
        "record_id": ["BNK-1"],
        "reference": ["INV-DUPLICATE"],
        "amount": [300.00],
        "date": ["2026-08-01"],
        "entity": ["Test Vendor"],
    })

    docs = [
        (df_a, "doc_a", "ledger.csv", "ledger"),
        (df_b, "doc_b", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    assert result["duplicates_count"] > 0
    # Duplicates should be isolated into exceptions
    dup_exc = [e for e in result["exceptions"] if e["reason_code"] == "DUPLICATE_TRANSACTION"]
    assert len(dup_exc) > 0


def test_pandas_reconciler_zero_match_diagnostics():
    """
    Test that when match rate is 0%, clear diagnostics explain the exact failure reason:
    e.g. no overlapping references and dates/amounts incompatible.
    """
    df_a = pd.DataFrame({
        "record_id": ["A-1", "A-2"],
        "amount": [10.00, 20.00],
        "date": ["2026-01-01", "2026-01-02"],
        "entity": ["Alpha Corp", "Beta Corp"],
    })

    df_b = pd.DataFrame({
        "record_id": ["B-1", "B-2"],
        "amount": [5000.00, 6000.00],  # Incompatible amounts
        "date": ["2026-08-01", "2026-08-02"],  # Incompatible dates (7 months apart)
        "entity": ["Gamma Inc", "Delta Inc"],
    })

    docs = [
        (df_a, "doc_a", "file_a.csv", "file_a"),
        (df_b, "doc_b", "file_b.csv", "file_b"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    assert result["match_rate"] == 0.0
    assert result["diagnostics"]["zero_match_diagnostics"] is not None
    assert "0% Match" in result["diagnostics"]["zero_match_diagnostics"]


def test_pandas_reconciler_multi_document_three_files():
    """
    Test reconciliation with 3 uploaded documents:
    1. Primary Ledger (10 records)
    2. Bank Statement (5 records)
    3. Payout Gateway (5 records)
    """
    df_ledger = pd.DataFrame({
        "record_id": [f"REC-{i}" for i in range(10)],
        "amount": [100.0 + i for i in range(10)],
        "date": ["2026-08-01"] * 10,
        "entity": ["Vendor"] * 10,
    })

    df_bank = pd.DataFrame({
        "txn_id": [f"REC-{i}" for i in range(5)],
        "transaction_amount": [100.0 + i for i in range(5)],
        "value_date": ["2026-08-01"] * 5,
        "payee": ["Vendor"] * 5,
    })

    df_payout = pd.DataFrame({
        "payout_id": [f"REC-{i}" for i in range(5, 10)],
        "net_amount": [100.0 + i for i in range(5, 10)],
        "settlement_date": ["2026-08-01"] * 5,
        "merchant": ["Vendor"] * 5,
    })

    docs = [
        (df_ledger, "doc_ledger", "ledger.csv", "ledger"),
        (df_bank, "doc_bank", "bank.csv", "bank"),
        (df_payout, "doc_payout", "payouts.xlsx", "payouts"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    assert result["records_processed"] == 20
    assert len(result["documents_processed"]) == 3
    assert len(result["matches"]) == 10
    assert result["match_rate"] == 100.0


def test_reconciliation_row_order_independence():
    """
    CRITICAL KEY RULE REGRESSION TEST:
    Row number must NEVER be used as a reconciliation key.
    Reconciliation must be purely key-value on canonical_transaction_id.
    
    Transactions:
      row 0 -> TXN_A
      row 1 -> TXN_B
      row 2 -> TXN_C
      
    Settlements:
      row 0..49 -> Other filler transactions
      row 50 -> TXN_C
      row 51 -> TXN_A
      row 52 -> TXN_B
      
    Expected:
      3/3 target transactions matched with exact provenance preserved.
    """
    # Create 3 transactions
    df_txns = pd.DataFrame({
        "transaction_id": ["TXN_A", "TXN_B", "TXN_C"],
        "amount": [1250.00, 3400.50, 750.00],
        "date": ["2026-08-01", "2026-08-02", "2026-08-03"],
        "entity": ["Acme Corp", "Beta LLC", "Gamma Inc"],
    })

    # Create settlements with 50 preceding records then TXN_C, TXN_A, TXN_B
    filler = [
        {"settlement_id": f"SETTLE_OTHER_{i:03d}", "amount": 10.0 + i, "date": "2026-08-01", "entity": "Other"}
        for i in range(50)
    ]
    target_settlements = [
        {"settlement_id": "TXN_C", "amount": 750.00, "date": "2026-08-03", "entity": "Gamma Inc"},     # row 50
        {"settlement_id": "TXN_A", "amount": 1250.00, "date": "2026-08-01", "entity": "Acme Corp"},    # row 51
        {"settlement_id": "TXN_B", "amount": 3400.50, "date": "2026-08-02", "entity": "Beta LLC"},     # row 52
    ]
    df_settlements = pd.DataFrame(filler + target_settlements)

    docs = [
        (df_txns, "doc_txns", "01_transactions.csv", "transactions"),
        (df_settlements, "doc_settlements", "02_settlements.csv", "settlements"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    # 3 target records must all match
    matches_by_canon = {m["canonical_transaction_id"]: m for m in result["matches"]}
    assert "TXN_A" in matches_by_canon
    assert "TXN_B" in matches_by_canon
    assert "TXN_C" in matches_by_canon

    # Verify exact provenance: different row positions must not prevent reconciliation
    match_a = matches_by_canon["TXN_A"]
    assert match_a["transaction_row"] == 0
    assert match_a["settlement_row"] == 51
    assert match_a["matching_strategy"] == "EXACT_TRANSACTION_ID"
    assert match_a["confidence_score"] == 100.0

    match_b = matches_by_canon["TXN_B"]
    assert match_b["transaction_row"] == 1
    assert match_b["settlement_row"] == 52
    assert match_b["matching_strategy"] == "EXACT_TRANSACTION_ID"

    match_c = matches_by_canon["TXN_C"]
    assert match_c["transaction_row"] == 2
    assert match_c["settlement_row"] == 50
    assert match_c["matching_strategy"] == "EXACT_TRANSACTION_ID"


def test_multiple_transactions_per_member_isolation():
    """
    CRITICAL RULE REGRESSION TEST:
    The engine must support one-to-many relationships:
      member_id -> many transaction_id values.
    member_id/entity_id = grouping/context ONLY.
    Never reconcile transactions using only member_id/entity_id.
    
    Member M001:
      TXN_1001 ($500)
      TXN_1002 ($750)
      TXN_1003 ($1200)
      
    Reconciles at transaction level independently.
    """
    df_txns = pd.DataFrame({
        "member_id": ["M001", "M001", "M001", "M002"],
        "transaction_id": ["TXN_1001", "TXN_1002", "TXN_1003", "TXN_2001"],
        "amount": [500.00, 750.00, 1200.00, 300.00],
        "date": ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-01"],
        "entity": ["Member M001", "Member M001", "Member M001", "Member M002"],
    })

    df_settlements = pd.DataFrame({
        "member_id": ["M001", "M001", "M001", "M002"],
        "payment_id": ["TXN_1003", "TXN_1001", "TXN_1002", "TXN_2001"],  # Shuffled order
        "amount": [1200.00, 500.00, 750.00, 300.00],
        "date": ["2026-08-03", "2026-08-01", "2026-08-02", "2026-08-01"],
        "entity": ["Member M001", "Member M001", "Member M001", "Member M002"],
    })

    docs = [
        (df_txns, "doc_txns", "transactions.csv", "transactions"),
        (df_settlements, "doc_settlements", "settlements.csv", "settlements"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    assert result["status"] == "COMPLETED"
    assert len(result["matches"]) == 4
    assert result["match_rate"] == 100.0

    matched_ids = {m["canonical_transaction_id"] for m in result["matches"]}
    assert matched_ids == {"TXN_1001", "TXN_1002", "TXN_1003", "TXN_2001"}

    # Verify each was matched 1-to-1 on its canonical_transaction_id
    for m in result["matches"]:
        assert m["matching_strategy"] == "EXACT_TRANSACTION_ID"
        assert m["confidence_score"] == 100.0


def test_exact_transaction_id_amount_mismatch_never_fuzzy_matches():
    """
    CRITICAL MATCH VALIDATION RULE:
    Finding the same transaction ID is the primary identity match.
    Same transaction ID + amount difference -> AMOUNT_MISMATCH.
    Do NOT automatically fuzzy-match a different transaction ID when an exact ID exists!
    """
    df_txns = pd.DataFrame({
        "transaction_id": ["TXN_002"],
        "amount": [2450.00],
        "date": ["2026-08-01"],
        "entity": ["Acme Corp"],
    })

    df_settlements = pd.DataFrame({
        # Counterpart with same transaction ID but amount difference ($2,000 vs $2,450)
        "transaction_id": ["TXN_002", "TXN_OTHER_999"],
        # TXN_OTHER_999 has amount 2450.00 on the same date!
        "amount": [2000.00, 2450.00],
        "date": ["2026-08-01", "2026-08-01"],
        "entity": ["Acme Corp", "Acme Corp"],
    })

    docs = [
        (df_txns, "doc_txns", "transactions.csv", "transactions"),
        (df_settlements, "doc_settlements", "settlements.csv", "settlements"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    # Must NOT have matched TXN_002 to TXN_OTHER_999 via fuzzy matching!
    assert len(result["matches"]) == 0

    # TXN_002 must be classified as AMOUNT_MISMATCH
    exc_list = result["exceptions"]
    mismatch_exc = [e for e in exc_list if e.get("reason_code") == "AMOUNT_MISMATCH"]
    assert len(mismatch_exc) >= 1
    assert mismatch_exc[0]["canonical_transaction_id"] == "TXN_002"
    assert mismatch_exc[0]["amount_discrepancy"] == 450.00


def test_ambiguous_candidate_conflict_in_fallback():
    """
    CRITICAL FALLBACK RULE:
    If multiple candidates remain in fallback matching:
    Flag as AMBIGUOUS_CANDIDATE_CONFLICT.
    Do not arbitrarily choose matches[0].
    """
    # Transaction without reference ID (relies on amount+date fallback)
    df_txns = pd.DataFrame({
        "order_num": ["ORD_A"],
        "amount": [150.00],
        "date": ["2026-08-10"],
        "client": ["Generic Client"],
    })

    # Bank has TWO identical $150 transactions on the same date without reference
    df_bank = pd.DataFrame({
        "bank_line": ["LINE_1", "LINE_2"],
        "amount": [150.00, 150.00],
        "date": ["2026-08-10", "2026-08-10"],
        "client": ["Generic Client", "Generic Client"],
    })

    docs = [
        (df_txns, "doc_txns", "orders.csv", "orders"),
        (df_bank, "doc_bank", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)

    # Neither should be arbitrarily matched!
    assert len(result["matches"]) == 0

    # Ambiguity must be flagged in exceptions
    ambiguous_exc = [e for e in result["exceptions"] if e.get("reason_code") == "AMBIGUOUS_CANDIDATE_CONFLICT"]
    assert len(ambiguous_exc) >= 1
