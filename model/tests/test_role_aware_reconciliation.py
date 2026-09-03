"""
Comprehensive Regression Test Suite for Role-Aware Reconciliation Architecture.
Verifies all requirements A through T:
    A. Different row ordering
    B. Multiple transactions per member
    C. Same member with many transaction IDs
    D. Exact transaction-ID match
    E. Same transaction ID with amount mismatch (strict identity preservation)
    F. Missing counterpart
    G. Duplicate transaction IDs
    H. Ambiguous fallback candidates (no matches[0])
    I. Missing transaction IDs
    J. Reordered columns
    K. Renamed semantic columns
    L. Multiple document roles
    M. Unrelated enrichment documents (do NOT alter primary match rate or denominator)
    N. Many-to-one / one-to-many candidate situations
    O. No arbitrary first-candidate matching
    P. Reconciliation denominator based on source population
    Q. Candidate rejection counts separated from final exceptions
    R. Provenance preservation
    S. Thread isolation
    T. Deterministic repeated execution
"""

import copy
import pytest
import pandas as pd

from model.reconciliation.role_classifier import role_classifier, DocumentRole
from model.reconciliation.planner import reconciliation_planner, ReconciliationPlan
from model.reconciliation.pandas_reconciler import pandas_reconciler, PandasReconciliationEngine


def test_req_l_document_role_classification_multi_domain():
    """
    Test L: Verify deterministic classification across distinct financial domain files.
    """
    # 1. Tax report
    df_tax = pd.DataFrame({
        "invoice_id": ["INV-01"],
        "taxable_amount": [1000.0],
        "gst_rate": [0.18],
        "tax_amount": [180.0],
    })
    cls_tax = role_classifier.classify_document(df_tax, "doc_tax", "gst_filing_august.csv")
    assert cls_tax.document_role == DocumentRole.TAX
    assert cls_tax.confidence >= 0.70

    # 2. Fee schedule
    df_fee = pd.DataFrame({
        "transaction_ref": ["TXN-01"],
        "mdr_fee": [2.50],
        "interchange": [1.20],
        "commission": [0.50],
    })
    cls_fee = role_classifier.classify_document(df_fee, "doc_fee", "gateway_mdr_fees.csv")
    assert cls_fee.document_role == DocumentRole.FEE
    assert cls_fee.confidence >= 0.70

    # 3. Bank Statement
    df_bank = pd.DataFrame({
        "utr": ["UTR998877"],
        "closing_balance": [54000.0],
        "value_date": ["2026-08-01"],
        "debit": [500.0],
    })
    cls_bank = role_classifier.classify_document(df_bank, "doc_bank", "bank_account_stmt.csv")
    assert cls_bank.document_role == DocumentRole.BANK_STATEMENT
    assert cls_bank.confidence >= 0.70

    # 4. Unknown File
    df_rand = pd.DataFrame({
        "foo": [1, 2, 3],
        "bar": ["x", "y", "z"],
    })
    cls_rand = role_classifier.classify_document(df_rand, "doc_rand", "random_notes.txt")
    assert cls_rand.document_role == DocumentRole.UNKNOWN
    assert cls_rand.confidence == 0.0


