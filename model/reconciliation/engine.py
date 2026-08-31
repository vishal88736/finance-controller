"""
Deterministic Financial Reconciliation Engine.
Implements multi-pass matching strategy:

    PASS 1: Exact reference matching (auto-match)
    PASS 2: Amount + date matching (within tolerance)
    PASS 3: Entity/description fuzzy matching
    PASS 4: Tolerance checks (classify discrepancy, don't hide it)

Evidence-First Design: Every decision returns structured evidence and confidence breakdown.
Categorizes discrepancies into NORMAL (small rounding, minor date lag) and MATERIAL (fee deltas, duplicates, missing).
"""

import time
import uuid
from decimal import Decimal
from typing import List, Dict, Tuple, Optional, Set, Any

from ..ingestion.normalizer import NormalizedRecord
from ..verification.scorer import calculate_match_score, MatchScore
from ..verification.verifier import detect_duplicates, verify_candidate, VerificationResult
from ..verification.exceptions import (
    ExceptionType,
    classify_exception,
    get_exception_action,
)
from .models import (
    CandidateMatch,
    ReconciliationMatch,
    ReconciliationException,
    ReconciliationSummary,
)


def score_record_pair(
    rec_a: NormalizedRecord, rec_b: NormalizedRecord
) -> Tuple[float, Dict[str, float], str, float, int]:
    """
    Backward-compatible scoring function.
    Delegates to verification.scorer.calculate_match_score.
    Returns: (total_score, breakdown, category, amt_diff, days_diff)
    """
    ms = calculate_match_score(
        ref_a=rec_a.raw_reference_id,
        ref_b=rec_b.raw_reference_id,
        clean_ref_a=rec_a.clean_reference_id,
        clean_ref_b=rec_b.clean_reference_id,
        amount_a=rec_a.amount_as_decimal,
        amount_b=rec_b.amount_as_decimal,
        date_a=rec_a.iso_date,
        date_b=rec_b.iso_date,
        currency_a=rec_a.currency,
        currency_b=rec_b.currency,
        entity_a=rec_a.clean_entity,
        entity_b=rec_b.clean_entity,
        desc_a=rec_a.clean_description,
        desc_b=rec_b.clean_description,
    )
    return (
        ms.total,
        ms.breakdown,
        ms.category,
        float(ms.amount_diff),
        ms.days_diff,
    )


