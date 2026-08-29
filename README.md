# AI Finance Controller

> **Agentic Multi-Source Financial Reconciliation, Exception Intelligence, & Ground Truth Evaluation**

---

## 1. What the Project Does

**AI Finance Controller** is an agentic finance-operations platform built to solve multi-source financial reconciliation across internal ERP/ledgers, bank accounts, and payment gateways. 

Instead of forcing users into predefined roles (CFO, Accountant, Controller), the platform provides a **natural-language conversational workspace** where anyone can:
1. Upload multi-source financial documents (CSV, Excel `.xlsx`, PDF, JSON).
2. Instruct the agent to reconcile records and isolate discrepancies.
3. Automatically execute a deterministic multi-tier candidate scoring pipeline orchestrated via **LangGraph**.
4. Capture **honest unresolved exceptions** (amount discrepancies, bank fees, duplicate entries, ambiguous multi-candidates).
5. Measure reconciliation performance and throughput against a **known ground truth dataset** across 200+ records.
6. Interactively query transactions, discrepancies, and metrics via a context-aware **QA Copilot**.

---

## 2. Problem Statement

Financial operations teams struggle with manual reconciliation across ERP ledgers, bank statements, and payment gateways. Traditional rule engines either fail on minor formatting variations or LLM-only approaches hallucinate financial figures and force incorrect matches.

The **AI Finance Controller** pairs **deterministic Python scoring & arithmetic** for 100% mathematical precision with **LangGraph orchestration & Gemini Flash** for semantic understanding and conversational investigation.

---

## 3. Architecture

```
                               +-------------------------------------------------------+
                               |                  USER INTERFACE                       |
                               |    Next.js + React + TypeScript + Tailwind (Razorpay) |
                               +-------------------------------------------------------+
                                                           |
                                                           | REST API (HTTP)
                                                           v
                               +-------------------------------------------------------+
                               |                 FASTAPI BACKEND                       |
                               |  /api/upload  /api/reconciliation/run  /api/chat      |
                               +-------------------------------------------------------+
                                                           |
                                                           v
+----------------------------------------------------------------------------------------------------------------+
|                                           LANGGRAPH RECONCILIATION AGENT                                       |
|                                                                                                                |
|   START --> [ analyze_request ] --> [ load_documents ] --> [ normalize_records ] --> [ generate_candidates ]   |
|                                                                                               |                |
|   END   <-- [ calculate_metrics ] <-- [ create_exceptions ] <-- [ verify_matches ]   <-- [ match_records ]       |
+----------------------------------------------------------------------------------------------------------------+
             |                                                                              |
             v                                                                              v
+------------------------------------+                                     +------------------------------------+
|   DETERMINISTIC SCORING ENGINE     |                                     |    BENCHMARK & EVALUATION MODULE   |
|  - Ref Match (+40)                 |                                     |  - Ground Truth (200+ cases)       |
|  - Amount Match (+30)              |                                     |  - Precision: 100.0%               |
|  - Date Proximity (+15)            |                                     |  - Recall: 96.25%                  |
|  - Entity Similarity (+15)         |                                     |  - Accuracy: 96.92%                |
|  - Delta / Fee Detection           |                                     |  - Throughput: >600 rec/sec        |
+------------------------------------+                                     +------------------------------------+
             |                                                                              |
             +--------------------------------------+---------------------------------------+
                                                    |
                                                    v
                               +-----------------------------------------+
                               |           SQLITE DATABASE               |
                               |  - ReconciliationRun  - MatchResult     |
                               |  - ExceptionResult    - MetricData      |
                               +-----------------------------------------+
                                                    ^
                                                    | Retrieves Real Data
                               +-----------------------------------------+
                               |            QA COPILOT AGENT             |
                               |    LangGraph + Gemini Flash / Heuristics|
                               +-----------------------------------------+
```

---

## 4. Directory Structure

Strictly structured with two primary application directories:

