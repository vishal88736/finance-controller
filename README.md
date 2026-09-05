# AI Finance Controller
> **Agentic Multi-Source Financial Reconciliation, Exception Intelligence, & Ground Truth Evaluation**
> *Razorpay AI Buildathon — Track 4: AI Finance Controller*

---

## 1. Executive Summary

**AI Finance Controller** is a production-quality financial operations workspace built around a critical architectural principle:

> **The LLM is NEVER the source of financial truth.**
> - **Pure Python Functions**: File parsing, normalization with `Decimal`, candidate generation, multi-pass deterministic scoring (0–100), duplicate detection, tolerance checks, and metric computation.
> - **LLM & LangGraph**: Intent routing, natural-language reasoning, summarization, guardrailed question-answering, and conversational investigation.

---

## 2. System Architecture

```
                                  USER
                                   │
                          ┌────────┴────────┐
                          │                 │
                      Chat Input       Document Upload
                          │                 │
                          └────────┬────────┘
                                   │
                                THREAD (thread_id)
                                   │
                         Document Registry
                                   │
                 ┌─────────────────┴─────────────────┐
                 ▼                                   ▼
         Level 1 Check                       Level 2 Check
         (SHA-256 Bytes)                (Canonical Fingerprint)
                 │                                   │
                 └─────────────────┬─────────────────┘
                                   │ (If New)
                          Document Processing
                        (Detect Type + Normalize)
                                   │
                                   ▼
                   LangGraph Orchestrator / Router
                                   │
    ┌───────────────────┬──────────┴───────────┬───────────────────┐
    ▼                   ▼                      ▼                   ▼
[ Off-Topic ]      [ Reconciliation ]     [ Exception Query ]    [ Q&A Agent ]
(4-Layer Guard)    (Python Engine)        (Material/Normal)     (Structured Tools)
    │                   │                      │                   │
    │                   ▼                      │                   │
    │           Structured Results ────────────┴───────────────────┘
    │           (Evidence + Confidence)
    │                   │
    │                   ▼
    │             Results Store (SQLite - Thread Scoped)
    │                   │
    └───────────────────┼──────────────────────────────────────────┘
                        │
                        ▼
                Final User Answer + Audit Trail + LangSmith Trace
```

---

## 3. Key Capabilities

### 1. Evidence-First Pandas Reconciliation Engine
- Pure deterministic engine (`pandas_reconciler.py`) processing records natively. Legacy loops have been fully removed.
- **Fee, Refund, and Chargeback Netting**: Deterministic net amount calculation (`Gross - Fee = Net`). Differentiates between exact gross matches, net matches, and normal fee deltas.
- **Currency (FX) Handling**: Detects currency mismatches across counterpart sources and immediately raises explicit "Currency conversion required" exceptions instead of failing math operations.
- **Strict Relationship Validation**: Detects and cleanly rejects unsupported multi-way reconciliations (e.g., trying to reconcile Ledger vs Bank vs Processor simultaneously).

### 2. ChatGPT-Style Thread System & Router
- Every conversation has a unique `thread_id` (e.g. `thr_8f3a91...`). Strict **Thread Isolation** prevents cross-thread data leakage.
- **Expanded Intent Coverage**: The Orchestrator supports granular natural-language routing for Fees, Refunds, Chargebacks, and Tax operations. 
- **Read-Only Safeties**: Forecasting, Tax Verification, and Querying APIs are strictly `GET` endpoints that cannot mutate state. Empty-states (e.g. 0 eligible transactions) are accurately differentiated from zero-tax results.

### 3. Two-Level Duplicate Detection
- **Level 1 (Exact File Duplicate)**: Cryptographic SHA-256 hash of raw bytes.
- **Level 2 (Logical Dataset Duplicate)**: Deterministic hash of sorted canonical records. Detects renamed files with identical transactions.

### 4. 4-Layer Guardrails
- **Layer 1: Input Classification**: Rejects off-topic requests and unsupported queries (e.g. system audit logs).
- **Layer 2: Thread Scope Check**: Ensures thread existence and blocks cross-thread queries.
- **Layer 3: Tool Permission Check**: Only allows authorized deterministic financial tools.
- **Layer 4: Output Validation**: Redacts confidential keys or answer keys.

### 5. Append-Only Immutable Audit Trail
- Records every action, agent invocation, tool call, parameter set, and outcome timestamp in `audit_logs`.

---

## 4. Benchmark & Accuracy Metrics

Tested directly against the 200+ case synthetic dataset:

| Metric | Measured Value | Standard Target |
|---|---|---|
| **Precision** | **100.0%** | > 99.0% |
| **Recall** | **96.25%** | > 95.0% |
| **Overall Accuracy** | **96.92%** | > 95.0% |
| **False Positives (FP)** | **0** | 0 |
| **Throughput** | **> 700 rec/sec** | > 200 rec/sec |
| **Processing Time** | **< 0.60 seconds** | < 5.0 seconds |

---

## 5. How to Run Locally

### Prerequisites
- Python 3.10+
- Node.js 18+

### Step 1: Start Backend (FastAPI)
```bash
# In repository root
source model/.venv/bin/activate
python -m uvicorn model.app.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Health: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Step 2: Start Frontend (Next.js)
```bash
cd website
npm run dev
```
- Web Application: [http://localhost:3000](http://localhost:3000)

### Step 3: Run Backend Test Suite
```bash
python -m pytest model/tests
```
*(190/190 unit & integration tests passing)*

---

## 6. Complete Demo Walkthrough

| Step | Action | Expected Outcome |
|---|---|---|
| **1. Create Thread** | Click **"+ New Thread"** in left sidebar. | A new isolated workspace thread is created (`thr_...`). |
| **2. Upload Files** | Click **"Documents"** and upload `source_a_ledger.csv`. | Document is registered with SHA-256 hash & record count. |
| **3. Duplicate Check** | Upload `source_a_ledger.csv` again. | **"Level 1: Exact File Duplicate Detected"** warning displayed. File is not re-processed. |
| **4. Run Reconcile** | Click **"Run Reconcile"** or type *"Reconcile these files."* | Deterministic 4-pass engine processes records in <0.6s. KPI metric cards update. |
| **5. Inspect Matches** | Navigate to **"Reconciled Pairs"** tab. | Shows pairwise matches with confidence scores and evidence breakdown. |
| **6. Inspect Exceptions** | Navigate to **"Exceptions & Fees"** tab. | Flags fee deltas (2.5% gateway fees), ambiguous candidates, and duplicate entries. |
| **7. Ask Financial Question** | Type: *"Why are there amount mismatch exceptions?"* | Copilot retrieves exact fee deltas ($15 wire fees, 2.5% gateway deductions) with citations. |
| **8. Test Guardrail** | Type: *"Write me a poem about the sunrise."* | Guardrail immediately refuses with official financial scope message. |
| **9. View Audit Trail** | Navigate to **"Audit Trail"** tab. | Displays immutable chronological record of all actions, tools, and decisions. |
