"""
Deterministic Financial Reconciliation Engine.
Implements multi-source matching, candidate generation, explicit scoring,
and honest exception classification without relying on LLMs for math.
"""

import time
import uuid
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz

from ..ingestion.normalizer import NormalizedRecord
from .models import (
    CandidateMatch,
    ReconciliationMatch,
    ReconciliationException,
    ReconciliationSummary
)

def compute_date_diff(date_a: Optional[str], date_b: Optional[str]) -> int:
    if not date_a or not date_b:
        return 999
    try:
        dt_a = datetime.strptime(date_a, "%Y-%m-%d")
        dt_b = datetime.strptime(date_b, "%Y-%m-%d")
        return abs((dt_a - dt_b).days)
    except Exception:
        return 999

def score_record_pair(rec_a: NormalizedRecord, rec_b: NormalizedRecord) -> Tuple[float, Dict[str, float], str, float, int]:
    """
    Computes deterministic match score (0 to 100) with explicit breakdown:
    - Reference match: up to +40
    - Amount match: up to +30
    - Date proximity: up to +15
    - Entity similarity: up to +15
    """
    score_breakdown: Dict[str, float] = {
        "reference_score": 0.0,
        "amount_score": 0.0,
        "date_score": 0.0,
        "entity_score": 0.0
    }

    # 1. Reference matching (+40 max)
    ref_score = 0.0
    if rec_a.raw_reference_id and rec_b.raw_reference_id:
        if rec_a.raw_reference_id.strip().upper() == rec_b.raw_reference_id.strip().upper():
            ref_score = 40.0
        elif rec_a.clean_reference_id and rec_b.clean_reference_id and rec_a.clean_reference_id == rec_b.clean_reference_id:
            ref_score = 38.0
        elif rec_a.clean_reference_id and rec_b.clean_reference_id and (rec_a.clean_reference_id in rec_b.clean_reference_id or rec_b.clean_reference_id in rec_a.clean_reference_id):
            ref_score = 32.0
        else:
            sim = fuzz.ratio(rec_a.raw_reference_id.lower(), rec_b.raw_reference_id.lower())
            if sim >= 85:
                ref_score = 25.0
            elif sim >= 70:
                ref_score = 15.0
    elif rec_a.record_id and rec_b.record_id and rec_a.record_id == rec_b.record_id:
        ref_score = 40.0
    
    score_breakdown["reference_score"] = ref_score

    # 2. Amount matching (+30 max)
    amt_score = 0.0
    amt_diff = round(abs(rec_a.amount - rec_b.amount), 2)
    if amt_diff == 0.0:
        amt_score = 30.0
    elif amt_diff <= 0.05:
        amt_score = 28.0
    else:
        # Check percentage difference
        max_amt = max(abs(rec_a.amount), abs(rec_b.amount), 0.01)
        pct_diff = (amt_diff / max_amt) * 100.0
        if pct_diff <= 1.0:
            amt_score = 20.0
        elif pct_diff <= 3.0:
            amt_score = 10.0
        else:
            amt_score = 0.0
    
    score_breakdown["amount_score"] = amt_score

    # 3. Date proximity (+15 max)
    date_score = 0.0
    days_diff = compute_date_diff(rec_a.iso_date, rec_b.iso_date)
    if days_diff == 0:
        date_score = 15.0
    elif days_diff <= 2:
        date_score = 12.0
    elif days_diff <= 5:
        date_score = 8.0
    elif days_diff <= 10:
        date_score = 4.0
    else:
        date_score = 0.0
    
    score_breakdown["date_score"] = date_score

    # 4. Entity similarity (+15 max)
    ent_score = 0.0
    if rec_a.clean_entity and rec_b.clean_entity:
        if rec_a.clean_entity == rec_b.clean_entity:
            ent_score = 15.0
        else:
            ent_sim = max(
                fuzz.token_sort_ratio(rec_a.clean_entity, rec_b.clean_entity),
                fuzz.ratio(rec_a.clean_entity, rec_b.clean_entity)
            )
            if ent_sim >= 85:
                ent_score = 15.0
            elif ent_sim >= 65:
                ent_score = 12.0
            elif ent_sim >= 45:
                ent_score = 8.0
            else:
                ent_score = 0.0
    elif rec_a.clean_description and rec_b.clean_description:
        desc_sim = fuzz.token_set_ratio(rec_a.clean_description, rec_b.clean_description)
        if desc_sim >= 75:
            ent_score = 12.0
        elif desc_sim >= 50:
            ent_score = 8.0
    
    score_breakdown["entity_score"] = ent_score

    total_score = round(ref_score + amt_score + date_score + ent_score, 1)

    # Determine match category
    if ref_score >= 35 and amt_score == 30 and days_diff <= 1 and ent_score >= 8:
        category = "EXACT_MATCH"
    elif ref_score >= 25 and amt_score == 30:
        category = "FUZZY_MATCH"
    elif ref_score >= 30 and days_diff > 2 and amt_score == 30:
        category = "DATE_LAG"
    elif ref_score >= 30 and amt_diff > 0.05:
        category = "AMOUNT_MISMATCH"
    else:
        category = "PARTIAL_MATCH"

    return total_score, score_breakdown, category, amt_diff, days_diff

