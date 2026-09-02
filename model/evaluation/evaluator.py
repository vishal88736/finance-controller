"""
Reconciliation Evaluation & Benchmarking Module.
Compares actual agent reconciliation output against known ground truth.
Calculates Precision, Recall, Accuracy, F1-Score, Processing Time, and Throughput.
"""

import json
import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from ..reconciliation.models import (
    ReconciliationMatch,
    ReconciliationException,
    ReconciliationSummary
)

class EvaluationReport(BaseModel):
    total_ground_truth_cases: int
    records_processed: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    match_rate: float
    processing_time_sec: float
    throughput_records_sec: float
    category_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    detailed_metrics_json: Dict[str, Any] = Field(default_factory=dict)

def evaluate_reconciliation(
    matches: List[ReconciliationMatch],
    exceptions: List[ReconciliationException],
    summary: ReconciliationSummary,
    ground_truth_path_or_dict: Any
) -> EvaluationReport:
    """
    Evaluates matches and exceptions against an EXPLICIT ground truth source.

    Security: the caller must pass the ground truth explicitly (dict or path).
    This function never silently substitutes the bundled benchmark file — if
    the given path does not exist, it raises rather than fabricating metrics.
    """
    if isinstance(ground_truth_path_or_dict, str):
        if not os.path.exists(ground_truth_path_or_dict):
            raise FileNotFoundError(
                f"Ground truth file not found: {ground_truth_path_or_dict}. "
                "Refusing to silently fall back to bundled benchmark data."
            )
        with open(ground_truth_path_or_dict, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
    else:
        gt_data = ground_truth_path_or_dict

    gt_cases: Dict[str, Any] = gt_data.get("cases", {})
    total_gt = len(gt_cases)

    # Build bidirectional lookup of actual match decisions
    actual_matches: Dict[str, str] = {}
    for m in matches:
        actual_matches[m.record_id_a] = m.record_id_b
        actual_matches[m.record_id_b] = m.record_id_a

    # Map exception record_id -> reason_code
    actual_exceptions: Dict[str, str] = {}
    for e in exceptions:
        actual_exceptions[e.record_id] = e.reason_code

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    category_stats: Dict[str, Dict[str, int]] = {}

    for rec_id, gt in gt_cases.items():
        expected_status = gt.get("ground_truth_status")
        expected_target = gt.get("matched_record_id")
        category = gt.get("category", "UNKNOWN")

        if category not in category_stats:
            category_stats[category] = {"total": 0, "correct": 0, "errors": 0}
        category_stats[category]["total"] += 1

        is_actual_match = rec_id in actual_matches
        actual_target = actual_matches.get(rec_id)
        is_actual_exception = rec_id in actual_exceptions

        if expected_status == "MATCHED":
            # True Positive if correctly matched to expected target
            if is_actual_match and actual_target == expected_target:
                tp += 1
                category_stats[category]["correct"] += 1
            elif is_actual_match and actual_target != expected_target:
                fp += 1  # Matched to wrong target
                category_stats[category]["errors"] += 1
            else:
                fn += 1  # Should have matched, but was left unmatched or exception
                category_stats[category]["errors"] += 1

        elif expected_status in ["AMOUNT_MISMATCH", "UNRESOLVED_AMBIGUOUS", "DUPLICATE", "MISSING_RECORD"]:
            # Ground truth expected exception / unresolved
            if is_actual_exception:
                tn += 1
                category_stats[category]["correct"] += 1
            elif is_actual_match:
                fp += 1  # Incorrectly forced a false match!
                category_stats[category]["errors"] += 1
            else:
                tn += 1
                category_stats[category]["correct"] += 1

    precision = round((tp / max(tp + fp, 1)) * 100.0, 2)
    recall = round((tp / max(tp + fn, 1)) * 100.0, 2)
    if (precision + recall) > 0:
        f1 = round((2 * precision * recall) / (precision + recall), 2)
    else:
        f1 = 0.0
    accuracy = round(((tp + tn) / max(total_gt, 1)) * 100.0, 2)

    return EvaluationReport(
        total_ground_truth_cases=total_gt,
        records_processed=summary.total_records_processed,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        accuracy=accuracy,
        match_rate=summary.match_rate,
        processing_time_sec=summary.processing_time_sec,
        throughput_records_sec=summary.throughput_records_sec,
        category_breakdown=category_stats,
        detailed_metrics_json={
            "confusion_matrix": {
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "TN": tn
            },
            "category_performance": category_stats
        }
    )
