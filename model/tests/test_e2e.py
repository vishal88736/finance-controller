"""
End-to-end test: generate synthetic data → reconcile → evaluate → print metrics.
This is the most important integration test.
"""

import os
import json
import pytest
import time

from ..synthetic.generator import generate_synthetic_dataset
from ..ingestion.parser import parse_file
from ..ingestion.normalizer import NormalizedRecord
from ..reconciliation.engine import ReconciliationEngine
from ..evaluation.evaluator import evaluate_reconciliation


def test_end_to_end_reconciliation(tmp_path):
    """
    Full pipeline:
        1. Generate 200+ synthetic records with ground truth
        2. Parse source files
        3. Normalize records
        4. Run deterministic reconciliation
        5. Evaluate against ground truth
        6. Print metrics

    This test MUST produce real metrics from actual execution.
    """
    output_dir = str(tmp_path)

    # ---- Step 1: Generate synthetic data ----
    gen_result = generate_synthetic_dataset(output_dir, total_records=200)
    assert gen_result["total_source_a"] >= 180
    assert gen_result["total_source_b"] >= 180
    assert gen_result["ground_truth_cases"] >= 180

    # ---- Step 2: Parse source files ----
    records_a = parse_file(gen_result["source_a_path"], "source_a_ledger.csv", "source_a_ledger")
    records_b = parse_file(gen_result["source_b_path"], "source_b_bank.csv", "source_b_bank")

    all_records = records_a + records_b
    assert len(all_records) > 350, f"Expected 350+ records, got {len(all_records)}"

    # ---- Step 3: Normalization is done by parse_file ----
    # Verify records are properly normalized
    for rec in all_records[:5]:
        assert rec.record_id, "record_id must not be empty"
        assert rec.amount != 0.0, "amount must not be zero"
        assert rec.iso_date, "iso_date must not be empty"

    # ---- Step 4: Run reconciliation ----
    start = time.perf_counter()
    engine = ReconciliationEngine(confidence_threshold=80.0, ambiguity_delta=6.0)
    matches, exceptions, summary = engine.run_reconciliation(all_records)
    elapsed = time.perf_counter() - start

    # Basic sanity checks
    assert len(matches) > 100, f"Expected 100+ matches, got {len(matches)}"
    assert len(exceptions) > 10, f"Expected 10+ exceptions, got {len(exceptions)}"
    assert summary.match_rate > 50.0, f"Match rate {summary.match_rate}% too low"
    assert summary.throughput_records_sec > 10.0, f"Throughput too low"

    # ---- Step 5: Evaluate against ground truth ----
    eval_report = evaluate_reconciliation(
        matches, exceptions, summary, gen_result["ground_truth_path"]
    )

    # ---- Step 6: Print metrics ----
    print("\n" + "=" * 60)
    print("  END-TO-END RECONCILIATION BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Total records:       {summary.total_records_processed}")
    print(f"  Records processed:   {summary.total_records_processed}")
    print(f"  Correct matches:     {eval_report.true_positives}")
    print(f"  Incorrect matches:   {eval_report.false_positives}")
    print(f"  Unresolved:          {eval_report.false_negatives}")
    print(f"  Exceptions caught:   {eval_report.true_negatives}")
    print(f"")
    print(f"  Match rate:          {summary.match_rate:.1f}%")
    print(f"  Accuracy:            {eval_report.accuracy:.1f}%")
    print(f"  Precision:           {eval_report.precision:.1f}%")
    print(f"  Recall:              {eval_report.recall:.1f}%")
    print(f"  F1-Score:            {eval_report.f1_score:.1f}%")
    print(f"")
    print(f"  Processing time:     {elapsed:.4f} sec")
    print(f"  Throughput:          {summary.total_records_processed / elapsed:.0f} records/sec")
    print(f"")
    print(f"  Category breakdown:")
    for cat, stats in eval_report.category_breakdown.items():
        print(f"    {cat}: {stats['correct']}/{stats['total']} correct")
    print("=" * 60)

    # Quality assertions
    assert eval_report.accuracy > 80.0, f"Accuracy {eval_report.accuracy}% below 80%"
    assert eval_report.precision > 90.0, f"Precision {eval_report.precision}% below 90%"
    assert eval_report.false_positives == 0, f"Expected 0 false positives, got {eval_report.false_positives}"

    # Verify exception categories exist
    exception_reasons = set(e.reason_code for e in exceptions)
    assert "AMOUNT_MISMATCH" in exception_reasons, "Should detect amount mismatches"
    assert "MISSING_COUNTERPART" in exception_reasons, "Should detect missing records"
