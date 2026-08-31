"""
Record normalization module.
Standardizes dates, amounts, currencies, identifiers, and entity names.
Uses Decimal for all monetary values.
Deterministic record ID generation without memory-pointer dependencies.
"""

import re
import math
import json
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from ..verification.normalizers import (
    normalize_amount,
    normalize_date,
    normalize_currency,
    normalize_entity_name,
    normalize_transaction_id,
    _is_nan,
)


class NormalizedRecord(BaseModel):
    record_id: str
    source: str
    raw_reference_id: Optional[str] = None
    clean_reference_id: Optional[str] = None
    raw_date: Optional[str] = None
    iso_date: Optional[str] = None  # YYYY-MM-DD
    amount: float  # Kept as float for Pydantic/JSON compat; internal calcs use Decimal
    amount_decimal: Optional[str] = None  # String representation of Decimal for precision
    currency: str = "USD"
    raw_entity: Optional[str] = None
    clean_entity: Optional[str] = None
    raw_description: Optional[str] = None
    clean_description: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    @property
    def amount_as_decimal(self) -> Decimal:
        """Get the amount as Decimal for financial calculations."""
        if self.amount_decimal:
            return Decimal(self.amount_decimal)
        return Decimal(str(self.amount))


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'[\s\-_/\\#]+', ' ', str(text)).strip().lower()
    return cleaned


def extract_reference_token(ref: Optional[str]) -> str:
    """Extract core alphanumeric identifier tokens (e.g. INV-2026-2005 -> 2005 or 20262005)."""
    return normalize_transaction_id(ref)


def parse_iso_date(date_val: Any) -> Optional[str]:
    return normalize_date(date_val)


def parse_amount(amount_val: Any) -> float:
    """Parse amount and return as float (for Pydantic compat). Use amount_decimal for precision."""
    dec = normalize_amount(amount_val)
    return float(dec)


def parse_amount_decimal(amount_val: Any) -> str:
    """Parse amount and return as Decimal string for precision storage."""
    dec = normalize_amount(amount_val)
    return str(dec)


def pd_is_nan(val: Any) -> bool:
    return _is_nan(val)


def normalize_single_record(raw: Dict[str, Any], source_label: str) -> NormalizedRecord:
    # Deterministic record_id identification
    raw_id = (
        raw.get("record_id")
        or raw.get("id")
        or raw.get("txn_id")
        or raw.get("payout_id")
        or raw.get("transaction_id")
        or raw.get("invoice_id")
        or raw.get("settlement_id")
    )
    if raw_id:
        rec_id = str(raw_id)
    else:
        # Deterministic hash of row contents (no memory pointer dependencies)
        row_sig = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]
        rec_id = f"REC-{row_sig}"

    raw_ref = (
        raw.get("reference_id")
        or raw.get("reference")
        or raw.get("order_ref")
        or raw.get("ref_no")
        or raw.get("invoice")
        or raw.get("utr")
    )
    clean_ref = extract_reference_token(str(raw_ref)) if raw_ref else None

    raw_date = (
        raw.get("date")
        or raw.get("txn_date")
        or raw.get("payout_date")
        or raw.get("created_at")
        or raw.get("posting_date")
        or raw.get("settlement_date")
        or raw.get("invoice_date")
    )
    iso_date = parse_iso_date(raw_date)

    raw_amt = (
        raw.get("amount")
        or raw.get("net_amount")
        or raw.get("gross_amount")
        or raw.get("value")
        or raw.get("total")
        or raw.get("paid_amount")
    )
    amount = parse_amount(raw_amt)
    amount_decimal = parse_amount_decimal(raw_amt)

    currency_raw = raw.get("currency") or raw.get("curr") or "USD"
    currency = normalize_currency(currency_raw)

    raw_ent = (
        raw.get("entity")
        or raw.get("vendor")
        or raw.get("merchant")
        or raw.get("merchant_entity")
        or raw.get("counterparty")
        or raw.get("customer")
        or raw.get("client")
    )
    clean_ent = normalize_entity_name(raw_ent) if raw_ent else ""

    raw_desc = (
        raw.get("description")
        or raw.get("details")
        or raw.get("narration")
        or raw.get("notes")
        or raw.get("memo")
        or raw.get("remarks")
    )
    clean_desc = clean_text(str(raw_desc)) if raw_desc else ""

    return NormalizedRecord(
        record_id=rec_id,
        source=source_label,
        raw_reference_id=str(raw_ref) if raw_ref else None,
        clean_reference_id=clean_ref,
        raw_date=str(raw_date) if raw_date else None,
        iso_date=iso_date,
        amount=amount,
        amount_decimal=amount_decimal,
        currency=currency,
        raw_entity=str(raw_ent) if raw_ent else None,
        clean_entity=clean_ent,
        raw_description=str(raw_desc) if raw_desc else None,
        clean_description=clean_desc,
        raw_data=raw
    )
