"""
Unit tests for deterministic Tax-Line Matcher service.
Validates:
- Exact tax match (18% GST calculation)
- Tax rate mismatch (12% vs 18%)
- Missing tax lines
- Tolerance on rounding
- Empty thread handling
- Thread isolation
"""

import json
import uuid
import pytest
from model.database.models import Thread, Document, DocumentRecord, TaxMatchResult
from model.services.tax_matcher import tax_matcher


def test_tax_match_empty_thread(db_session):
    """Empty thread returns NO_DATA without errors."""
    th_id = f"thr_tax_mt_{uuid.uuid4().hex[:8]}"
    th = Thread(id=th_id, title="Tax Empty")
    db_session.add(th)
    db_session.commit()

    res = tax_matcher.run_tax_matching(db_session, th.id)
    assert res["status"] == "NO_DATA"
    assert res["total_records"] == 0
    assert len(res["tax_lines"]) == 0


def test_tax_match_calculations(db_session):
    """Validates MATCH, MISMATCH, and MISSING status classifications."""
    thread_id = f"thr_tax_calc_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Tax Calc Test")
    db_session.add(th)

    doc = Document(
        id=f"doc_tax_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="invoices.csv",
        file_type="csv",
        content_hash_sha256=f"tax_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)

    # 1. Exact Match: 1000.00 at 18% -> 180.00 tax
    rec1 = DocumentRecord(
        id=f"dr_tax_1_{uuid.uuid4().hex[:8]}",
        document_id=doc.id,
        thread_id=thread_id,
        record_id="INV-001",
        source="invoices",
        amount=1000.0,
        raw_data_json=json.dumps({"taxable_amount": 1000.0, "tax_amount": 180.0, "tax_rate": 0.18}),
    )
    # 2. Mismatch: 1000.00 at 18% expected 180.00, but reported 120.00
    rec2 = DocumentRecord(
        id=f"dr_tax_2_{uuid.uuid4().hex[:8]}",
        document_id=doc.id,
        thread_id=thread_id,
        record_id="INV-002",
        source="invoices",
        amount=1000.0,
        raw_data_json=json.dumps({"taxable_amount": 1000.0, "tax_amount": 120.0, "tax_rate": 0.18}),
    )
    # 3. Missing Tax: 500.00 at 18% expected 90.00, but tax_amount is 0.0
    rec3 = DocumentRecord(
        id=f"dr_tax_3_{uuid.uuid4().hex[:8]}",
        document_id=doc.id,
        thread_id=thread_id,
        record_id="INV-003",
        source="invoices",
        amount=500.0,
        raw_data_json=json.dumps({"taxable_amount": 500.0, "tax_amount": 0.0, "tax_rate": 0.18}),
    )

    db_session.add_all([rec1, rec2, rec3])
    db_session.commit()

    res = tax_matcher.run_tax_matching(db_session, thread_id, tax_rate=0.18)
    assert res["status"] == "COMPLETED"
    assert res["total_records"] == 3
    assert res["matched_count"] == 1
    assert res["mismatched_count"] == 1
    assert res["missing_count"] == 1
    assert res["total_tax_expected"] == 450.0  # 180 + 180 + 90
    assert res["total_tax_reported"] == 300.0  # 180 + 120 + 0
    assert res["total_tax_discrepancy"] == 150.0  # 0 + 60 + 90


def test_tax_match_thread_isolation(db_session):
    """Thread B must never see tax records from Thread A."""
    th_a = Thread(id=f"thr_tax_a_{uuid.uuid4().hex[:8]}", title="Thread A")
    th_b = Thread(id=f"thr_tax_b_{uuid.uuid4().hex[:8]}", title="Thread B")
    db_session.add_all([th_a, th_b])

    doc_a = Document(id=f"doc_tax_a_{uuid.uuid4().hex[:8]}", thread_id=th_a.id, filename="a.csv", file_type="csv", content_hash_sha256="h_tax_a")
    db_session.add(doc_a)
    rec_a = DocumentRecord(
        id=f"dr_tax_iso_a_{uuid.uuid4().hex[:8]}", document_id=doc_a.id, thread_id=th_a.id,
        record_id="INV_A", source="invoices", amount=2000.0,
        raw_data_json=json.dumps({"taxable_amount": 2000.0, "tax_amount": 360.0, "tax_rate": 0.18})
    )
    db_session.add(rec_a)
    db_session.commit()

    # Thread B has no documents
    res_b = tax_matcher.run_tax_matching(db_session, th_b.id)
    assert res_b["status"] == "NO_DATA"
    assert res_b["total_records"] == 0

    # Thread A has 1 matched record
    res_a = tax_matcher.run_tax_matching(db_session, th_a.id)
    assert res_a["status"] == "COMPLETED"
    assert res_a["matched_count"] == 1


def test_tax_non_applicable_records_excluded(db_session):
    """Records without any tax evidence must be NOT_TAX_APPLICABLE, not tax lines."""
    thread_id = f"thr_tax_na_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Tax NA")
    db_session.add(th)
    doc = Document(
        id=f"doc_tax_na_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="bank_statement.csv",
        file_type="csv",
        content_hash_sha256=f"tax_na_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)
    rec = DocumentRecord(
        id=f"dr_tax_na_{uuid.uuid4().hex[:8]}",
        document_id=doc.id,
        thread_id=thread_id,
        record_id="BNK-001",
        source="bank",
        amount=1500.0,
        raw_data_json=json.dumps({"reference_id": "INV-1", "amount": 1500.0}),
    )
    db_session.add(doc)
    db_session.add(rec)
    db_session.commit()

    res = tax_matcher.run_tax_matching(db_session, thread_id, tax_rate=0.18)
    assert res["status"] == "COMPLETED"
    assert res["tax_eligible_count"] == 0
    assert res["not_applicable_count"] == 1
    assert res["total_tax_expected"] is None
    assert res["tax_match_rate"] == 0.0
    assert res["tax_lines"][0]["status"] == "NOT_TAX_APPLICABLE"


def test_tax_net_variance_signed_and_absolute(db_session):
    """Signed net variance and absolute cumulative variance must be distinct."""
    thread_id = f"thr_tax_var_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Tax Var")
    db_session.add(th)
    doc = Document(
        id=f"doc_tax_var_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="invoices.csv",
        file_type="csv",
        content_hash_sha256=f"tax_var_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)
    rec = DocumentRecord(
        id=f"dr_tax_var_{uuid.uuid4().hex[:8]}",
        document_id=doc.id,
        thread_id=thread_id,
        record_id="INV-VAR",
        source="invoices",
        amount=1000.0,
        raw_data_json=json.dumps({"taxable_amount": 1000.0, "tax_amount": 120.0, "tax_rate": 0.18}),
    )
    db_session.add(doc)
    db_session.add(rec)
    db_session.commit()

    res = tax_matcher.run_tax_matching(db_session, thread_id, tax_rate=0.18)
    assert res["total_tax_discrepancy"] == 60.0   # absolute
    assert res["net_tax_variance"] == -60.0        # signed (reported - expected)


def test_tax_source_rate_overrides_default(db_session):
    """A source-level tax_rate must override the default statutory rate."""
    thread_id = f"thr_tax_src_{uuid.uuid4().hex[:8]}"
    th = Thread(id=thread_id, title="Tax Src")
    db_session.add(th)
    doc = Document(
        id=f"doc_tax_src_{uuid.uuid4().hex[:8]}",
        thread_id=thread_id,
        filename="invoices.csv",
        file_type="csv",
        content_hash_sha256=f"tax_src_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(doc)
    # Source specifies 12% (0.12); default passed in is 18%.
    db_session.add(DocumentRecord(
        id=f"dr_tax_src_{uuid.uuid4().hex[:8]}",
        document_id=doc.id,
        thread_id=thread_id,
        record_id="INV-SRC",
        source="invoices",
        amount=1000.0,
        raw_data_json=json.dumps({"taxable_amount": 1000.0, "tax_amount": 120.0, "tax_rate": 0.12}),
    ))
    db_session.commit()

    res = tax_matcher.run_tax_matching(db_session, thread_id, tax_rate=0.18)

    assert res["status"] == "COMPLETED"
    assert res["matched_count"] == 1
    line = res["tax_lines"][0]
    assert line["status"] == "MATCH"
    assert line["tax_rate"] == 0.12
    assert line["tax_rate_source"] == "SOURCE_DATA"
    assert line["expected_tax"] == 120.0  # 1000 * 0.12, NOT 1000 * 0.18
