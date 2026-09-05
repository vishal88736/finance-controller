"""
Legacy / currently unused in the live reconciliation path (only
verification.normalizers is imported by the runtime; this module is
exercised by tests only).
Exception types and classification for financial reconciliation.
Explicit categories — never just "FAILED".
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from .scorer import MatchScore


class ExceptionType(str, Enum):
    """
    Explicit exception categories.
    The user needs to know WHY a record could not be reconciled.
    """
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    DATE_MISMATCH = "DATE_MISMATCH"
    MISSING_RECORD = "MISSING_RECORD"
    DUPLICATE = "DUPLICATE"
    AMBIGUOUS_MATCH = "AMBIGUOUS_CANDIDATES"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    INVALID_RECORD = "INVALID_RECORD"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MISSING_COUNTERPART = "MISSING_COUNTERPART"


def classify_exception(
    has_candidates: bool,
    num_candidates: int,
    top_score: Optional[MatchScore] = None,
    second_score: Optional[MatchScore] = None,
    is_duplicate: bool = False,
    is_missing_counterpart: bool = False,
    missing_fields: Optional[List[str]] = None,
    ambiguity_delta: float = 6.0,
    confidence_threshold: float = 80.0,
) -> ExceptionType:
    """
    Classify why a record could not be reconciled.
    Uses deterministic rules — no LLM.

    Priority order:
    1. INVALID_RECORD — missing required fields
    2. DUPLICATE — intra-source duplicate detected
    3. MISSING_COUNTERPART — no candidates at all
    4. AMBIGUOUS_MATCH — multiple close candidates
    5. AMOUNT_MISMATCH — strong ref match but amount differs
    6. CURRENCY_MISMATCH — currencies don't match
    7. DATE_MISMATCH — dates too far apart
    8. ENTITY_MISMATCH — entities don't match
    9. LOW_CONFIDENCE — below threshold, no specific reason
    """
    # 1. Invalid record
    if missing_fields:
        return ExceptionType.INVALID_RECORD

    # 2. Duplicate
    if is_duplicate:
        return ExceptionType.DUPLICATE

    # 3. Missing counterpart
    if is_missing_counterpart or not has_candidates or num_candidates == 0:
        return ExceptionType.MISSING_COUNTERPART

    # 4. Ambiguous match (multiple close candidates)
    if (
        top_score is not None
        and second_score is not None
        and top_score.total >= 65.0
        and (top_score.total - second_score.total) < ambiguity_delta
        and top_score.total < 98.0
    ):
        return ExceptionType.AMBIGUOUS_MATCH

    # For remaining classifications, we need a top_score
    if top_score is None:
        return ExceptionType.MISSING_COUNTERPART

    checks = top_score.checks

    # 5. Amount mismatch (strong reference but amount differs)
    if checks.get("reference", False) and not checks.get("amount", False):
        return ExceptionType.AMOUNT_MISMATCH

    # 6. Currency mismatch
    if not checks.get("currency", True):
        return ExceptionType.CURRENCY_MISMATCH

    # 7. Date mismatch (strong reference and amount but date too far)
    if (
        checks.get("reference", False)
        and checks.get("amount", False)
        and not checks.get("date", False)
        and top_score.days_diff > 10
    ):
        return ExceptionType.DATE_MISMATCH

    # 8. Entity mismatch
    if (
        checks.get("reference", False)
        and checks.get("amount", False)
        and not checks.get("entity", False)
        and top_score.entity_similarity < 40
    ):
        return ExceptionType.ENTITY_MISMATCH

    # 9. Low confidence (fallback)
    return ExceptionType.LOW_CONFIDENCE


def get_exception_action(exc_type: ExceptionType) -> str:
    """Return a recommended action for each exception type."""
    actions = {
        ExceptionType.AMOUNT_MISMATCH: "Verify if difference is due to bank transfer fee, gateway commission, or vendor discount.",
        ExceptionType.DATE_MISMATCH: "Check for settlement lag, international wire processing time, or posting date difference.",
        ExceptionType.MISSING_RECORD: "Post missing transaction to ledger or investigate bank feed for missing entry.",
        ExceptionType.MISSING_COUNTERPART: "Post missing transaction to ledger or investigate bank feed for missing entry.",
        ExceptionType.DUPLICATE: "Void duplicate ledger transaction entry to correct cash balances.",
        ExceptionType.AMBIGUOUS_MATCH: "Manual cross-reference required to prevent incorrect ledger posting.",
        ExceptionType.ENTITY_MISMATCH: "Verify counterparty name against vendor master data.",
        ExceptionType.CURRENCY_MISMATCH: "Check for multi-currency booking errors or FX conversion entries.",
        ExceptionType.INVALID_RECORD: "Correct missing fields in source data and re-process.",
        ExceptionType.LOW_CONFIDENCE: "Review record manually — insufficient evidence for automated reconciliation.",
    }
    return actions.get(exc_type, "Manual review required.")
