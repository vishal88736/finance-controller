"""
Normalization functions for financial records.
Uses Decimal for monetary values — NEVER floating-point for financial truth.
"""

import re
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime
from typing import Optional, Any, List


def normalize_amount(raw: Any) -> Decimal:
    """
    Parse a raw amount value into Decimal.
    Strips currency symbols, commas, whitespace.

    GOOD: Decimal("1050.25")
    BAD:  1050.25 (float)
    """
    if raw is None or _is_nan(raw):
        return Decimal("0.00")
    if isinstance(raw, Decimal):
        return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(raw, (int, float)):
        # Convert float through string to avoid float precision issues
        return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # String cleaning: strip currency symbols, commas, spaces
    cleaned = re.sub(r'[₹$€£¥,\s]', '', str(raw))
    # Remove trailing currency codes like "USD", "INR"
    cleaned = re.sub(r'[A-Za-z]+$', '', cleaned).strip()
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def normalize_date(raw: Any) -> Optional[str]:
    """
    Parse a raw date value into ISO 8601 format (YYYY-MM-DD).
    Supports multiple common date formats.
    Returns None if unparseable.
    """
    if raw is None or _is_nan(raw):
        return None
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")

    date_str = str(raw).strip()
    if not date_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Fallback: regex extraction of YYYY-MM-DD
    match = re.search(
        r'\b(20\d\d)[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b',
        date_str
    )
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def normalize_currency(raw: Any) -> str:
    """
    Normalize currency code to uppercase 3-letter ISO 4217.
    Defaults to 'USD' if empty.
    """
    if raw is None or _is_nan(raw):
        return "USD"
    cleaned = str(raw).strip().upper()
    # Extract 3-letter currency code
    match = re.search(r'\b([A-Z]{3})\b', cleaned)
    if match:
        return match.group(1)
    # Map common symbols
    symbol_map = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY"}
    for sym, code in symbol_map.items():
        if sym in str(raw):
            return code
    return cleaned if len(cleaned) == 3 else "USD"


def normalize_entity_name(raw: Any) -> str:
    """
    Normalize entity/vendor/merchant name for comparison.
    Lowercase, strip noise characters, collapse whitespace.
    """
    if raw is None or _is_nan(raw):
        return ""
    cleaned = str(raw).strip()
    if not cleaned:
        return ""
    # Lowercase
    cleaned = cleaned.lower()
    # Replace common separators with space
    cleaned = re.sub(r'[\-_/\\#&.]+', ' ', cleaned)
    # Remove common suffixes that vary between sources
    for suffix in [' pvt ltd', ' pvt. ltd.', ' private limited', ' limited',
                   ' ltd', ' inc', ' corp', ' llc', ' llp', ' gmbh',
                   ' co', ' company']:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def normalize_transaction_id(raw: Any) -> str:
    """
    Extract core alphanumeric identifier from a transaction/reference ID.
    Strips common prefixes (INV, REF, TXN, etc.) and noise.
    """
    if raw is None or _is_nan(raw):
        return ""
    cleaned = str(raw).upper().strip()
    if not cleaned:
        return ""
    # Remove common prefix noise
    cleaned = re.sub(
        r'^(INV|REF|TXN|PAYOUT|ORD|ORDER|SETTLE|PAY)[\-_#/:]*',
        '', cleaned
    )
    # Remove common suffix noise
    cleaned = re.sub(r'[\-_#/:]*(AUTO|MANUAL|CLR)$', '', cleaned)
    # Extract numbers as core token
    nums = re.findall(r'\d+', cleaned)
    if nums:
        return "".join(nums)
    return cleaned.strip()


def validate_required_fields(record: dict) -> List[str]:
    """
    Check that a raw record has the minimum required fields for reconciliation.
    Returns a list of missing field names (empty list = valid).
    """
    missing = []

    # Must have some kind of ID
    id_fields = ["record_id", "id", "txn_id", "payout_id", "transaction_id"]
    if not any(record.get(f) for f in id_fields):
        missing.append("record_id")

    # Must have an amount
    amt_fields = ["amount", "net_amount", "gross_amount", "value", "total"]
    if not any(record.get(f) is not None for f in amt_fields):
        missing.append("amount")

    return missing


def _is_nan(val: Any) -> bool:
    """Check if a value is NaN (handles float NaN safely)."""
    try:
        if isinstance(val, float) and math.isnan(val):
            return True
    except Exception:
        pass
    if isinstance(val, str) and val.strip().lower() in ('nan', 'none', 'null', ''):
        return True
    return False


def is_missing_amount_value(raw: Any) -> bool:
    """
    Strict missing-amount detector (does NOT treat 0 as missing).

    Returns True when the raw value carries no financial amount:
    None, NaN/Inf floats, empty/blank strings, or 'nan'/'none'/'null' tokens.
    Numeric zero (0, 0.0, "0", "0.00") is a VALID amount and returns False.
    """
    if raw is None:
        return True
    if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
        return True
    if isinstance(raw, Decimal):
        try:
            if raw.is_nan() or raw.is_infinite():
                return True
        except Exception:
            return True
        return False
    if isinstance(raw, (int,)):
        return False
    s = str(raw).strip()
    if s == "":
        return True
    if s.lower() in ("nan", "none", "null", "n/a", "na", "-", "--", "inf", "-inf", "+inf"):
        return True
    return False


def parse_optional_amount(raw: Any) -> Optional[Decimal]:
    """
    Parse a raw amount value into Decimal, preserving missingness.

    Returns None when the value is missing/invalid (see is_missing_amount_value
    or unparseable strings). Returns Decimal("0.00") ONLY for genuine zero
    inputs ("0", 0, 0.0). Callers must treat None as "no amount" and exclude
    such records from amount-based matching with an INVALID_RECORD /
    MISSING_AMOUNT exception — never coerce to 0.0.
    """
    if is_missing_amount_value(raw):
        return None
    if isinstance(raw, Decimal):
        try:
            if raw.is_nan() or raw.is_infinite():
                return None
        except Exception:
            return None
        return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(raw, (int, float)):
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            return None
    cleaned = re.sub(r'[₹$€£¥,\s]', '', str(raw))
    cleaned = re.sub(r'[A-Za-z]+$', '', cleaned).strip()
    if cleaned in ("", "-", ".", "-.", ".-"):
        return None
    try:
        d = Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if d.is_nan() or d.is_infinite():
            return None
        return d
    except (InvalidOperation, ValueError, Exception):
        return None
