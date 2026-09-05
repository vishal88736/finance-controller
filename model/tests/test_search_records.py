"""
Tests for the deterministic keyword record search tool (search_records_tool).
"""
import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from model.database.models import Base, Thread, Document, DocumentRecord
from model.tools.qa_tools import search_records_tool


@pytest.fixture
def search_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    th = Thread(id="thr_search", title="Search")
    session.add(th)
    doc = Document(id="doc_s", thread_id="thr_search", filename="f.csv", file_type="csv", content_hash_sha256="h_s")
    session.add(doc)
    session.add_all([
        DocumentRecord(id="dr_s1", document_id="doc_s", thread_id="thr_search",
                       record_id="INV-1", source="invoices", amount=1500.0,
                       entity="Alpha Logistics", description="Warehouse freight"),
        DocumentRecord(id="dr_s2", document_id="doc_s", thread_id="thr_search",
                       record_id="INV-2", source="invoices", amount=2450.0,
                       entity="Beta Software", description="Cloud SaaS subscription"),
        DocumentRecord(id="dr_s3", document_id="doc_s", thread_id="thr_search",
                       record_id="INV-3", source="invoices", amount=5000.0,
                       entity="Gamma Ads", description="Marketing campaign"),
    ])
    session.commit()
    yield session
    session.close()


def test_search_records_finds_citation(search_db):
    res = search_records_tool(search_db, "thr_search", "warehouse freight", limit=5)
    assert res["status"] == "OK"
    assert res["result_count"] >= 1
    assert any(r["record_id"] == "INV-1" for r in res["results"])
    r = res["results"][0]
    assert r["description"] == "Warehouse freight"


def test_search_records_refuses_on_no_match(search_db):
    res = search_records_tool(search_db, "thr_search", "rocket launch pad", limit=5)
    assert res["status"] == "NO_MATCH"
    assert res["results"] == []


def test_search_records_thraad_scoped(search_db):
    # A query matching record text but from another thread returns no data.
    res = search_records_tool(search_db, "thr_OTHER", "warehouse")
    assert res["status"] == "NO_DATA"