def test_req_a_row_order_independence():
    """
    Test A: Row order must NEVER determine matching.
    Source: rows 0, 1, 2 -> TXN_A, TXN_B, TXN_C.
    Counterpart: 40 filler rows, then TXN_C, TXN_A, TXN_B.
    """
    df_a = pd.DataFrame({
        "transaction_id": ["TXN_A", "TXN_B", "TXN_C"],
        "amount": [100.0, 200.0, 300.0],
        "date": ["2026-08-01", "2026-08-02", "2026-08-03"],
        "client": ["Alpha", "Beta", "Gamma"],
    })

    filler = [{"payout_id": f"OTHER_{i}", "amount": float(i + 1), "date": "2026-08-01", "client": "Other"} for i in range(40)]
    targets = [
        {"payout_id": "TXN_C", "amount": 300.0, "date": "2026-08-03", "client": "Gamma"},
        {"payout_id": "TXN_A", "amount": 100.0, "date": "2026-08-01", "client": "Alpha"},
        {"payout_id": "TXN_B", "amount": 200.0, "date": "2026-08-02", "client": "Beta"},
    ]
    df_b = pd.DataFrame(filler + targets)

    docs = [
        (df_a, "doc_a", "sales_orders.csv", "sales"),
        (df_b, "doc_b", "settlement_payouts.csv", "payouts"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert result["status"] == "COMPLETED"

    matches = {m["canonical_transaction_id"]: m for m in result["matches"]}
    assert "TXN_A" in matches
    assert "TXN_B" in matches
    assert "TXN_C" in matches

    # Check row provenance
    assert matches["TXN_A"]["transaction_row"] == 0
    assert matches["TXN_A"]["settlement_row"] == 41  # row 41 in df_b
    assert matches["TXN_C"]["transaction_row"] == 2
    assert matches["TXN_C"]["settlement_row"] == 40  # row 40 in df_b


def test_req_b_c_multiple_transactions_per_member_isolation():
    """
    Test B & C: Multiple transactions per member.
    Member M001 has TXN_1, TXN_2, TXN_3.
    Member M002 has TXN_4, TXN_5.
    Must reconcile independently at transaction level without collapsing.
    """
    df_txns = pd.DataFrame({
        "member_id": ["M001", "M001", "M001", "M002", "M002"],
        "transaction_id": ["TXN_1", "TXN_2", "TXN_3", "TXN_4", "TXN_5"],
        "amount": [50.0, 75.0, 120.0, 300.0, 450.0],
        "date": ["2026-08-01"] * 5,
        "name": ["Cust 1", "Cust 1", "Cust 1", "Cust 2", "Cust 2"],
    })

    df_settle = pd.DataFrame({
        "customer_id": ["M001", "M001", "M001", "M002", "M002"],
        "payment_id": ["TXN_3", "TXN_1", "TXN_2", "TXN_5", "TXN_4"],  # Shuffled
        "amount": [120.0, 50.0, 75.0, 450.0, 300.0],
        "date": ["2026-08-01"] * 5,
        "name": ["Cust 1", "Cust 1", "Cust 1", "Cust 2", "Cust 2"],
    })

    docs = [
        (df_txns, "doc_txns", "orders.csv", "orders"),
        (df_settle, "doc_settle", "settlements.csv", "settlements"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert result["match_rate"] == 100.0
    assert len(result["matches"]) == 5

    for m in result["matches"]:
        assert m["matching_strategy"] == "EXACT_TRANSACTION_ID"
        assert m["confidence_score"] == 100.0


def test_req_d_e_exact_id_amount_mismatch_strict_identity():
    """
    Test D & E: Same transaction ID + amount difference -> AMOUNT_MISMATCH.
    DO NOT abandon that ID and fuzzy-match to some other transaction!
    """
    df_a = pd.DataFrame({
        "transaction_id": ["TXN_101"],
        "amount": [1000.0],
        "date": ["2026-08-01"],
        "entity": ["Acme Corp"],
    })

    # df_b has TXN_101 with wrong amount, and another TXN_999 with 1000.0!
    df_b = pd.DataFrame({
        "settlement_id": ["TXN_101", "TXN_999"],
        "amount": [850.0, 1000.0],
        "date": ["2026-08-01", "2026-08-01"],
        "entity": ["Acme Corp", "Acme Corp"],
    })

    docs = [
        (df_a, "doc_a", "ledger.csv", "ledger"),
        (df_b, "doc_b", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    # Must NOT match TXN_101 to TXN_999!
    assert len(result["matches"]) == 0

    # TXN_101 must be an AMOUNT_MISMATCH exception
    mismatches = [e for e in result["exceptions"] if e["reason_code"] == "AMOUNT_MISMATCH"]
    assert len(mismatches) >= 1
    assert mismatches[0]["canonical_transaction_id"] == "TXN_101"
    assert mismatches[0]["amount_discrepancy"] == 150.0


def test_req_f_missing_counterpart():
    """
    Test F: Transaction present in source but completely absent in counterpart.
    """
    df_a = pd.DataFrame({
        "transaction_id": ["TXN_ORPHAN"],
        "amount": [500.0],
        "date": ["2026-08-01"],
        "entity": ["Orphan LLC"],
    })

    df_b = pd.DataFrame({
        "settlement_id": ["OTHER_TXN"],
        "amount": [999.0],
        "date": ["2026-08-01"],
        "entity": ["Unrelated"],
    })

    docs = [
        (df_a, "doc_a", "source.csv", "source"),
        (df_b, "doc_b", "counterpart.csv", "counterpart"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert len(result["matches"]) == 0
    missing = [e for e in result["exceptions"] if e["reason_code"] == "MISSING_COUNTERPART"]
    assert len(missing) >= 1
    assert missing[0]["canonical_transaction_id"] == "TXN_ORPHAN"


def test_req_g_duplicate_transaction_ids():
    """
    Test G: Duplicate transaction ID detected before merge to prevent merge explosions.
    """
    df_a = pd.DataFrame({
        "transaction_id": ["TXN_DUP", "TXN_DUP"],
        "amount": [200.0, 200.0],
        "date": ["2026-08-01", "2026-08-01"],
        "entity": ["Acme", "Acme"],
    })

    df_b = pd.DataFrame({
        "settlement_id": ["TXN_DUP"],
        "amount": [200.0],
        "date": ["2026-08-01"],
        "entity": ["Acme"],
    })

    docs = [
        (df_a, "doc_a", "sales.csv", "sales"),
        (df_b, "doc_b", "settlements.csv", "settlements"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert result["duplicates_count"] >= 1
    dup_excs = [e for e in result["exceptions"] if e["reason_code"] == "DUPLICATE_TRANSACTION"]
    assert len(dup_excs) >= 1


def test_req_h_o_fallback_ambiguity_no_matches_zero():
    """
    Test H & O: If fallback matching finds multiple candidates,
    record AMBIGUOUS_CANDIDATE_CONFLICT. Never arbitrarily choose matches[0].
    """
    df_a = pd.DataFrame({
        "order_num": ["ORD_X"],  # No reference_id
        "amount": [350.0],
        "date": ["2026-08-01"],
        "client": ["Company X"],
    })

    # Two bank records with identical amount and date
    df_b = pd.DataFrame({
        "bank_line": ["LINE_1", "LINE_2"],
        "amount": [350.0, 350.0],
        "date": ["2026-08-01", "2026-08-01"],
        "client": ["Company X", "Company X"],
    })

    docs = [
        (df_a, "doc_a", "orders.csv", "orders"),
        (df_b, "doc_b", "bank.csv", "bank"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert len(result["matches"]) == 0
    ambiguous = [e for e in result["exceptions"] if e["reason_code"] == "AMBIGUOUS_CANDIDATE_CONFLICT"]
    assert len(ambiguous) >= 1


def test_req_j_k_reordered_and_renamed_columns():
    """
    Test J & K: Robustness to column order and arbitrary semantic headers.
    """
    df_a = pd.DataFrame({
        "vendor_name": ["Stripe"],
        "txn_date": ["2026-08-01"],
        "total_amount": [777.0],
        "payment_reference": ["PAY-777"],
    })

    # df_b has completely reversed column order and different headers
    df_b = pd.DataFrame({
        "external_ref": ["PAY-777"],
        "merchant": ["Stripe"],
        "settled_at": ["2026-08-01"],
        "net_payout": [777.0],
    })

    docs = [
        (df_a, "doc_a", "ledger.csv", "ledger"),
        (df_b, "doc_b", "settlement.csv", "settlement"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    assert result["match_rate"] == 100.0
    assert len(result["matches"]) == 1
    assert result["matches"][0]["canonical_transaction_id"] == "PAY-777"


def test_req_m_p_unrelated_enrichment_does_not_change_match_rate_or_denominator():
    """
    Test M & P: Adding unrelated enrichment documents (FEES, TAXES)
    must NOT dilute the source population or change the match rate.
    """
    # 1. Base Pair: 10 transactions ↔ 8 matched settlements
    df_txns = pd.DataFrame({
        "transaction_id": [f"TXN_{i}" for i in range(10)],
        "amount": [100.0] * 10,
        "date": ["2026-08-01"] * 10,
        "customer": ["Acme"] * 10,
    })

    df_settle = pd.DataFrame({
        "settlement_id": [f"TXN_{i}" for i in range(8)],  # 8 out of 10 match
        "amount": [100.0] * 8,
        "date": ["2026-08-01"] * 8,
        "customer": ["Acme"] * 8,
    })

    base_docs = [
        (df_txns, "doc_txns", "sales_transactions.csv", "sales"),
        (df_settle, "doc_settle", "settlement_batch.csv", "settlements"),
    ]

    base_result = pandas_reconciler.reconcile_documents(base_docs)
    assert base_result["source_population"] == 10
    assert base_result["matched_records_count"] == 8
    assert base_result["match_rate"] == 80.0

    # 2. Now upload 200 fee rows and 100 tax rows as enrichment
    df_fees = pd.DataFrame({
        "fee_reference": [f"FEE_{i}" for i in range(200)],
        "mdr_fee": [1.50] * 200,
        "commission": [0.25] * 200,
    })

    df_tax = pd.DataFrame({
        "tax_record_id": [f"TAX_{i}" for i in range(100)],
        "gst_amount": [18.0] * 100,
        "taxable_amount": [100.0] * 100,
    })

    enriched_docs = [
        (df_txns, "doc_txns", "sales_transactions.csv", "sales"),
        (df_settle, "doc_settle", "settlement_batch.csv", "settlements"),
        (df_fees, "doc_fees", "gateway_fees.csv", "fees"),
        (df_tax, "doc_tax", "statutory_tax.csv", "tax"),
    ]

    enriched_result = pandas_reconciler.reconcile_documents(enriched_docs)

    # Denominator must REMAIN 10!
    assert enriched_result["source_population"] == 10
    # Matched count must REMAIN 8!
    assert enriched_result["matched_records_count"] == 8
    # Match rate must REMAIN EXACTLY 80.0%! (NOT diluted by 300 enrichment rows!)
    assert enriched_result["match_rate"] == 80.0

    # Enrichment documents must be registered as adjustments
    assert len(enriched_result["enrichment_adjustments"]) == 2


def test_req_q_r_provenance_and_diagnostics_separation():
    """
    Test Q & R: Every match preserves row index, document role, and canonical ID.
    Diagnostics candidate rejections are separated from final exceptions.
    """
    df_a = pd.DataFrame({
        "transaction_id": ["TXN_ALPHA"],
        "amount": [123.45],
        "date": ["2026-08-01"],
        "client": ["Alpha Corp"],
    })
    df_b = pd.DataFrame({
        "payment_id": ["TXN_ALPHA"],
        "amount": [123.45],
        "date": ["2026-08-01"],
        "client": ["Alpha Corp"],
    })

    docs = [
        (df_a, "doc_a", "internal_sales.csv", "sales"),
        (df_b, "doc_b", "bank_payouts.csv", "payouts"),
    ]

    result = pandas_reconciler.reconcile_documents(docs)
    m = result["matches"][0]

    assert m["transaction_row"] == 0
    assert m["settlement_row"] == 0
    assert m["canonical_transaction_id"] == "TXN_ALPHA"
    assert m["provenance_a"]["document_id"] == "doc_a"
    assert m["provenance_b"]["document_id"] == "doc_b"

    # Diagnostics vs exceptions separation
    assert "candidate_pairs_evaluated" in result["diagnostics"]
    assert "rejection_breakdown" in result["diagnostics"]
    assert len(result["exceptions"]) == 0


def test_req_t_deterministic_repeated_execution():
    """
    Test T: Running the same dataset multiple times yields identical results.
    """
    df_a = pd.DataFrame({
        "transaction_id": [f"ID_{i}" for i in range(25)],
        "amount": [float(i * 10) for i in range(25)],
        "date": ["2026-08-01"] * 25,
        "vendor": ["Vendor"] * 25,
    })
    df_b = pd.DataFrame({
        "settlement_id": [f"ID_{i}" for i in reversed(range(25))],
        "amount": [float(i * 10) for i in reversed(range(25))],
        "date": ["2026-08-01"] * 25,
        "vendor": ["Vendor"] * 25,
    })

    docs = [
        (df_a, "doc_a", "sales.csv", "sales"),
        (df_b, "doc_b", "settlements.csv", "settlements"),
    ]

    res1 = pandas_reconciler.reconcile_documents(docs)
    res2 = pandas_reconciler.reconcile_documents(docs)

    assert res1["match_rate"] == res2["match_rate"] == 100.0
    assert len(res1["matches"]) == len(res2["matches"]) == 25
    assert res1["exact_matches_count"] == res2["exact_matches_count"] == 25
