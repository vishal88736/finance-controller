"""
Tests for Thread Lifecycle and Data Isolation.
Verifies:
- Thread creation, listing, retrieval, renaming, deletion
- Message persistence scoped to thread
- Strict thread isolation (Thread A data not leaked to Thread B)
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from model.database.models import Base, Thread, Document, Message, ReconciliationResult
from model.database.repositories import (
    create_thread,
    get_thread,
    list_threads,
    update_thread_title,
    delete_thread,
    add_message,
    get_thread_messages,
    get_thread_matches
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_thread_crud(test_db):
    # 1. Create
    t1 = create_thread(test_db, title="Q3 Settlement Reconciliation")
    assert t1.id.startswith("thr_")
    assert t1.title == "Q3 Settlement Reconciliation"

    # 2. Retrieve
    retrieved = get_thread(test_db, t1.id)
    assert retrieved is not None
    assert retrieved.id == t1.id

    # 3. Update title
    updated = update_thread_title(test_db, t1.id, "Q3 Reconciled - Final")
    assert updated.title == "Q3 Reconciled - Final"

    # 4. List
    t2 = create_thread(test_db, title="Invoice Discrepancies")
    threads = list_threads(test_db)
    assert len(threads) == 2

    # 5. Delete
    deleted = delete_thread(test_db, t1.id)
    assert deleted is True
    assert get_thread(test_db, t1.id) is None
    assert len(list_threads(test_db)) == 1


def test_thread_messages(test_db):
    t = create_thread(test_db, title="Investigation Thread")
    msg1 = add_message(test_db, t.id, role="user", content="Why did TXN-101 fail?")
    msg2 = add_message(test_db, t.id, role="assistant", content="TXN-101 has a $15.00 wire deduction.")

    messages = get_thread_messages(test_db, t.id)
    assert len(messages) == 2
    assert messages[0].content == "Why did TXN-101 fail?"
    assert messages[1].role == "assistant"


def test_thread_isolation(test_db):
    """Ensure data in Thread A is strictly inaccessible to Thread B."""
    t_a = create_thread(test_db, title="Thread Alpha")
    t_b = create_thread(test_db, title="Thread Beta")

    # Add match result to Thread A
    match_a = ReconciliationResult(
        id="match_alpha_01",
        thread_id=t_a.id,
        run_id="run_a",
        record_id_a="TXN-ALPHA-01",
        record_id_b="BNK-ALPHA-01",
        source_a="ledger",
        source_b="bank",
        amount_a=5000.0,
        amount_b=5000.0,
        confidence_score=98.5,
        match_category="EXACT_MATCH",
        status="MATCHED"
    )
    test_db.add(match_a)
    test_db.commit()

    # Query matches for Thread A
    matches_a, count_a = get_thread_matches(test_db, thread_id=t_a.id)
    assert count_a == 1
    assert matches_a[0].record_id_a == "TXN-ALPHA-01"

    # Query matches for Thread B (Must be empty)
    matches_b, count_b = get_thread_matches(test_db, thread_id=t_b.id)
    assert count_b == 0
    assert len(matches_b) == 0
