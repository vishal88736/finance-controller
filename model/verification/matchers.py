"""
Legacy / currently unused in the live reconciliation path (only
verification.normalizers is imported by the runtime; this module is
exercised by tests only).
Individual match-check functions for financial record comparison.
Each function checks one specific dimension and returns a deterministic result.

Uses Decimal for all monetary comparisons.
Uses RapidFuzz for entity/description fuzzy matching.
"""

from decimal import Decimal
from datetime import datetime
from typing import Tuple, Optional
from rapidfuzz import fuzz


def exact_id_match(ref_a: Optional[str], ref_b: Optional[str]) -> bool:
    """
    Check if two reference IDs are an exact match (case-insensitive).
    Both must be non-empty.
    """
    if not ref_a or not ref_b:
        return False
    return ref_a.strip().upper() == ref_b.strip().upper()


def amount_match(
    amt_a: Decimal,
    amt_b: Decimal,
    tolerance_cents: int = 0
) -> Tuple[bool, Decimal]:
    """
    Check if two amounts match within a tolerance.
    Returns (is_match, absolute_difference).

    tolerance_cents=0 means exact match only.
    tolerance_cents=5 means allow up to $0.05 difference.

    Uses Decimal arithmetic — never float.
    """
    diff = abs(amt_a - amt_b)
    tolerance = Decimal(tolerance_cents) / Decimal(100)
    return diff <= tolerance, diff


def date_match(
    date_a: Optional[str],
    date_b: Optional[str],
    window_days: int = 0
) -> Tuple[bool, int]:
    """
    Check if two ISO dates match within a window.
    Returns (is_match, days_difference).

    window_days=0 means same day only.
    window_days=3 means within 3 calendar days.
    """
    if not date_a or not date_b:
        return False, 999

    try:
        dt_a = datetime.strptime(date_a, "%Y-%m-%d")
        dt_b = datetime.strptime(date_b, "%Y-%m-%d")
        days_diff = abs((dt_a - dt_b).days)
        return days_diff <= window_days, days_diff
    except (ValueError, TypeError):
        return False, 999


def currency_match(cur_a: Optional[str], cur_b: Optional[str]) -> bool:
    """
    Check if two currency codes match (case-insensitive).
    If either is missing, assume match (benefit of doubt).
    """
    if not cur_a or not cur_b:
        return True
    return cur_a.strip().upper() == cur_b.strip().upper()


def entity_match(
    ent_a: Optional[str],
    ent_b: Optional[str]
) -> Tuple[bool, float]:
    """
    Check if two entity names match exactly (after normalization).
    Returns (is_exact_match, similarity_ratio 0-100).
    """
    if not ent_a or not ent_b:
        return False, 0.0
    a = ent_a.strip().lower()
    b = ent_b.strip().lower()
    if a == b:
        return True, 100.0
    # Compute similarity for reporting even if not exact
    sim = max(
        fuzz.ratio(a, b),
        fuzz.token_sort_ratio(a, b)
    )
    return False, float(sim)


def fuzzy_entity_match(
    ent_a: Optional[str],
    ent_b: Optional[str],
    threshold: float = 80.0
) -> Tuple[bool, float]:
    """
    Check if two entity names match using fuzzy string similarity.
    Uses RapidFuzz (deterministic, no LLM).
    Returns (passes_threshold, similarity_ratio 0-100).

    Example:
        "Amazon India Pvt Ltd" vs "AMAZON INDIA" → True, 85.0
    """
    if not ent_a or not ent_b:
        return False, 0.0

    a = ent_a.strip().lower()
    b = ent_b.strip().lower()

    if a == b:
        return True, 100.0

    # Use multiple fuzzy strategies and take the best
    sim = max(
        fuzz.ratio(a, b),
        fuzz.token_sort_ratio(a, b),
        fuzz.token_set_ratio(a, b),
    )
    return sim >= threshold, float(sim)


def description_match(
    desc_a: Optional[str],
    desc_b: Optional[str],
    threshold: float = 70.0
) -> Tuple[bool, float]:
    """
    Check if two transaction descriptions have significant overlap.
    Uses token_set_ratio which handles word reordering and partial overlap.
    Returns (passes_threshold, similarity_ratio 0-100).
    """
    if not desc_a or not desc_b:
        return False, 0.0

    a = desc_a.strip().lower()
    b = desc_b.strip().lower()

    sim = fuzz.token_set_ratio(a, b)
    return sim >= threshold, float(sim)
