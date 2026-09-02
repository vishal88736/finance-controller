import os
import pytest
from ..agents.reconciliation_graph import reconciliation_graph
from ..agents.qa_graph import qa_graph
from ..synthetic.generator import generate_synthetic_dataset
from ..database.db import init_db

def test_full_reconciliation_agent_workflow(tmp_path):
    init_db()
    synth_dir = os.path.join(os.path.dirname(__file__), "..", "synthetic")
    generate_synthetic_dataset(synth_dir, total_records=200)

    fa = os.path.join(synth_dir, "source_a_ledger.csv")
    fb = os.path.join(synth_dir, "source_b_bank.csv")

    initial_state = {
        "run_id": "TEST-RUN-001",
        "user_request": "Reconcile these transactions and flag discrepancies.",
        "uploaded_files": [
            {"path": fa, "filename": "source_a_ledger.csv", "source_label": "source_a_ledger"},
            {"path": fb, "filename": "source_b_bank.csv", "source_label": "source_b_bank"}
        ],
        "documents": [],
        "normalized_records": [],
        "candidates": [],
        "matches": [],
        "exceptions": [],
        "metrics": {},
        "final_report": {},
        "current_step": "init",
        "step_progress": [],
        "error": None
    }

    output = reconciliation_graph.invoke(initial_state)

    assert len(output["matches"]) > 100
    assert len(output["exceptions"]) > 10
    assert output["final_report"]["match_rate"] > 70.0
    assert output["final_report"]["throughput_records_sec"] > 10.0
    # No explicit ground truth supplied → must NOT fabricate evaluation
    assert output["final_report"]["evaluated"] is False
    assert output["final_report"]["accuracy"] is None
    assert output["final_report"]["precision"] is None
    assert output["final_report"]["recall"] is None

def test_qa_agent_metric_response():
    init_db()
    qa_input = {
        "thread_id": "thr_missing",
        "run_id": "TEST-RUN-001",
        "question": "What is our current match rate and accuracy?",
        "guardrail_passed": True,
        "guardrail_refusal": None,
        "guardrail_layer": None,
        "query_type": "GENERAL",
        "extracted_entities": [],
        "extracted_record_ids": [],
        "retrieved_records": [],
        "retrieved_exceptions": [],
        "retrieved_metrics": {},
        "retrieved_documents": [],
        "evidence": {},
        "tools_called": [],
        "answer": "",
        "answer_source": "deterministic",
        "db_session": None,
    }
    # No DB session passed → graph must refuse to query rather than open its own
    output = qa_graph.invoke(qa_input)
    assert output["answer"] is not None
    assert "database session" in output["answer"].lower()
