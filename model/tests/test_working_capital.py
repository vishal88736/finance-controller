"""
Tests for deterministic working-capital service
(model/services/working_capital.py).
"""
import json
import uuid

import pytest

from model.database.models import Thread, Document, DocumentRecord, ReconciliationResult
from model.services.working_capital import (
    compute_dso,
    compute_dio,
    compute_dpo,
    compute_ccc,
    working_capital,
)


def test_compute_dso_dio_dpo_ccc_golden():
    assert compute_dso(30000, 100000, 365) == 109.5
    assert compute_dio(50000, 200000, 365) == 91.25
    assert compute_dpo(40000, 200000, 365) == 73.0
    assert compute_ccc(109.5, 91.25, 73.0) == 127.75


def test_compute_functions_guard_division_by_zero():
    assert compute_dso(100, 0) is None
    assert compute_dio(100, None) is None
    assert compute_dpo(100, 0) is None
    assert compute_ccc(None, 10, 5) is None


def test_working_capital_insufficient_data(db_session):
    th = Thread(id=f"thr_wc_empty_{uuid.uuid4().hex[:8]}", title="WC empty")
    db_session.add(th)
    db_session.commit()
    res = working_capital.run_analysis(db_session, th.id)
    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["dso_days"] is None


def test_working_capital_derives_metrics(db_session):
    th = Thread(id=f"thr_wc_{uuid.uuid4().hex[:8]}", title="WC")
    db_session.add(th)
    doc = Document(
        id=f"doc_wc_{uuid.uuid4().hex[:8]}", thread_id=th.id, filename="ledger.csv",
        file_type="csv", content_hash_sha256=f"wc_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)
    db_session.add_all([
        DocumentRecord(id=f"dr_wc_1_{uuid.uuid4().hex[:8]}", document_id=doc.id, thread_id=th.id,
                       record_id="IN-1", source="ledger", amount=1000.0),
        DocumentRecord(id=f"dr_wc_2_{uuid.uuid4().hex[:8]}", document_id=doc.id, thread_id=th.id,
                       record_id="OUT-1", source="ledger", amount=-400.0),
    ])
    db_session.commit()

    res = working_capital.run_analysis(db_session, th.id)
    assert res["status"] == "COMPLETED"
    assert res["total_inflows"] == 1000.0
    assert res["total_outflows"] == 400.0
    # Both inflow records unmatched -> receivables outstanding == total inflows.
    assert res["receivables_outstanding"] == 1000.0
    assert res["payables_outstanding"] == 400.0
    # DIO unavailable (no inventory) but DSO/DPO/partial CCC are derivable.
    assert res["dio_days"] is None
    assert res["dso_days"] is not None
    assert res["dpo_days"] is not None