class ReconciliationEngine:
    def __init__(
        self,
        confidence_threshold: float = 80.0,
        ambiguity_delta: float = 6.0,
    ):
        self.confidence_threshold = confidence_threshold
        self.ambiguity_delta = ambiguity_delta

    def run_reconciliation(
        self,
        records: List[NormalizedRecord],
    ) -> Tuple[
        List[ReconciliationMatch],
        List[ReconciliationException],
        ReconciliationSummary,
    ]:
        start_time = time.perf_counter()

        # ---- Split into sources ----
        unique_sources = sorted(list(set(r.source for r in records)))
        primary_source = self._pick_primary_source(unique_sources)
        records_a = [r for r in records if r.source == primary_source]
        records_b = [r for r in records if r.source != primary_source]

        # Fallback: if all same source, split evenly
        if not records_b and len(records) > 1:
            half = len(records) // 2
            records_a = records[:half]
            records_b = records[half:]

        # ---- PASS 0: Duplicate detection in source A ----
        dup_groups = detect_duplicates(records_a)
        duplicate_ids: Set[str] = set()
        for grp in dup_groups:
            for rid in grp.record_ids[1:]:
                duplicate_ids.add(rid)

        matched_b_ids: Set[str] = set()
        matches: List[ReconciliationMatch] = []
        exceptions: List[ReconciliationException] = []

        total_amount_processed = sum(
            abs(Decimal(str(r.amount))) for r in records
        )
        total_amount_matched = Decimal("0.00")
        total_amount_discrepancy = Decimal("0.00")

        # ---- Process each source A record ----
        for rec_a in records_a:
            # Handle duplicates
            if rec_a.record_id in duplicate_ids:
                exceptions.append(self._make_exception(
                    rec_a,
                    reason_code=ExceptionType.DUPLICATE.value,
                    discrepancy_category="MATERIAL",
                    evidence={
                        "record_id": rec_a.record_id,
                        "reference_id": rec_a.raw_reference_id,
                        "amount": rec_a.amount,
                        "duplicate_type": "EXACT_REFERENCE_COLLISION",
                        "rule": "Duplicate ledger booking detected."
                    },
                    explanation=(
                        f"Duplicate entry detected in ledger with reference "
                        f"{rec_a.raw_reference_id} and amount "
                        f"${rec_a.amount:,.2f}."
                    ),
                ))
                continue

            # Generate candidates from records_b (not already matched)
            candidates = self._generate_candidates(rec_a, records_b, matched_b_ids)

            if not candidates:
                exceptions.append(self._make_exception(
                    rec_a,
                    reason_code=ExceptionType.MISSING_COUNTERPART.value,
                    discrepancy_category="MATERIAL",
                    evidence={
                        "record_id": rec_a.record_id,
                        "reference_id": rec_a.raw_reference_id,
                        "amount": rec_a.amount,
                        "date": rec_a.iso_date,
                        "candidate_count": 0,
                        "rule": "No counterpart transaction in bank statement/feed."
                    },
                    explanation=(
                        f"No matching counterpart transaction found in bank/settlement "
                        f"records for reference {rec_a.raw_reference_id or rec_a.record_id} "
                        f"(${rec_a.amount:,.2f})."
                    ),
                ))
                continue

            # Sort by score descending
            candidates.sort(key=lambda c: c.confidence_score, reverse=True)
            top = candidates[0]
            second = candidates[1] if len(candidates) > 1 else None

            # Build MatchScore for classification
            top_ms = MatchScore(
                total=top.confidence_score,
                breakdown=top.score_breakdown,
                checks=top.checks if hasattr(top, 'checks') and top.checks else {},
                category=top.match_category,
                amount_diff=Decimal(str(top.amount_diff)),
                days_diff=top.date_diff_days,
            )
            second_ms = None
            if second:
                second_ms = MatchScore(
                    total=second.confidence_score,
                    breakdown=second.score_breakdown,
                    checks={},
                    category=second.match_category,
                    amount_diff=Decimal(str(second.amount_diff)),
                    days_diff=second.date_diff_days,
                )

            # ---- PASS 1-4: Multi-pass classification ----
            exc_type = classify_exception(
                has_candidates=True,
                num_candidates=len(candidates),
                top_score=top_ms,
                second_score=second_ms,
                is_duplicate=False,
                is_missing_counterpart=False,
                ambiguity_delta=self.ambiguity_delta,
                confidence_threshold=self.confidence_threshold,
            )

            # If ambiguous → exception
            if exc_type == ExceptionType.AMBIGUOUS_MATCH:
                exceptions.append(self._make_exception(
                    rec_a,
                    reason_code=exc_type.value,
                    discrepancy_category="MATERIAL",
                    confidence=top.confidence_score,
                    amount_discrepancy=top.amount_diff,
                    candidates=candidates[:3],
                    evidence={
                        "record_id_a": rec_a.record_id,
                        "candidate_a": top.target_record_id,
                        "score_a": top.confidence_score,
                        "candidate_b": second.target_record_id if second else None,
                        "score_b": second.confidence_score if second else None,
                        "score_delta": round(top.confidence_score - (second.confidence_score if second else 0), 1),
                        "ambiguity_threshold": self.ambiguity_delta
                    },
                    explanation=(
                        f"Multiple ambiguous candidates found with close confidence "
                        f"({top.confidence_score:.1f}% vs "
                        f"{second.confidence_score if second else 0:.1f}%). "
                        f"Insufficient evidence to safely auto-select."
                    ),
                ))
                continue

            # PASS 1: Strong reference match + amount mismatch → AMOUNT_MISMATCH exception
            if (
                top.score_breakdown.get("reference_score", 0) >= 30.0
                and top.amount_diff > 0.05
            ):
                total_amount_discrepancy += Decimal(str(top.amount_diff))
                exceptions.append(self._make_exception(
                    rec_a,
                    reason_code=ExceptionType.AMOUNT_MISMATCH.value,
                    discrepancy_category="MATERIAL",
                    confidence=top.confidence_score,
                    amount_discrepancy=top.amount_diff,
                    candidates=candidates[:2],
                    evidence={
                        "record_id_a": rec_a.record_id,
                        "target_record_id": top.target_record_id,
                        "ledger_amount": rec_a.amount,
                        "bank_amount": top.target_amount,
                        "amount_difference": top.amount_diff,
                        "percentage_difference": round((top.amount_diff / max(rec_a.amount, 0.01)) * 100, 2),
                        "reference_matched": True,
                        "reference": rec_a.raw_reference_id
                    },
                    explanation=(
                        f"Amount mismatch on reference {rec_a.raw_reference_id}: "
                        f"Ledger is ${rec_a.amount:,.2f} vs Bank candidate "
                        f"{top.target_record_id} is ${top.target_amount:,.2f} "
                        f"(Discrepancy: ${top.amount_diff:,.2f}). "
                        f"Possible gateway fee or wire deduction."
                    ),
                ))
                continue

            # PASS 2-4: High confidence match
            if top.confidence_score >= self.confidence_threshold:
                match_id = f"match_{uuid.uuid4().hex[:12]}"
                matched_b_ids.add(top.target_record_id)
                total_amount_matched += Decimal(str(rec_a.amount))

                # Build Evidence-First Structure
                evidence = {
                    "match_id": match_id,
                    "record_id_a": rec_a.record_id,
                    "record_id_b": top.target_record_id,
                    "amount_a": rec_a.amount,
                    "amount_b": top.target_amount,
                    "amount_difference": top.amount_diff,
                    "amount_match_exact": top.amount_diff == 0.0,
                    "date_a": rec_a.iso_date,
                    "date_b": top.target_date,
                    "date_difference_days": top.date_diff_days,
                    "entity_a": rec_a.raw_entity,
                    "entity_b": top.target_entity,
                    "reference_a": rec_a.raw_reference_id,
                    "score_breakdown": top.score_breakdown,
                    "checks": top.checks if hasattr(top, 'checks') else {},
                    "confidence_score": top.confidence_score,
                    "match_category": top.match_category
                }

                m = ReconciliationMatch(
                    match_id=match_id,
                    record_id_a=rec_a.record_id,
                    record_id_b=top.target_record_id,
                    source_a=rec_a.source,
                    source_b=top.target_source,
                    amount_a=rec_a.amount,
                    amount_b=top.target_amount,
                    date_a=rec_a.iso_date,
                    date_b=top.target_date,
                    entity_a=rec_a.raw_entity,
                    entity_b=top.target_entity,
                    confidence_score=top.confidence_score,
                    match_category=top.match_category,
                    status="MATCHED",
                    score_breakdown=top.score_breakdown,
                    checks=top.checks if hasattr(top, 'checks') else {},
                    evidence=evidence,
                    explanation=(
                        f"Matched with {top.confidence_score:.1f}% confidence "
                        f"({top.match_category}). Evidence: Amount Δ=${top.amount_diff:.2f}, "
                        f"Date Δ={top.date_diff_days}d."
                    ),
                )
                matches.append(m)
            else:
                # Low confidence → exception
                exceptions.append(self._make_exception(
                    rec_a,
                    reason_code=ExceptionType.LOW_CONFIDENCE.value,
                    discrepancy_category="MATERIAL",
                    confidence=top.confidence_score,
                    amount_discrepancy=top.amount_diff,
                    candidates=candidates[:2],
                    evidence={
                        "record_id": rec_a.record_id,
                        "best_candidate": top.target_record_id,
                        "best_score": top.confidence_score,
                        "required_threshold": self.confidence_threshold
                    },
                    explanation=(
                        f"Best candidate {top.target_record_id} scored only "
                        f"{top.confidence_score:.1f}%, below the required "
                        f"{self.confidence_threshold}% threshold."
                    ),
                ))

        # ---- Unmatched records in Source B ----
        for rec_b in records_b:
            if rec_b.record_id not in matched_b_ids:
                exceptions.append(self._make_exception(
                    rec_b,
                    reason_code=ExceptionType.MISSING_COUNTERPART.value,
                    discrepancy_category="MATERIAL",
                    evidence={
                        "record_id": rec_b.record_id,
                        "source": rec_b.source,
                        "amount": rec_b.amount,
                        "date": rec_b.iso_date,
                        "rule": "Bank transaction unrecorded in internal ledger."
                    },
                    explanation=(
                        f"Bank transaction {rec_b.record_id} "
                        f"(${rec_b.amount:,.2f}) for "
                        f"'{rec_b.raw_entity or rec_b.clean_description}' "
                        f"is unrecorded in the internal ledger."
                    ),
                ))

        # ---- Summary metrics ----
        elapsed = max(time.perf_counter() - start_time, 0.001)
        total_records_processed = len(records)
        match_rate = round(
            (len(matches) / max(len(records_a), 1)) * 100.0, 2
        )
        throughput = round(total_records_processed / elapsed, 2)

        summary = ReconciliationSummary(
            total_records_processed=total_records_processed,
            matched_count=len(matches),
            unmatched_count=len(exceptions),
            unresolved_exceptions_count=len(exceptions),
            match_rate=match_rate,
            total_amount_processed=round(float(total_amount_processed), 2),
            total_amount_matched=round(float(total_amount_matched), 2),
            total_amount_discrepancy=round(float(total_amount_discrepancy), 2),
            processing_time_sec=round(elapsed, 4),
            throughput_records_sec=throughput,
        )

        return matches, exceptions, summary

    def _pick_primary_source(self, sources: List[str]) -> str:
        """Pick the primary source (ledger-like) for reconciliation."""
        for s in sources:
            if "ledger" in s.lower() or "source_a" in s.lower():
                return s
        return sources[0] if sources else "source_a"

    def _generate_candidates(
        self,
        rec_a: NormalizedRecord,
        records_b: List[NormalizedRecord],
        matched_b_ids: Set[str],
    ) -> List[CandidateMatch]:
        """
        Generate scored candidate matches for a single source A record
        against all available source B records.
        """
        candidates: List[CandidateMatch] = []

        for rec_b in records_b:
            if rec_b.record_id in matched_b_ids:
                continue

            ms = calculate_match_score(
                ref_a=rec_a.raw_reference_id,
                ref_b=rec_b.raw_reference_id,
                clean_ref_a=rec_a.clean_reference_id,
                clean_ref_b=rec_b.clean_reference_id,
                amount_a=rec_a.amount_as_decimal,
                amount_b=rec_b.amount_as_decimal,
                date_a=rec_a.iso_date,
                date_b=rec_b.iso_date,
                currency_a=rec_a.currency,
                currency_b=rec_b.currency,
                entity_a=rec_a.clean_entity,
                entity_b=rec_b.clean_entity,
                desc_a=rec_a.clean_description,
                desc_b=rec_b.clean_description,
            )

            if ms.total >= 40.0:
                candidates.append(CandidateMatch(
                    target_record_id=rec_b.record_id,
                    target_source=rec_b.source,
                    target_amount=rec_b.amount,
                    target_date=rec_b.iso_date,
                    target_entity=rec_b.raw_entity,
                    confidence_score=ms.total,
                    score_breakdown=ms.breakdown,
                    match_category=ms.category,
                    amount_diff=float(ms.amount_diff),
                    date_diff_days=ms.days_diff,
                    checks=ms.checks,
                    notes=(
                        f"Ref: {ms.breakdown['reference_score']}, "
                        f"Amt: {ms.breakdown['amount_score']}, "
                        f"Date: {ms.breakdown['date_score']}, "
                        f"Ent: {ms.breakdown['entity_score']}"
                    ),
                ))

        return candidates

    def _make_exception(
        self,
        rec: NormalizedRecord,
        reason_code: str,
        explanation: str,
        discrepancy_category: str = "MATERIAL",
        confidence: float = 0.0,
        amount_discrepancy: float = 0.0,
        candidates: Optional[List[CandidateMatch]] = None,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> ReconciliationException:
        """Create a ReconciliationException with recommended action and evidence."""
        action = get_exception_action(
            ExceptionType(reason_code)
        )
        return ReconciliationException(
            exception_id=f"exc_{uuid.uuid4().hex[:12]}",
            record_id=rec.record_id,
            source=rec.source,
            amount=rec.amount,
            entity=rec.raw_entity,
            date=rec.iso_date,
            reason_code=reason_code,
            discrepancy_category=discrepancy_category,
            confidence=confidence,
            decision="UNRESOLVED",
            explanation=f"{explanation} Action: {action}",
            amount_discrepancy=amount_discrepancy,
            candidates=candidates or [],
            evidence=evidence or {},
            raw_data=rec.raw_data,
        )
