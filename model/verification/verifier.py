"""
Legacy / currently unused in the live reconciliation path (only
verification.normalizers is imported by the runtime; this module is
exercised by tests only).
Verification functions and duplicate detection.
Produces structured VerificationResult per record matching the spec:

    {
        "record_id": "TXN001",
        "status": "MATCHED",
        "matched_record_id": "SET101",
        "checks": { "reference": true, "amount": true, ... },
        "difference": 0,
        "reason": null
    }
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Any
from .scorer import MatchScore


@dataclass
class VerificationResult:
    """Structured result of verifying a single record against candidates."""
    record_id: str
    status: str  # MATCHED, REVIEW_REQUIRED, UNRESOLVED, INVALID
    matched_record_id: Optional[str] = None
    checks: Dict[str, bool] = field(default_factory=dict)
    difference: Decimal = Decimal("0.00")
    reason: Optional[str] = None
    confidence: float = 0.0
    category: str = ""
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "status": self.status,
            "matched_record_id": self.matched_record_id,
            "checks": self.checks,
            "difference": float(self.difference),
            "reason": self.reason,
            "confidence": self.confidence,
            "category": self.category,
            "score_breakdown": self.score_breakdown,
        }


@dataclass
class DuplicateGroup:
    """A group of records that appear to be duplicates of each other."""
    reference_key: str
    record_ids: List[str] = field(default_factory=list)
    amount: Decimal = Decimal("0.00")
    source: str = ""


def verify_candidate(
    record_id: str,
    score: MatchScore,
    candidate_id: str,
    confidence_threshold: float = 80.0,
) -> VerificationResult:
    """
    Verify a single candidate match and produce a structured result.

    If score >= threshold → MATCHED
    If score < threshold → REVIEW_REQUIRED with reason
    """
    if score.total >= confidence_threshold:
        # Check for partial failures that should be flagged
        failing_checks = [k for k, v in score.checks.items() if not v]
        if failing_checks and score.total < 95.0:
            reason = f"Partial checks failed: {', '.join(failing_checks)}"
        else:
            reason = None

        return VerificationResult(
            record_id=record_id,
            status="MATCHED",
            matched_record_id=candidate_id,
            checks=score.checks,
            difference=score.amount_diff,
            reason=reason,
            confidence=score.total,
            category=score.category,
            score_breakdown=score.breakdown,
        )
    else:
        return VerificationResult(
            record_id=record_id,
            status="REVIEW_REQUIRED",
            matched_record_id=candidate_id,
            checks=score.checks,
            difference=score.amount_diff,
            reason=f"Score {score.total:.1f}% below threshold {confidence_threshold}%",
            confidence=score.total,
            category=score.category,
            score_breakdown=score.breakdown,
        )


def detect_duplicates(
    records: List[Any],
    get_ref: Any = None,
    get_amount: Any = None,
    get_id: Any = None,
) -> List[DuplicateGroup]:
    """
    Detect duplicate records within a single source based on
    composite key of (reference_id + amount).

    Args:
        records: list of record objects/dicts
        get_ref: callable to extract reference from a record
        get_amount: callable to extract amount from a record
        get_id: callable to extract record_id from a record

    Returns:
        List of DuplicateGroup (only groups with 2+ records)
    """
    if get_ref is None:
        get_ref = lambda r: getattr(r, 'clean_reference_id', None) or ""
    if get_amount is None:
        get_amount = lambda r: getattr(r, 'amount', Decimal("0"))
    if get_id is None:
        get_id = lambda r: getattr(r, 'record_id', "")

    seen: Dict[str, DuplicateGroup] = {}

    for rec in records:
        ref = get_ref(rec)
        amt = get_amount(rec)
        rec_id = get_id(rec)
        source = getattr(rec, 'source', '')

        key = f"{ref}_{amt}"
        if key in seen:
            seen[key].record_ids.append(rec_id)
        else:
            seen[key] = DuplicateGroup(
                reference_key=key,
                record_ids=[rec_id],
                amount=Decimal(str(amt)),
                source=source,
            )

    # Return only groups with actual duplicates (2+ records)
    return [g for g in seen.values() if len(g.record_ids) > 1]
