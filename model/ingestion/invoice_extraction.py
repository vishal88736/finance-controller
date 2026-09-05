"""
Deterministic structured invoice extraction.

Adopts the reference pattern from `template-workflow-extract-reconcile-invoice`
(a Pydantic `InvoiceExtractionSchema` with per-field extraction metadata and
file-hash deduplication), but keeps extraction fully deterministic and local:
values are mapped from normalized record fields — never guessed by an LLM.

Acts as a typed, auditable view over normalized DocumentRecord raw data. The
LLM/VLM path (hosted structured extraction) is deliberately NOT included here:
it transmits document content externally and requires explicit approval.

File-hash deduplication is already owned by `model/ingestion/registry.py`
(SHA-256 bytes + canonical dataset fingerprint); callers reusing this module
should pair `extract_invoice` with a file hash for idempotent, dedupable store.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class InvoiceLineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class InvoiceExtractionSchema(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    purchase_order_number: Optional[str] = None
    payment_terms: Optional[str] = None
    currency: Optional[str] = "USD"
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total: Optional[float] = None
    line_items: Optional[List[InvoiceLineItem]] = None


# Ordered candidate aliases per semantic field (first present wins).
_FIELD_ALIASES: Dict[str, List[str]] = {
    "vendor_name": ["vendor_name", "vendor", "merchant", "supplier", "entity", "name"],
    "invoice_number": ["invoice_number", "invoice_id", "inv_no", "invoice_no", "bill_no", "invoice"],
    "invoice_date": ["invoice_date", "bill_date", "date"],
    "purchase_order_number": ["purchase_order_number", "po_number", "po"],
    "payment_terms": ["payment_terms", "terms"],
    "currency": ["currency", "curr", "ccy"],
    "subtotal": ["subtotal", "base_amount", "taxable_amount", "net_amount"],
    "tax_amount": ["tax_amount", "tax", "gst", "vat", "total_tax"],
    "total": ["total", "total_amount", "invoice_total", "grand_total"],
}


def _round_dec(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_float(value: Any) -> Optional[float]:
    """Deterministic numeric coercion; never fabricates a number for missing/garbage."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    s = str(value).strip().lower()
    if s in ("", "nan", "none", "null", "inf", "-inf"):
        return None
    try:
        return float(_round_dec(Decimal(s)))
    except Exception:
        return None


def _pick(raw: Dict[str, Any], candidates: List[str]) -> Tuple[Optional[Any], Optional[str]]:
    for key in candidates:
        if key in raw and raw[key] is not None:
            return raw[key], key
    return None, None


def extract_invoice(raw_data: Dict[str, Any]) -> Tuple[InvoiceExtractionSchema, Dict[str, Any]]:
    """
    Extract a typed invoice view from a normalized record's raw data.

    Returns (schema, field_metadata). `field_metadata` records, per field, the
    source key and a confidence (1.0 when deterministically present, None when
    absent) so downstream consumers can see exactly where each value came from.
    """
    raw = raw_data or {}
    field_metadata: Dict[str, Any] = {}
    values: Dict[str, Any] = {}

    for field, aliases in _FIELD_ALIASES.items():
        value, source_key = _pick(raw, aliases)
        field_metadata[field] = {
            "present": value is not None,
            "source_key": source_key,
            "confidence": 1.0 if value is not None else None,
        }
        values[field] = value

    # line items: require a list/tuple, else None (never coerce a scalar).
    line_items_raw = raw.get("line_items") or raw.get("items")
    line_items = None
    if isinstance(line_items_raw, (list, tuple)):
        parsed_items: List[InvoiceLineItem] = []
        for item in line_items_raw:
            if isinstance(item, dict):
                parsed_items.append(InvoiceLineItem(
                    description=item.get("description"),
                    quantity=_to_float(item.get("quantity")),
                    unit_price=_to_float(item.get("unit_price") or item.get("unit_price_amount")),
                    amount=_to_float(item.get("amount") or item.get("line_amount")),
                ))
        line_items = parsed_items if parsed_items else None

    schema = InvoiceExtractionSchema(
        vendor_name=values.get("vendor_name"),
        invoice_number=values.get("invoice_number"),
        invoice_date=values.get("invoice_date"),
        purchase_order_number=values.get("purchase_order_number"),
        payment_terms=values.get("payment_terms"),
        currency=values.get("currency") or "USD",
        subtotal=_to_float(values.get("subtotal")),
        tax_amount=_to_float(values.get("tax_amount")),
        total=_to_float(values.get("total")),
        line_items=line_items,
    )

    return schema, field_metadata