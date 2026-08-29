"""
Record normalization module.
Standardizes dates, amounts, currencies, identifiers, and entity names.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class NormalizedRecord(BaseModel):
    record_id: str
    source: str
    raw_reference_id: Optional[str] = None
    clean_reference_id: Optional[str] = None
    raw_date: Optional[str] = None
    iso_date: Optional[str] = None  # YYYY-MM-DD
    amount: float
    currency: str = "USD"
    raw_entity: Optional[str] = None
    clean_entity: Optional[str] = None
    raw_description: Optional[str] = None
    clean_description: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)

def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    # Strip whitespace, lower case, replace multiple spaces/punctuations
    cleaned = re.sub(r'[\s\-_/\\#]+', ' ', str(text)).strip().lower()
    return cleaned

def extract_reference_token(ref: Optional[str]) -> str:
    """Extract core alphanumeric identifier tokens (e.g. INV-2026-2005 -> 2005 or 20262005)."""
    if not ref:
        return ""
    cleaned = str(ref).upper().strip()
    # Remove common prefix noise like REF#, INV-, TXN-, AUTO, etc.
    cleaned = re.sub(r'^(INV|REF|TXN|PAYOUT|ORD|ORDER|SETTLE)[\-_#/:]*', '', cleaned)
    cleaned = re.sub(r'[\-_#/:]*(AUTO|MANUAL|CLR)$', '', cleaned)
    # Extract numbers or remaining core string
    nums = re.findall(r'\d+', cleaned)
    if nums:
        return "".join(nums)
    return cleaned.strip()

def parse_iso_date(date_val: Any) -> Optional[str]:
    if not date_val or pd_is_nan(date_val):
        return None
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y-%m-%d")
    
    date_str = str(date_val).strip()
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%d %b %Y"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Fallback regex extraction of YYYY-MM-DD
    match = re.search(r'\b(20\d\d)[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None

def parse_amount(amount_val: Any) -> float:
    if amount_val is None or pd_is_nan(amount_val):
        return 0.0
    if isinstance(amount_val, (int, float)):
        return round(float(amount_val), 2)
    # Clean currency symbols and commas e.g. "$1,250.50 USD"
    cleaned = re.sub(r'[^\d.\-+]', '', str(amount_val))
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0

def pd_is_nan(val: Any) -> bool:
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return True
    except Exception:
        pass
    return False

def normalize_single_record(raw: Dict[str, Any], source_label: str) -> NormalizedRecord:
    # Identify record_id
    rec_id = str(raw.get("record_id") or raw.get("id") or raw.get("txn_id") or raw.get("payout_id") or raw.get("transaction_id") or f"REC-{id(raw)}")
    
    raw_ref = raw.get("reference_id") or raw.get("reference") or raw.get("order_ref") or raw.get("ref_no") or raw.get("invoice")
    clean_ref = extract_reference_token(str(raw_ref)) if raw_ref else None
    
    raw_date = raw.get("date") or raw.get("txn_date") or raw.get("payout_date") or raw.get("created_at") or raw.get("posting_date")
    iso_date = parse_iso_date(raw_date)
    
    raw_amt = raw.get("amount") or raw.get("net_amount") or raw.get("gross_amount") or raw.get("value") or raw.get("total")
    amount = parse_amount(raw_amt)
    
    currency = str(raw.get("currency") or raw.get("curr") or "USD").upper().strip()
    
    raw_ent = raw.get("entity") or raw.get("vendor") or raw.get("merchant") or raw.get("merchant_entity") or raw.get("counterparty") or raw.get("customer")
    clean_ent = clean_text(str(raw_ent)) if raw_ent else ""
    
    raw_desc = raw.get("description") or raw.get("details") or raw.get("narration") or raw.get("notes") or raw.get("memo")
    clean_desc = clean_text(str(raw_desc)) if raw_desc else ""

    return NormalizedRecord(
        record_id=rec_id,
        source=source_label,
        raw_reference_id=str(raw_ref) if raw_ref else None,
        clean_reference_id=clean_ref,
        raw_date=str(raw_date) if raw_date else None,
        iso_date=iso_date,
        amount=amount,
        currency=currency,
        raw_entity=str(raw_ent) if raw_ent else None,
        clean_entity=clean_ent,
        raw_description=str(raw_desc) if raw_desc else None,
        clean_description=clean_desc,
        raw_data=raw
    )
