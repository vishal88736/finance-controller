"""
Comprehensive API tests: threads, documents (upload security), reconciliation,
results, metrics honesty, suggestions, audit — executed against real HTTP
routes via FastAPI TestClient.
"""

import io

import pytest

from .conftest import LEDGER_CSV, BANK_CSV, make_xlsx, make_json_doc


def create_thread(client, title="Test Thread"):
    r = client.post("/api/threads", json={"title": title})
    assert r.status_code == 201
    return r.json()


def upload(client, thread_id, name, content):
    return client.post(
        f"/api/threads/{thread_id}/documents",
        files={"files": (name, content, "application/octet-stream")},
    )


def upload_pair(client, thread_id):
    r1 = upload(client, thread_id, "transactions_ledger.csv", LEDGER_CSV)
    r2 = upload(client, thread_id, "bank_statement.csv", BANK_CSV)
    assert r1.status_code == 200
    assert r2.status_code == 200
    outcomes = r1.json()["results"] + r2.json()["results"]
    assert all(o["status"] == "SUCCESS" for o in outcomes)
    return outcomes


def reconcile(client, thread_id, **body):
    return client.post(f"/api/threads/{thread_id}/reconcile", json=body)


# ═════════════════════════════════════════════════════════════
# THREADS
# ═════════════════════════════════════════════════════════════

