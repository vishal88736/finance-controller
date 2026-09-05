"""
Tests for deterministic structured invoice extraction
(model/ingestion/invoice_extraction.py).
"""
import pytest

from model.ingestion.invoice_extraction import extract_invoice, InvoiceExtractionSchema


def test_extract_invoice_fields_and_metadata():
    raw = {
        "vendor_name": "Alpha Logistics",
        "invoice_number": "INV-1001",
        "invoice_date": "2026-08-10",
        "purchase_order_number": "PO-55",
        "payment_terms": "Net 30",
        "currency": "USD",
        "subtotal": 1000.0,
        "tax_amount": 180.0,
        "total": 1180.0,
        "line_items": [
            {"description": "Freight", "quantity": 2, "unit_price": 500.0, "amount": 1000.0},
        ],
    }
    schema, meta = extract_invoice(raw)
    assert isinstance(schema, InvoiceExtractionSchema)
    assert schema.vendor_name == "Alpha Logistics"
    assert schema.invoice_number == "INV-1001"
    assert schema.subtotal == 1000.0
    assert schema.tax_amount == 180.0
    assert schema.total == 1180.0
    assert len(schema.line_items) == 1
    assert schema.line_items[0].description == "Freight"
    assert meta["vendor_name"]["present"] is True
    assert meta["vendor_name"]["confidence"] == 1.0
    assert meta["vendor_name"]["source_key"] == "vendor_name"


def test_extract_invoice_missing_fields_honest():
    schema, meta = extract_invoice({"invoice_number": "INV-9"})
    assert schema.vendor_name is None
    assert schema.total is None
    assert schema.line_items is None
    assert meta["vendor_name"]["present"] is False
    assert meta["vendor_name"]["confidence"] is None