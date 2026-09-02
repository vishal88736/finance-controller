"""
Shared fixtures for the AI Finance Controller test suite.

Provides:
- isolated in-memory DB sessions
- FastAPI TestClient wired to a temp DB + temp upload dir
- small real CSV/XLSX/JSON document factories
"""

import io
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from model.database.models import Base


@pytest.fixture
def db_session():
    """Fresh in-memory DB session for repository/service-level tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """
    FastAPI TestClient with dependency overrides:
    - isolated temp SQLite file DB
    - isolated temp upload dir
    - LangSmith tracing disabled (deterministic tests)
    """
    from fastapi.testclient import TestClient

    db_file = tmp_path / "test_finance.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)

    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 30.0},
    )
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    from model.database.db import get_db
    from model.app import main as app_main

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.delenv("LANGSMITH_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    app_main.UPLOAD_DIR = str(upload_dir)
    app = app_main.app
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────
# Document factories (small, realistic financial data)
# ─────────────────────────────────────────────────────────────

LEDGER_CSV = (
    b"record_id,reference,amount,date,entity,description\n"
    b"TX_001,INV_1001,1500.00,2026-08-10,Alpha Logistics,Warehouse freight payment\n"
    b"TX_002,INV_1002,2450.00,2026-08-11,Beta Software,Cloud server subscription\n"
    b"TX_003,INV_1003,5000.00,2026-08-12,Gamma Marketing,Ad campaign spend\n"
)

BANK_CSV = (
    b"record_id,reference,amount,date,entity,description\n"
    b"BNK_001,INV_1001,1500.00,2026-08-10,Alpha Logistics,Direct deposit Alpha\n"
    b"BNK_002,INV_1002,2388.75,2026-08-11,Beta Software,Card payout fee deducted\n"
    b"BNK_999,INV_9999,800.00,2026-08-15,Delta Services,Unrecorded bank credit\n"
)


@pytest.fixture
def ledger_csv():
    return LEDGER_CSV


@pytest.fixture
def bank_csv():
    return BANK_CSV


def make_xlsx(rows):
    """Build a real XLSX file from row dicts."""
    import pandas as pd

    buf = io.BytesIO()
    df = pd.DataFrame(rows)
    df.to_excel(buf, index=False)
    return buf.getvalue()


def make_json_doc(rows):
    import json

    return json.dumps({"records": rows}).encode()