class TestThreads:
    def test_create_thread(self, api_client):
        r = api_client.post("/api/threads", json={"title": "Razorpay March"})
        assert r.status_code == 201
        body = r.json()
        assert body["id"].startswith("thr_")
        assert body["title"] == "Razorpay March"

    def test_create_thread_default_title(self, api_client):
        r = api_client.post("/api/threads", json={})
        assert r.status_code == 201
        assert r.json()["title"] == "New Financial Investigation"

    def test_list_threads(self, api_client):
        create_thread(api_client, "A")
        create_thread(api_client, "B")
        r = api_client.get("/api/threads")
        assert r.status_code == 200
        titles = {t["title"] for t in r.json()}
        assert {"A", "B"} <= titles

    def test_get_thread_detail(self, api_client):
        t = create_thread(api_client)
        r = api_client.get(f"/api/threads/{t['id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == t["id"]
        assert body["documents"] == []
        assert body["latest_run"] is None

    def test_get_missing_thread_404(self, api_client):
        assert api_client.get("/api/threads/thr_nope").status_code == 404

    def test_rename_thread(self, api_client):
        t = create_thread(api_client, "Old")
        r = api_client.patch(f"/api/threads/{t['id']}", json={"title": "New Name"})
        assert r.status_code == 200
        assert r.json()["title"] == "New Name"
        assert api_client.get(f"/api/threads/{t['id']}").json()["title"] == "New Name"

    def test_rename_missing_thread_404(self, api_client):
        assert api_client.patch("/api/threads/thr_nope", json={"title": "x"}).status_code == 404

    def test_delete_thread_cascades(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        assert api_client.delete(f"/api/threads/{t['id']}").status_code == 200
        assert api_client.get(f"/api/threads/{t['id']}").status_code == 404
        assert api_client.get(f"/api/threads/{t['id']}/documents").status_code == 404

    def test_delete_missing_thread_404(self, api_client):
        assert api_client.delete("/api/threads/thr_nope").status_code == 404

    def test_thread_isolation_documents(self, api_client):
        ta = create_thread(api_client, "A")
        tb = create_thread(api_client, "B")
        upload(api_client, ta["id"], "a_ledger.csv", LEDGER_CSV)
        docs_a = api_client.get(f"/api/threads/{ta['id']}/documents").json()
        docs_b = api_client.get(f"/api/threads/{tb['id']}/documents").json()
        assert len(docs_a) == 1
        assert len(docs_b) == 0  # thread B never sees thread A's documents


# ═════════════════════════════════════════════════════════════
# DOCUMENTS — FORMATS & DUPLICATES
# ═════════════════════════════════════════════════════════════

class TestDocumentUploads:
    def test_csv_upload_success(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "ledger.csv", LEDGER_CSV)
        res = r.json()["results"][0]
        assert res["status"] == "SUCCESS"
        assert res["document"]["record_count"] == 3

    def test_xlsx_upload_success(self, api_client):
        t = create_thread(api_client)
        xlsx = make_xlsx([
            {"record_id": "X1", "reference": "R1", "amount": 100.5, "date": "2026-01-01", "entity": "Acme"},
            {"record_id": "X2", "reference": "R2", "amount": 200.5, "date": "2026-01-02", "entity": "Globex"},
        ])
        r = upload(api_client, t["id"], "payouts.xlsx", xlsx)
        res = r.json()["results"][0]
        assert res["status"] == "SUCCESS"
        assert res["document"]["record_count"] == 2

    def test_json_upload_success(self, api_client):
        t = create_thread(api_client)
        content = make_json_doc([
            {"id": "J1", "reference_id": "REF-1", "amount": "75.00", "date": "2026-02-02"},
        ])
        r = upload(api_client, t["id"], "records.json", content)
        res = r.json()["results"][0]
        assert res["status"] == "SUCCESS"
        assert res["document"]["record_count"] == 1

    def test_exact_byte_duplicate(self, api_client):
        t = create_thread(api_client)
        upload(api_client, t["id"], "one.csv", LEDGER_CSV)
        r2 = upload(api_client, t["id"], "one_copy.csv", LEDGER_CSV)
        res = r2.json()["results"][0]
        assert res["status"] == "DUPLICATE_EXACT"
        assert res["duplicate_type"] == "EXACT_FILE"

    def test_renamed_duplicate_same_dataset(self, api_client):
        """Same records under different filename/headers → Level 2 fingerprint duplicate."""
        t = create_thread(api_client)
        upload(api_client, t["id"], "settlement_v1.csv", LEDGER_CSV)
        renamed = (
            b"txn_id,ref_no,net_amount,txn_date,vendor,notes\n"
            b"TX_001,INV_1001,1500.00,2026-08-10,Alpha Logistics,Warehouse freight payment\n"
            b"TX_002,INV_1002,2450.00,2026-08-11,Beta Software,Cloud server subscription\n"
            b"TX_003,INV_1003,5000.00,2026-08-12,Gamma Marketing,Ad campaign spend\n"
        )
        r2 = upload(api_client, t["id"], "settlement_final.csv", renamed)
        res = r2.json()["results"][0]
        assert res["status"] == "DUPLICATE_LOGICAL"
        assert res["duplicate_type"] == "LOGICAL_DATASET"

    def test_reordered_records_still_duplicate(self, api_client):
        """Row reordering must not bypass the canonical fingerprint."""
        t = create_thread(api_client)
        upload(api_client, t["id"], "v1.csv", LEDGER_CSV)
        reordered = (
            b"record_id,reference,amount,date,entity,description\n"
            b"TX_003,INV_1003,5000.00,2026-08-12,Gamma Marketing,Ad campaign spend\n"
            b"TX_001,INV_1001,1500.00,2026-08-10,Alpha Logistics,Warehouse freight payment\n"
            b"TX_002,INV_1002,2450.00,2026-08-11,Beta Software,Cloud server subscription\n"
        )
        res = upload(api_client, t["id"], "v2.csv", reordered).json()["results"][0]
        assert res["status"] == "DUPLICATE_LOGICAL"


# ═════════════════════════════════════════════════════════════
# DOCUMENTS — SECURITY (upload hardening)
# ═════════════════════════════════════════════════════════════

class TestUploadSecurity:
    def test_path_traversal_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "../../pwned.txt", LEDGER_CSV)
        res = r.json()["results"][0]
        assert res["status"] == "REJECTED"
        assert res["reason_code"] == "PATH_TRAVERSAL"
        assert api_client.get(f"/api/threads/{t['id']}/documents").json() == []

    def test_deep_traversal_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "../../../etc/passwd", LEDGER_CSV)
        assert r.json()["results"][0]["reason_code"] == "PATH_TRAVERSAL"

    def test_absolute_path_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "/etc/passwd", LEDGER_CSV)
        assert r.json()["results"][0]["reason_code"] == "PATH_TRAVERSAL"

    def test_windows_path_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "..\\..\\evil.csv", LEDGER_CSV)
        assert r.json()["results"][0]["reason_code"] == "PATH_TRAVERSAL"

    def test_unicode_filename_rejected_or_safe(self, api_client):
        """Unicode separators/control chars must not traverse or crash."""
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "日本語履歴.csv", LEDGER_CSV)
        res = r.json()["results"][0]
        assert res["status"] in ("SUCCESS", "REJECTED")

    def test_control_chars_rejected(self, api_client):
        """Control chars are neutralized by multipart transport; registry layer also rejects raw ones."""
        from model.ingestion.registry import validate_upload_filename, UploadRejected

        # direct layer defense: raw control char is rejected
        with pytest.raises(UploadRejected) as ei:
            validate_upload_filename("evil\x00.csv")
        assert ei.value.reason_code == "INVALID_FILENAME"

        # via HTTP transport, the raw byte never arrives as a filename (percent-encoded),
        # so it is stored harmlessly or rejected — but never traverses
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "evil\x00.csv", LEDGER_CSV)
        res = r.json()["results"][0]
        assert res["status"] in ("SUCCESS", "REJECTED")

    def test_very_long_filename_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "x" * 300 + ".csv", LEDGER_CSV)
        assert r.json()["results"][0]["reason_code"] == "INVALID_FILENAME"

    def test_empty_file_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "empty.csv", b"")
        res = r.json()["results"][0]
        assert res["status"] == "REJECTED"
        assert res["reason_code"] == "EMPTY_FILE"

    def test_header_only_csv_zero_records_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "headers_only.csv", b"record_id,reference,amount,date,entity\n")
        res = r.json()["results"][0]
        assert res["status"] == "REJECTED"
        assert res["reason_code"] == "ZERO_RECORDS"

    def test_malformed_csv_rejected(self, api_client):
        """Garbage bytes in a .csv must be rejected explicitly."""
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "corrupt.csv", b"\x00\xff\xfe\x12\x34\x56\x78\x9a")
        res = r.json()["results"][0]
        assert res["status"] == "REJECTED"
        assert res["reason_code"] in ("MALFORMED_FILE", "ZERO_RECORDS")

    def test_malformed_xlsx_rejected(self, api_client):
        """Non-zip content claiming to be xlsx is rejected."""
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "fake.xlsx", b"this is definitely not a zip file")
        res = r.json()["results"][0]
        assert res["status"] == "REJECTED"
        assert res["reason_code"] == "MALFORMED_FILE"

    def test_unsupported_extension_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "script.sh", b"#!/bin/sh\nrm -rf /")
        assert r.json()["results"][0]["reason_code"] == "UNSUPPORTED_TYPE"

    def test_pdf_rejected(self, api_client):
        t = create_thread(api_client)
        r = upload(api_client, t["id"], "doc.pdf", b"%PDF-1.4 fake")
        assert r.json()["results"][0]["reason_code"] == "UNSUPPORTED_TYPE"

    def test_oversized_file_rejected(self, api_client):
        from model.ingestion.registry import MAX_UPLOAD_BYTES

        t = create_thread(api_client)
        big = b"record_id,reference,amount\n" + b"R1,X,1.00\n" * 1000
        big = big + b"0" * (MAX_UPLOAD_BYTES + 1)
        r = upload(api_client, t["id"], "big.csv", big)
        assert r.json()["results"][0]["reason_code"] == "OVERSIZED_FILE"

    def test_stored_files_use_server_names(self, api_client, tmp_path):
        """The stored file must NOT be named after user input."""
        t = create_thread(api_client)
        upload(api_client, t["id"], "my_ledger.csv", LEDGER_CSV)
        import os
        stored = os.listdir(tmp_path / "uploads")
        assert len(stored) == 1
        # server name: <thread_id>_<uuid>.<ext> — no user filename component
        assert "my_ledger" not in stored[0]
        assert stored[0].startswith(t["id"])
        assert stored[0].endswith(".csv")