```
ai-finance-controller/
│
├── website/                         # FRONTEND (Next.js, TypeScript, Tailwind CSS)
│   ├── app/
│   │   ├── globals.css              # Razorpay theme & fintech palette
│   │   ├── layout.tsx
│   │   └── page.tsx                 # Conversational workspace & tabbed dashboard
│   ├── components/
│   │   ├── Navbar.tsx               # Header with live agent status
│   │   ├── WorkspaceHeader.tsx      # Natural language prompt & recent runs
│   │   ├── FileUploader.tsx         # Multi-file drag & drop + demo loader
│   │   ├── RunProgress.tsx          # LangGraph visual execution stepper
│   │   ├── MetricCards.tsx          # KPI metric cards (Rate, Accuracy, Speed)
│   │   ├── ReconciliationTable.tsx  # Matched transactions with confidence bars
│   │   ├── ExceptionTable.tsx       # Discrepancies & exception list
│   │   ├── ExceptionDetailModal.tsx # Multi-candidate score breakdown drawer
│   │   ├── EvaluationView.tsx       # Ground truth benchmark & confusion matrix
│   │   └── ChatPanel.tsx            # Context-grounded QA Copilot
│   ├── lib/
│   │   └── api.ts                   # TypeScript API client
│   └── package.json
│
├── model/                           # BACKEND, AGENTS, RECONCILIATION & EVALUATION
│   ├── app/
│   │   └── main.py                  # FastAPI server with all REST endpoints
│   ├── agents/
│   │   ├── state.py                 # ReconciliationState & QAState definitions
│   │   ├── reconciliation_graph.py  # 8-Node LangGraph StateGraph pipeline
│   │   ├── qa_graph.py              # Context-aware QA investigation LangGraph
│   │   ├── orchestrator.py          # Intent routing & extensibility stubs
│   │   └── gemini_client.py         # Gemini Flash LLM with heuristic fallback
│   ├── ingestion/
│   │   ├── parser.py                # CSV, XLSX, PDF, JSON multi-file parser
│   │   └── normalizer.py            # Standardizes ISO dates, amounts, & tokens
│   ├── reconciliation/
│   │   ├── models.py                # Pydantic models (Candidate, Match, Exception)
│   │   └── engine.py                # Deterministic scoring & discrepancy detector
│   ├── evaluation/
│   │   └── evaluator.py             # Precision, recall, and accuracy benchmark
│   ├── synthetic/
│   │   ├── generator.py             # 200+ record multi-scenario synthetic generator
│   │   ├── source_a_ledger.csv      # Generated ERP ledger dataset
│   │   ├── source_b_bank.csv        # Generated bank statement dataset
│   │   ├── source_c_payouts.xlsx    # Generated gateway payouts dataset
│   │   └── ground_truth.json        # Ground truth mapping for all 200 records
│   ├── database/
│   │   ├── models.py                # SQLAlchemy ORM models
│   │   └── db.py                    # SQLite engine and session factory
│   ├── integrations/
│   │   └── razorpay/
│   │       └── client.py            # Razorpay ingestion abstraction
│   ├── tests/                       # Pytest automated test suite
│   └── requirements.txt
│
├── .env.example                     # Environment template
└── README.md
```

---

## 5. How LangGraph Works

The reconciliation workflow is implemented as an explicit 8-node LangGraph `StateGraph`:

1. **`analyze_request`**: Interprets the user's natural language request, identifying matching constraints.
2. **`load_documents`**: Ingests all uploaded files (or pre-bundled synthetic datasets).
3. **`normalize_records`**: Parses ISO dates (`YYYY-MM-DD`), standardizes numeric floats to 2 decimal places, and strips noise from reference tokens.
4. **`generate_candidates`**: Generates cross-source candidate pairs.
5. **`match_records`**: Executes multi-factor deterministic scoring and classifies candidate confidence.
6. **`verify_matches`**: Confirms 1-to-1 pairwise consistency and prevents double-counting.
7. **`create_exceptions`**: Categorizes honest unresolved exceptions with actionable explanations.
8. **`calculate_metrics`**: Computes ground truth benchmark metrics (Precision, Recall, Accuracy, Throughput).

---

## 6. Deterministic Reconciliation Engine

The matching engine uses an explicit, transparent scoring model (0 to 100 points):

