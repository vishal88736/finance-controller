"""
Unit tests for deterministic Schema Inspector and Semantic Column Mapper.
Validates automatic column mapping across various naming conventions:
    - txn_id / transaction_id / reference
    - amount / transaction_amount / debit_amount
    - date / transaction_date / value_date
    - description / narration / memo
"""

import pytest
import pandas as pd
from model.reconciliation.schema_mapper import schema_mapper, SchemaMapper


def test_schema_mapper_standard_columns():
    df = pd.DataFrame({
        "record_id": ["REC-1", "REC-2"],
        "date": ["2026-08-01", "2026-08-02"],
        "amount": [150.00, 250.50],
        "currency": ["USD", "USD"],
        "entity": ["Acme Corp", "Beta LLC"],
        "description": ["Invoice payment", "Software sub"],
    })

    schema = schema_mapper.inspect_and_map_dataframe(df, "doc_1", "ledger.csv", "ledger")

    assert schema.is_valid is True
    assert schema.mapped_columns["transaction_id"] == "record_id"
    assert schema.mapped_columns["date"] == "date"
    assert schema.mapped_columns["amount"] == "amount"
    assert schema.mapped_columns["currency"] == "currency"
    assert schema.mapped_columns["entity"] == "entity"
    assert schema.mapped_columns["description"] == "description"


def test_schema_mapper_alternative_financial_headers():
    """
    Test mapping alternative bank / payment gateway headers:
    txn_id, transaction_amount, value_date, narration, payee
    """
    df = pd.DataFrame({
        "txn_id": ["TXN-901", "TXN-902"],
        "value_date": ["2026-08-10", "2026-08-11"],
        "transaction_amount": [1200.75, 450.00],
        "payee": ["Stripe Inc", "Cloudflare"],
        "narration": ["Settlement transfer", "DNS bill"],
    })

    schema = schema_mapper.inspect_and_map_dataframe(df, "doc_2", "bank_statement.csv", "bank")

    assert schema.is_valid is True
    assert schema.mapped_columns["transaction_id"] == "txn_id"
    assert schema.mapped_columns["date"] == "value_date"
    assert schema.mapped_columns["amount"] == "transaction_amount"
    assert schema.mapped_columns["entity"] == "payee"
    assert schema.mapped_columns["description"] == "narration"


def test_schema_mapper_banking_debit_credit_format():
    """
    Test mapping banking debit headers and UTR references.
    """
    df = pd.DataFrame({
        "utr": ["UTR8829104", "UTR8829105"],
        "posting_date": ["2026-08-15", "2026-08-16"],
        "debit_amount": [890.00, 1500.00],
        "memo": ["ACH transfer", "Vendor payout"],
    })

    schema = schema_mapper.inspect_and_map_dataframe(df, "doc_3", "payouts.xlsx", "payouts")

    assert schema.is_valid is True
    assert schema.mapped_columns["reference_id"] == "utr"
    assert schema.mapped_columns["date"] == "posting_date"
    assert schema.mapped_columns["amount"] == "debit_amount"
    assert schema.mapped_columns["description"] == "memo"


def test_schema_mapper_content_fallback():
    """
    When headers are non-standard (e.g. col_a, col_b), content-based heuristics identify date and numeric amount.
    """
    df = pd.DataFrame({
        "col_num": ["REF101", "REF102"],
        "col_day": ["2026-08-01", "2026-08-02"],
        "col_money": [99.50, 199.00],
    })

    schema = schema_mapper.inspect_and_map_dataframe(df, "doc_4", "legacy_export.csv", "legacy")

    assert schema.is_valid is True
    assert schema.mapped_columns["amount"] == "col_money"
    assert schema.mapped_columns["date"] == "col_day"


def test_schema_mapper_missing_required_columns():
    """
    If a document lacks any amount column, it is flagged as invalid with diagnostics.
    """
    df = pd.DataFrame({
        "some_id": ["1", "2"],
        "notes": ["No financial value here", "Just comments"],
    })

    schema = schema_mapper.inspect_and_map_dataframe(df, "doc_invalid", "notes.csv", "notes")

    assert schema.is_valid is False
    assert "amount" in schema.missing_required_fields


def test_schema_mapper_inspect_and_map_all():
    """Test batch inspection across 3 distinct document schemas."""
    df1 = pd.DataFrame({"record_id": ["A1"], "amount": [10.0], "date": ["2026-08-01"]})
    df2 = pd.DataFrame({"txn_id": ["B1"], "transaction_amount": [10.0], "value_date": ["2026-08-01"]})
    df3 = pd.DataFrame({"invoice": ["C1"], "net_amount": [10.0], "invoice_date": ["2026-08-01"]})

    docs = [
        (df1, "doc_1", "ledger.csv", "ledger"),
        (df2, "doc_2", "bank.csv", "bank"),
        (df3, "doc_3", "invoices.csv", "invoices"),
    ]

    result = schema_mapper.inspect_and_map_all(docs)
    assert result.documents_inspected == 3
    assert result.all_valid is True
    assert result.summary["valid_documents"] == 3
    assert result.summary["invalid_documents"] == 0