# ═════════════════════════════════════════════════════════════
# RECONCILIATION (REST)
# ═════════════════════════════════════════════════════════════

class TestReconciliationREST:
    def test_empty_thread_reconciliation_rejected_not_synthetic(self, api_client):
        """An empty thread must NOT silently reconcile synthetic data."""
        t = create_thread(api_client)
        r = reconcile(api_client, t["id"])
        assert r.status_code == 400
        assert "No documents" in r.json()["detail"]

    def test_reconciliation_uses_only_thread_documents(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        r = reconcile(api_client, t["id"])
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert summary["total_records"] == 6  # 3 + 3 from uploaded CSVs only

    def test_reconciliation_persists_results(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        run_id = reconcile(api_client, t["id"]).json()["run_id"]

        matches = api_client.get(f"/api/threads/{t['id']}/results").json()
        assert matches["total"] >= 1
        pairs = {(m["record_id_a"], m["record_id_b"]) for m in matches["matches"]}
        assert ("TX_001", "BNK_001") in pairs

        exceptions = api_client.get(f"/api/threads/{t['id']}/exceptions").json()
        exc_ids = {e["record_id"] for e in exceptions["exceptions"]}
        assert "TX_002" in exc_ids  # 2450 vs 2388.75
        assert "TX_003" in exc_ids  # missing in bank
        assert "BNK_999" in exc_ids  # extra bank row

        # fee exception evidence carries the exact delta
        tx2 = [e for e in exceptions["exceptions"] if e["record_id"] == "TX_002"][0]
        assert tx2["reason_code"] == "AMOUNT_MISMATCH"
        assert abs(tx2["amount_discrepancy"] - 61.25) < 0.01
        assert tx2["evidence"]["record_id_a"] == "TX_002"

    def test_reconciliation_thread_isolation(self, api_client):
        """Thread B reconciliation must not consume thread A docs and vice versa."""
        ta = create_thread(api_client, "A")
        tb = create_thread(api_client, "B")

        upload_pair(api_client, ta["id"])
        upload(api_client, tb["id"], "b_only.csv", LEDGER_CSV)  # 1 doc in B

        rb = reconcile(api_client, tb["id"]).json()
        # Thread B only reconciles its own single ledger doc (no bank doc)
        assert rb["summary"]["total_records"] == 3
        matches_b = api_client.get(f"/api/threads/{tb['id']}/results").json()
        matches_a = api_client.get(f"/api/threads/{ta['id']}/results").json()
        assert matches_b["total"] == 0
        # A's matches only contain A's records
        assert all(
            m["record_id_a"].startswith("TX_") for m in matches_a["matches"]
        )

    def test_reconciliation_creates_audit_events(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        reconcile(api_client, t["id"])
        audit = api_client.get(f"/api/threads/{t['id']}/audit").json()
        actions = {a["action"] for a in audit}
        assert "RECONCILIATION_STARTED" in actions
        assert "RECONCILIATION_COMPLETED" in actions

    def test_reconciliation_appends_assistant_message(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        reconcile(api_client, t["id"])
        msgs = api_client.get(f"/api/threads/{t['id']}/messages").json()
        assert any(
            m["role"] == "assistant" and "Reconciliation Completed" in m["content"]
            for m in msgs
        )

    def test_document_subset_reconciliation(self, api_client):
        t = create_thread(api_client)
        docs = upload_pair(api_client, t["id"])
        doc_ids = [o["document"]["id"] for o in docs]
        r = reconcile(api_client, t["id"], document_ids=[doc_ids[0]])
        assert r.status_code == 200
        assert r.json()["summary"]["total_records"] == 3  # only doc 1

    def test_match_evidence_structure(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        reconcile(api_client, t["id"])
        m = api_client.get(f"/api/threads/{t['id']}/results").json()["matches"][0]
        ev = m["evidence"]
        assert "amount_a" in ev and "record_id_a" in ev
        assert m["confidence_score"] > 0


# ═════════════════════════════════════════════════════════════
# METRICS HONESTY
# ═════════════════════════════════════════════════════════════

class TestMetricsHonesty:
    def test_user_run_not_evaluated(self, api_client):
        """User-document runs must report evaluated=false with null eval metrics."""
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        reconcile(api_client, t["id"])
        m = api_client.get(f"/api/threads/{t['id']}/metrics").json()
        assert m["evaluated"] is False
        assert m["precision"] is None
        assert m["recall"] is None
        assert m["f1_score"] is None
        assert m["accuracy"] is None
        assert m["confusion_matrix"] == {}
        # operational metrics ARE real
        assert m["total_records"] == 6
        assert m["matched_count"] >= 1
        assert 0 < m["match_rate"] <= 100

    def test_metrics_404_when_no_run(self, api_client):
        t = create_thread(api_client)
        assert api_client.get(f"/api/threads/{t['id']}/metrics").status_code == 404


# ═════════════════════════════════════════════════════════════
# SUGGESTED QUESTIONS
# ═════════════════════════════════════════════════════════════

class TestSuggestions:
    def test_no_documents_state(self, api_client):
        t = create_thread(api_client)
        s = api_client.get(f"/api/threads/{t['id']}/suggestions").json()
        assert s["state"] == "NO_DOCUMENTS"
        assert len(s["suggestions"]) > 0

    def test_pending_state(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        s = api_client.get(f"/api/threads/{t['id']}/suggestions").json()
        assert s["state"] == "PENDING_RECONCILIATION"

    def test_ready_state_mentions_real_records(self, api_client):
        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        reconcile(api_client, t["id"])
        s = api_client.get(f"/api/threads/{t['id']}/suggestions").json()
        assert s["state"] == "READY"
        # suggestions reference an actual record from this thread
        assert any("TX_00" in q or "BNK_" in q or "exception" in q.lower() for q in s["suggestions"])

    def test_suggestions_are_guardrail_safe(self, api_client):
        """Every suggested question must pass the guardrails."""
        from model.agents.guardrails import guardrails

        t = create_thread(api_client)
        upload_pair(api_client, t["id"])
        reconcile(api_client, t["id"])
        s = api_client.get(f"/api/threads/{t['id']}/suggestions").json()
        for q in s["suggestions"]:
            ok, _ = guardrails.validate_input(q)
            assert ok, f"Suggested question blocked by guardrails: {q}"


# ═════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS
# ═════════════════════════════════════════════════════════════

class TestLegacyEndpoints:
    def test_legacy_chat_requires_existing_thread(self, api_client):
        r = api_client.post("/api/chat", json={"question": "What is the match rate?", "thread_id": "thr_evil"})
        assert r.status_code == 404

    def test_legacy_chat_creates_default_thread_server_side(self, api_client):
        r = api_client.post("/api/chat", json={"question": "What is the match rate?"})
        assert r.status_code == 200

    def test_legacy_run_never_uses_synthetic(self, api_client):
        r = api_client.post("/api/reconciliation/run", json={"user_prompt": "reconcile", "demo_batch": False})
        assert r.status_code == 400  # default thread has no documents

    def test_health(self, api_client):
        r = api_client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