$$\text{Score} = \text{Ref (+40)} + \text{Amount (+30)} + \text{Date (+15)} + \text{Entity (+15)}$$

- **Reference Match (up to +40)**: Exact reference (+40), clean alphanumeric token match (+38), substring (+32), fuzzy ratio (+25).
- **Amount Match (up to +30)**: Exact amount (+30), $\le \$0.05$ difference (+28), $\le 1\%$ difference (+20).
- **Date Proximity (up to +15)**: Same day (+15), within 2 days (+12), within 5 days (+8).
- **Entity Similarity (up to +15)**: Exact (+15), token sort ratio $\ge 85\%$ (+15), similarity $\ge 65\%$ (+12).

### Thresholds & Exception Rules:
- **Score $\ge 80.0$ & single dominant candidate** $\rightarrow$ `MATCHED`.
- **Reference match exists but amount differs $> \$0.05$** $\rightarrow$ `AMOUNT_MISMATCH` Exception (flags gateway fees or wire deductions).
- **Multiple candidates within $6.0$ score delta** $\rightarrow$ `AMBIGUOUS_CANDIDATES` Exception (prevents arbitrary guessing).
- **No counterpart found** $\rightarrow$ `MISSING_COUNTERPART` Exception.
- **Identical reference within same ledger** $\rightarrow$ `DUPLICATE` Exception.

---

## 7. Synthetic Benchmark Dataset (200+ Records)

The synthetic generator creates realistic scenarios with corresponding ground truth:

| Scenario Category | Count | Description |
|---|---|---|
| **Clean Exact Matches** | 120 | Identical reference ID, amount, date, and vendor |
| **Fuzzy Matches** | 25 | Slight entity name variation, formatting differences |
| **Amount Discrepancies** | 15 | Payment gateway fees (2.5%) or wire transfer deductions ($15) |
| **Settlement Lag (Date)** | 10 | T+7 international settlement delay |
| **Missing Records** | 10 | Ledger entries missing in bank or unrecorded bank fees |
| **Duplicate Entries** | 10 | Accidental duplicate bookings in ledger |
| **Ambiguous Candidates** | 10 | Identical amounts & dates on same vendor with different IDs |
| **Total** | **200** | Full batch benchmark |

---

## 8. Measured Benchmark Results

Evaluated directly against `ground_truth.json`:

- **Total Records Processed**: 380
- **Total Ground Truth Cases**: 195
- **True Positives (TP)**: 154
- **True Negatives (TN)**: 35
- **False Positives (FP)**: 0 *(Zero false matches forced)*
- **False Negatives (FN)**: 6
- **Match Rate**: **81.05%**
- **Precision**: **100.0%**
- **Recall**: **96.25%**
- **Overall Accuracy**: **96.92%**
- **Processing Time**: **0.61 seconds**
- **Throughput**: **622.56 records/sec**

---

## 9. How to Run

### Backend (`model/`):
```bash
# 1. Navigate to root
cd "ai-finance-controller"

# 2. Activate virtualenv
source model/.venv/bin/activate

# 3. (Optional) Run test suite
pytest model/tests

# 4. Start FastAPI server
python -m uvicorn model.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (`website/`):
```bash
# 1. Navigate to website folder
cd "website"

# 2. Start Next.js development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 10. Example User Workflow

1. Open the web workspace at `http://localhost:3000`.
2. Click **"Run 200+ Batch"** or type *"Reconcile these financial records and identify anything that doesn't match."*
3. Watch the **LangGraph 8-step pipeline** execute in real time.
4. Review the top KPI cards (**81.1% Match Rate, 96.9% Accuracy, 622 records/sec**).
5. Explore the **Matched Records** table and filter by *Exact*, *Fuzzy*, or *Settlement Lag*.
6. Switch to the **Exceptions & Discrepancies** tab and click **"Inspect"** on an ambiguous case or amount fee discrepancy to view candidate comparison scores.
7. Switch to the **Ground Truth Benchmark** tab to view the confusion matrix.
8. Open the **QA Copilot** and ask:
   - *"Why wasn't TXN-LEDGER-1184 matched?"*
   - *"What is our current accuracy and match rate?"*
   - *"Show me all amount discrepancies."*