class ReconciliationEngine:
    def __init__(self, confidence_threshold: float = 80.0, ambiguity_delta: float = 6.0):
        self.confidence_threshold = confidence_threshold
        self.ambiguity_delta = ambiguity_delta

    def run_reconciliation(
        self,
        records: List[NormalizedRecord]
    ) -> Tuple[List[ReconciliationMatch], List[ReconciliationException], ReconciliationSummary]:
        start_time = time.time()
        
        # Deterministically order sources, prioritizing ledger / source_a as primary
        unique_sources = sorted(list(set(r.source for r in records)))
        if any("ledger" in s.lower() or "source_a" in s.lower() for s in unique_sources):
            primary_source = next(s for s in unique_sources if "ledger" in s.lower() or "source_a" in s.lower())
        else:
            primary_source = unique_sources[0] if unique_sources else "source_a"

        records_a = [r for r in records if r.source == primary_source]
        records_b = [r for r in records if r.source != primary_source]

        # In case records came with identical source or multi-source, split evenly
        if not records_b and len(records) > 1:
            half = len(records) // 2
            records_a = records[:half]
            records_b = records[half:]

        # Check for intra-source duplicates first in records_a
        seen_refs_a: Dict[str, str] = {}
        duplicate_a_ids = set()
        for r in records_a:
            ref_key = f"{r.clean_reference_id}_{r.amount}" if r.clean_reference_id else f"{r.record_id}_{r.amount}"
            if ref_key in seen_refs_a:
                duplicate_a_ids.add(r.record_id)
            else:
                seen_refs_a[ref_key] = r.record_id

        matched_b_ids = set()
        matches: List[ReconciliationMatch] = []
        exceptions: List[ReconciliationException] = []

        total_amount_processed = sum(abs(r.amount) for r in records)
        total_amount_matched = 0.0
        total_amount_discrepancy = 0.0

        for rec_a in records_a:
            # Handle duplicate check
            if rec_a.record_id in duplicate_a_ids:
                exc = ReconciliationException(
                    exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
                    record_id=rec_a.record_id,
                    source=rec_a.source,
                    amount=rec_a.amount,
                    entity=rec_a.raw_entity,
                    date=rec_a.iso_date,
                    reason_code="DUPLICATE",
                    confidence=0.0,
                    decision="UNRESOLVED",
                    explanation=f"Duplicate entry detected in ledger with reference {rec_a.raw_reference_id} and amount ${rec_a.amount:,.2f}.",
                    amount_discrepancy=0.0,
                    candidates=[],
                    raw_data=rec_a.raw_data
                )
                exceptions.append(exc)
                continue

            # Candidate Generation & Scoring against records_b
            candidates: List[CandidateMatch] = []
            for rec_b in records_b:
                score, breakdown, category, amt_diff, days_diff = score_record_pair(rec_a, rec_b)
                if score >= 40.0:  # Candidate filter threshold
                    candidates.append(CandidateMatch(
                        target_record_id=rec_b.record_id,
                        target_source=rec_b.source,
                        target_amount=rec_b.amount,
                        target_date=rec_b.iso_date,
                        target_entity=rec_b.raw_entity,
                        confidence_score=score,
                        score_breakdown=breakdown,
                        match_category=category,
                        amount_diff=amt_diff,
                        date_diff_days=days_diff,
                        notes=f"Ref: {breakdown['reference_score']}, Amt: {breakdown['amount_score']}, Date: {breakdown['date_score']}, Ent: {breakdown['entity_score']}"
                    ))

            # Sort candidates by score descending
            candidates.sort(key=lambda c: c.confidence_score, reverse=True)

            if not candidates:
                # No counterpart found
                exc = ReconciliationException(
                    exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
                    record_id=rec_a.record_id,
                    source=rec_a.source,
                    amount=rec_a.amount,
                    entity=rec_a.raw_entity,
                    date=rec_a.iso_date,
                    reason_code="MISSING_COUNTERPART",
                    confidence=0.0,
                    decision="UNRESOLVED",
                    explanation=f"No matching counterpart transaction found in bank/settlement records for reference {rec_a.raw_reference_id or rec_a.record_id} (${rec_a.amount:,.2f}).",
                    amount_discrepancy=0.0,
                    candidates=[],
                    raw_data=rec_a.raw_data
                )
                exceptions.append(exc)
                continue

            top_candidate = candidates[0]

            # Check for Ambiguous Multiple Candidates
            if len(candidates) > 1:
                second_candidate = candidates[1]
                if top_candidate.confidence_score >= 65.0 and (top_candidate.confidence_score - second_candidate.confidence_score) < self.ambiguity_delta and top_candidate.confidence_score < 98.0:
                    exc = ReconciliationException(
                        exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
                        record_id=rec_a.record_id,
                        source=rec_a.source,
                        amount=rec_a.amount,
                        entity=rec_a.raw_entity,
                        date=rec_a.iso_date,
                        reason_code="AMBIGUOUS_CANDIDATES",
                        confidence=top_candidate.confidence_score,
                        decision="UNRESOLVED",
                        explanation=f"Multiple ambiguous candidates found with close confidence ({top_candidate.confidence_score:.1f}% vs {second_candidate.confidence_score:.1f}%). Insufficient evidence to safely auto-select.",
                        amount_discrepancy=top_candidate.amount_diff,
                        candidates=candidates[:3],
                        raw_data=rec_a.raw_data
                    )
                    exceptions.append(exc)
                    continue

            # Check for Amount Discrepancy (Strong reference match +30/40, but amount mismatch)
            if top_candidate.score_breakdown["reference_score"] >= 30.0 and top_candidate.amount_diff > 0.05:
                total_amount_discrepancy += top_candidate.amount_diff
                exc = ReconciliationException(
                    exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
                    record_id=rec_a.record_id,
                    source=rec_a.source,
                    amount=rec_a.amount,
                    entity=rec_a.raw_entity,
                    date=rec_a.iso_date,
                    reason_code="AMOUNT_MISMATCH",
                    confidence=top_candidate.confidence_score,
                    decision="UNRESOLVED",
                    explanation=f"Amount mismatch on reference {rec_a.raw_reference_id}: Ledger is ${rec_a.amount:,.2f} vs Bank candidate {top_candidate.target_record_id} is ${top_candidate.target_amount:,.2f} (Discrepancy: ${top_candidate.amount_diff:,.2f}). Possible fee or partial payment.",
                    amount_discrepancy=top_candidate.amount_diff,
                    candidates=candidates[:2],
                    raw_data=rec_a.raw_data
                )
                exceptions.append(exc)
                continue

            # High confidence Match
            if top_candidate.confidence_score >= self.confidence_threshold:
                match_id = f"MATCH-{uuid.uuid4().hex[:8].upper()}"
                matched_b_ids.add(top_candidate.target_record_id)
                total_amount_matched += rec_a.amount

                m = ReconciliationMatch(
                    match_id=match_id,
                    record_id_a=rec_a.record_id,
                    record_id_b=top_candidate.target_record_id,
                    source_a=rec_a.source,
                    source_b=top_candidate.target_source,
                    amount_a=rec_a.amount,
                    amount_b=top_candidate.target_amount,
                    date_a=rec_a.iso_date,
                    date_b=top_candidate.target_date,
                    entity_a=rec_a.raw_entity,
                    entity_b=top_candidate.target_entity,
                    confidence_score=top_candidate.confidence_score,
                    match_category=top_candidate.match_category,
                    status="MATCHED",
                    score_breakdown=top_candidate.score_breakdown,
                    explanation=f"Matched with {top_candidate.confidence_score:.1f}% confidence ({top_candidate.match_category})."
                )
                matches.append(m)
            else:
                # Low confidence candidate
                exc = ReconciliationException(
                    exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
                    record_id=rec_a.record_id,
                    source=rec_a.source,
                    amount=rec_a.amount,
                    entity=rec_a.raw_entity,
                    date=rec_a.iso_date,
                    reason_code="LOW_CONFIDENCE",
                    confidence=top_candidate.confidence_score,
                    decision="UNRESOLVED",
                    explanation=f"Best candidate {top_candidate.target_record_id} scored only {top_candidate.confidence_score:.1f}%, below the required {self.confidence_threshold}% threshold.",
                    amount_discrepancy=top_candidate.amount_diff,
                    candidates=candidates[:2],
                    raw_data=rec_a.raw_data
                )
                exceptions.append(exc)

        # Check for un-matched records in Source B (Unrecorded bank entries/fees)
        for rec_b in records_b:
            if rec_b.record_id not in matched_b_ids:
                # If rec_b was not matched to any rec_a
                exc = ReconciliationException(
                    exception_id=f"EXC-{uuid.uuid4().hex[:8].upper()}",
                    record_id=rec_b.record_id,
                    source=rec_b.source,
                    amount=rec_b.amount,
                    entity=rec_b.raw_entity,
                    date=rec_b.iso_date,
                    reason_code="MISSING_COUNTERPART",
                    confidence=0.0,
                    decision="UNRESOLVED",
                    explanation=f"Bank transaction {rec_b.record_id} (${rec_b.amount:,.2f}) for '{rec_b.raw_entity or rec_b.clean_description}' is unrecorded in the internal ledger.",
                    amount_discrepancy=0.0,
                    candidates=[],
                    raw_data=rec_b.raw_data
                )
                exceptions.append(exc)

        elapsed = max(time.time() - start_time, 0.001)
        total_records_processed = len(records)
        unresolved_exceptions_count = len(exceptions)
        match_rate = round((len(matches) / max(len(records_a), 1)) * 100.0, 2)
        throughput = round(total_records_processed / elapsed, 2)

        summary = ReconciliationSummary(
            total_records_processed=total_records_processed,
            matched_count=len(matches),
            unmatched_count=unresolved_exceptions_count,
            unresolved_exceptions_count=unresolved_exceptions_count,
            match_rate=match_rate,
            total_amount_processed=round(total_amount_processed, 2),
            total_amount_matched=round(total_amount_matched, 2),
            total_amount_discrepancy=round(total_amount_discrepancy, 2),
            processing_time_sec=round(elapsed, 4),
            throughput_records_sec=throughput
        )

        return matches, exceptions, summary
