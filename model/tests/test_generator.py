import os
import json
import pytest
from ..synthetic.generator import generate_synthetic_dataset

def test_generate_synthetic_dataset(tmp_path):
    out_dir = str(tmp_path)
    result = generate_synthetic_dataset(out_dir, total_records=200)

    assert os.path.exists(result["source_a_path"])
    assert os.path.exists(result["source_b_path"])
    assert os.path.exists(result["ground_truth_path"])

    assert result["total_source_a"] >= 180
    assert result["total_source_b"] >= 180
    assert result["ground_truth_cases"] >= 180

    with open(result["ground_truth_path"], "r") as f:
        gt = json.load(f)
    
    assert "cases" in gt
    assert len(gt["cases"]) >= 180
    assert "exact_matches" in gt["summary"]
    assert gt["summary"]["exact_matches"] == 120
