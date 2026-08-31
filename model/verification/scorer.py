"""
Composite scoring for record pair comparison.
Calls individual matchers and produces a structured score with boolean checks.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional

from .matchers import (
    exact_id_match,
    amount_match,
    date_match,
    currency_match,
    entity_match,
    fuzzy_entity_match,
    description_match,
)


@dataclass
class MatchScore:
    """
    Structured result of comparing two financial records.
    Includes total score, per-dimension breakdown, and boolean checks.
    """
    total: float  # 0..100
    breakdown: Dict[str, float] = field(default_factory=dict)
    checks: Dict[str, bool] = field(default_factory=dict)
    category: str = "PARTIAL_MATCH"
    amount_diff: Decimal = Decimal("0.00")
    days_diff: int = 0
    entity_similarity: float = 0.0


def calculate_match_score(
    ref_a: Optional[str],
    ref_b: Optional[str],
    clean_ref_a: Optional[str],
    clean_ref_b: Optional[str],
    amount_a: Decimal,
    amount_b: Decimal,
    date_a: Optional[str],
    date_b: Optional[str],
    currency_a: Optional[str],
    currency_b: Optional[str],
    entity_a: Optional[str],
    entity_b: Optional[str],
    desc_a: Optional[str] = None,
    desc_b: Optional[str] = None,
) -> MatchScore:
    """
    Calculate a composite match score (0-100) across 4 dimensions:
      - Reference/ID match: up to 40 points
      - Amount match: up to 30 points
      - Date proximity: up to 15 points
      - Entity similarity: up to 15 points

    Also sets boolean `checks` dict for structured verification result.
    """
    from rapidfuzz import fuzz

    # ---- 1. Reference matching (max 40) ----
    ref_score = 0.0
    ref_check = False

    if ref_a and ref_b:
        if exact_id_match(ref_a, ref_b):
            ref_score = 40.0
            ref_check = True
        elif clean_ref_a and clean_ref_b and clean_ref_a == clean_ref_b:
            ref_score = 38.0
            ref_check = True
        elif clean_ref_a and clean_ref_b and (
            clean_ref_a in clean_ref_b or clean_ref_b in clean_ref_a
        ):
            ref_score = 32.0
            ref_check = True
        else:
            sim = fuzz.ratio(ref_a.lower(), ref_b.lower())
            if sim >= 85:
                ref_score = 25.0
                ref_check = True
            elif sim >= 70:
                ref_score = 15.0

    # ---- 2. Amount matching (max 30) ----
    amt_score = 0.0
    is_amt_exact, amt_diff = amount_match(amount_a, amount_b, tolerance_cents=0)
    amt_check = False

    if is_amt_exact:
        amt_score = 30.0
        amt_check = True
    elif amt_diff <= Decimal("0.05"):
        amt_score = 28.0
        amt_check = True
    else:
        max_amt = max(abs(amount_a), abs(amount_b), Decimal("0.01"))
        pct_diff = (amt_diff / max_amt) * 100
        if pct_diff <= Decimal("1.0"):
            amt_score = 20.0
        elif pct_diff <= Decimal("3.0"):
            amt_score = 10.0

    # ---- 3. Date proximity (max 15) ----
    date_score = 0.0
    is_date_exact, days_diff = date_match(date_a, date_b, window_days=0)
    date_check = False

    if is_date_exact:
        date_score = 15.0
        date_check = True
    else:
        is_date_close, days_diff = date_match(date_a, date_b, window_days=999)
        if days_diff <= 2:
            date_score = 12.0
            date_check = True
        elif days_diff <= 5:
            date_score = 8.0
            date_check = True
        elif days_diff <= 10:
            date_score = 4.0

    # ---- 4. Entity similarity (max 15) ----
    ent_score = 0.0
    ent_check = False
    ent_sim = 0.0

    if entity_a and entity_b:
        is_exact, ent_sim = entity_match(entity_a, entity_b)
        if is_exact:
            ent_score = 15.0
            ent_check = True
        else:
            is_fuzzy, ent_sim = fuzzy_entity_match(entity_a, entity_b, threshold=45.0)
            if ent_sim >= 85:
                ent_score = 15.0
                ent_check = True
            elif ent_sim >= 65:
                ent_score = 12.0
                ent_check = True
            elif ent_sim >= 45:
                ent_score = 8.0
    elif desc_a and desc_b:
        is_desc_match, desc_sim = description_match(desc_a, desc_b, threshold=50.0)
        if desc_sim >= 75:
            ent_score = 12.0
            ent_check = True
        elif desc_sim >= 50:
            ent_score = 8.0
        ent_sim = desc_sim

    # ---- Currency check (not scored, but tracked) ----
    cur_check = currency_match(currency_a, currency_b)

    # ---- Total ----
    total = round(ref_score + amt_score + date_score + ent_score, 1)

    # ---- Category determination ----
    if ref_score >= 35 and amt_score == 30 and days_diff <= 1 and ent_score >= 8:
        category = "EXACT_MATCH"
    elif ref_score >= 25 and amt_score == 30:
        category = "FUZZY_MATCH"
    elif ref_score >= 30 and days_diff > 2 and amt_score == 30:
        category = "DATE_LAG"
    elif ref_score >= 30 and amt_diff > Decimal("0.05"):
        category = "AMOUNT_MISMATCH"
    else:
        category = "PARTIAL_MATCH"

    return MatchScore(
        total=total,
        breakdown={
            "reference_score": ref_score,
            "amount_score": amt_score,
            "date_score": date_score,
            "entity_score": ent_score,
        },
        checks={
            "reference": ref_check,
            "amount": amt_check,
            "date": date_check,
            "entity": ent_check,
            "currency": cur_check,
        },
        category=category,
        amount_diff=amt_diff,
        days_diff=days_diff,
        entity_similarity=ent_sim,
    )
