# Finance Controller Main Model Audit and Reference Repository Comparison

*Date: 2026-09-05 · Verification labels: VERIFIED FROM CODE / TESTS / DOCUMENTATION; INFERRED; NOT VERIFIED; MISSING; UNUSED; STUB.*

---

## 1. Executive summary

**Current status.** The "AI Finance Controller" (FastAPI + SQLite + Next.js + LangGraph) is fundamentally sound: it enforces the correct architectural principle — **deterministic Python owns every monetary calculation, match, tolerance, tax figure and DB write; the LLM is only an explanation layer for Q&A.** This places it ahead of most of the reference repositories on financial safety.

**Main strengths (VERIFIED FROM CODE):**
- Deterministic multi-pass reconciliation engine (`reconciliation/pandas_reconciler.py`) — canonical-ID join → reference-ID → amount+date-window → entity+date, with exact/fee-delta/tolerance confidence scoring, currency-mismatch rejection, duplicate + ambiguous-candidate detection.
- Six-layer deterministic guardrails (`agents/guardrails.py`) incl. numeric/ID evidence validation (Layer 5) that gates every LLM answer.
- Deterministic tax, cash-forecast, role-classification, schema mapping, and audit-trail.
- Groq `llama-3.3-70b-versatile` used in exactly one place (QA synthesis), with a deterministic fallback and sentinel on failure.

**Main weaknesses:**
1. **A live crash bug** in the settlement QA tool (non-existent SQLAlchemy columns).
2. **2 failing tests** (a routing regression and a multi-way-reconciliation semantic mismatch); README's "79/79 passing" is stale.
3. **No OCR/VLM/PDF extraction** (parser is a stub returning `[]`), **no embeddings/vector DB/reranker**, **no working-capital optimizer** despite being listed as a capability.
4. **Unused/dead code**: Gemini client, a `rapidfuzz` verification module, Razorpay stub.
5. Multi-source reconciliation is **half-implemented** (planner builds the plan; engine reconciles only the first counterpart).

**Active models (see §3).** Reconciliation/tax/forecast/classification/etc. are all **deterministic algorithms (local)**. Only decision explanation uses a **hosted LLM API**.

**Most important risks:** the settlement-tool crash; the routing regression that breaks the documented "factual grounding" behaviour; and the absence of a second deterministic guard on multi-file reconciliation.

**Highest-priority improvements (P0/P1, safe to implement now):** fix the settlement tool columns; fix ID+amount query routing. (See §5–§7.)

---

## 2. Current architecture

- **Backend:** FastAPI `model/app/main.py` (v2.1.0) → SQLite via SQLAlchemy (`model/database/{db,models,repositories}.py`).
- **Frontend:** Next.js 16 / React 19 (`website/`) with views for dashboard, reconciliation, results, exceptions, tax, forecast, audit trail, agent activity.
- **Orchestration:** two LangGraph `StateGraph`s — `graph/reconciliation_graph.py` (linear pipeline) and `agents/qa_graph.py` (guard → understand → retrieve → generate).
- **DB tables:** `threads, documents, document_records, processing_runs, reconciliation_results, exceptions, messages, audit_logs, cash_forecast_results, tax_match_results`.
- **Reconciliation flow:** `services/reconciliation_service.py::run_reconciliation` → LangGraph → role classifier → schema mapper → planner → `pandas_reconciler.reconcile_documents` → persist + audit. **No LLM.**
- **Tax flow:** `services/tax_matcher.py` — Decimal `taxable × rate = expected`, statuses MATCH/MISMATCH/MISSING/AMBIGUOUS/NOT_TAX_APPLICABLE/TAX_DATA_UNAVAILABLE. **No LLM.**
- **Forecast flow:** `services/cash_forecaster.py` — day-of-week-weighted moving average, `INSUFFICIENT_DATA` gate, confidence tiers. **No LLM/ML.**
- **QA/RAG flow:** deterministic SQL tools (`tools/qa_tools.py`) → deterministic formatter first → optional Groq synthesis validated by Layer 5 → Layer 6 sanitization. **No embeddings/vector DB/reranker — exact-ID SQL lookups.**
- **Decision-log flow:** append-only `audit_logs` via `database/repositories.py::log_audit`.

---

## 3. Current active model inventory

| Capability | Active model/algorithm | Exact file/function | Role | Local/API | Status |
|---|---|---|---|---|---|
| Reconciliation | Deterministic pandas+NumPy multi-pass merge | `reconciliation/pandas_reconciler.py::PandasReconciliationEngine._run_matching_passes` | inference | Local | MAIN ACTIVE (VERIFIED CODE+TESTS) |
| Transaction categorization (doc role) | Deterministic vocabulary-weight scorer | `reconciliation/role_classifier.py::DocumentRoleClassifier.classify_document` | classification | Local | MAIN ACTIVE |
| Tax matching | Deterministic Decimal arithmetic | `services/tax_matcher.py::TaxMatcherService.run_tax_matching` | calculation | Local | MAIN ACTIVE |
| Invoice extraction | None (PDF parser stub returns `[]`) | `ingestion/parser.py::parse_simple_pdf` | — | — | STUB / MISSING |
| Forecasting | Deterministic DOW-weighted moving average | `services/cash_forecaster.py::CashForecasterService.run_forecast` | calculation | Local | MAIN ACTIVE |
| Working-capital optimization | Not implemented | — | — | — | MISSING |
| Settlement QA | Deterministic SQL + optional Groq synthesis | `tools/qa_tools.py` + `agents/qa_graph.py::generate_answer_node` | retrieval+explanation | Local+API | MAIN ACTIVE |
| Document QA | Deterministic formatter; Groq synthesis (validated) | `qa_graph.py::format_deterministic_answer` / `generate_answer_node` | explanation | Local+API | MAIN ACTIVE (Groq = SECONDARY) |
| RAG retrieval / Embeddings / Reranking | None | — | — | — | MISSING |
| Agent planning | Deterministic `ReconciliationPlanner` | `reconciliation/planner.py::create_plan` | planning | Local | MAIN ACTIVE |
| Agent routing | Deterministic regex | `agents/orchestrator.py::route_intent` + `qa_graph.py::understand_question_node` | routing | Local | MAIN ACTIVE |
| Agent tool selection | Deterministic if/elif | `qa_graph.py::retrieve_relevant_records_node` | orchestration | Local | MAIN ACTIVE |
| Decision explanation | Groq `llama-3.3-70b-versatile` (fallback deterministic) | `agents/groq_client.py::generate_text` | reasoning | API | MAIN ACTIVE (FALLBACK = deterministic) |
| OCR / VLM | None | — | — | — | MISSING |

**Unused / stub / dead (VERIFIED):**
- `agents/gemini_client.py` (`gemini-2.5-flash`) — UNUSED (never imported in the live path; only `groq_client` is).
- `verification/{matchers,scorer,verifier}.py` (uses `rapidfuzz`) — UNUSED in live reconciliation path; only `verification/normalizers.py` is imported. Referenced by `tests/test_verification.py` only.
- `integrations/razorpay/client.py` — STUB (keys empty; returns `[]`).

---

## 4. Main model audit by capability (condensed)

| # | Capability | Current | Input | Output | Affects $? | Validated? | Failure behaviour |
|---|---|---|---|---|---|---|---|
| 1 | Reconciliation | pandas engine | DataFrames (per thread) | matches/exceptions/confidence | Yes | deterministic | n/a (no model) |
| 2 | Categorization | role_classifier | DF columns+values | role+confidence | Indirect | deterministic | UNKNOWN/0.0 |
| 3 | Tax matching | Decimal engine | records | match statuses + variance | Yes | deterministic | n/a |
| 4 | Invoice extraction | stub | — | [] | — | — | returns [] |
| 5 | OCR | none | — | — | — | — | — |
| 6 | Forecasting | DOW moving avg | records | projections + confidence | Yes | deterministic | INSUFFICIENT_DATA |
| 7 | Working capital | none | — | — | — | — | — |
| 8 | Settlement QA | SQL + Groq | question | answer w/ cite ids | No | Layer 5 | falls back deterministic |
| 9 | Document QA | formatter + Groq | evidence | answer | No | Layer 5 | determined fallback |
| 10 | RAG retrieval | none (exact SQL) | id/query_type | rows | No | — | — |
| 11 | Embeddings | none | — | — | — | — | — |
| 12 | Reranking | none | — | — | — | — | — |
| 13 | Agent planning | planner | classified docs | plan contract | Indirect | deterministic | — |
| 14 | Agent routing | regex | prompt | "RECONCILIATION"/"QA"/"OFF_TOPIC" | Indirect | deterministic | — |
| 15 | Tool selection | if/elif | query_type | tool calls | Indirect | deterministic | — |
| 16 | Decision explanation | Groq LLM | evidence prompt | prose | No | Layer 5 → fallback | `LLM_UNAVAILABLE` |
| 17 | Visual understanding | none | — | — | — | — | — |

---

## 5. Confirmed issues (with file paths and evidence)

| id | Issue | Exact location | Impact | Severity |
|---|---|---|---|---|
| B1 | `get_settlement_status_tool` filters on `ExceptionItemResult.exception_type` and reads `e.exception_type` / `e.description` — columns that **do not exist** (model has `reason_code`, `explanation`; no `exception_type`/`description`). Any "settlement status" query raises `AttributeError`. | `model/tools/qa_tools.py:446,455-456`; model columns `model/database/models.py:163-188` | Live crash on settlement-status QA | **P0** |
| B2 | "What is the amount of TX_001?" (and "Is TX_001 amount $999?") are not routed to `SPECIFIC_RECORD` because the trigger keyword lists omit `amount`; they fall to `GENERAL`→summary, so pre-reconciliation and fact-check answers lose the record amount. Regression vs the documented "factual grounding" feature. | `model/agents/qa_graph.py:116-120` (`understand_question_node` keyword lists) | Broken factual-grounding QA | **P1** |
| B3 | Multi-way reconciliation: planner labels 3-doc case `MULTI_SOURCE_RECONCILIATION` but engine reconciles only the first counterpart; test expects `MULTI_WAY_UNSUPPORTED` + 0 matches (`tests/test_pandas_reconciler.py:250`). Semantics half-implemented. | `model/reconciliation/planner.py:159`; `model/reconciliation/pandas_reconciler.py` | Misleading plan / silent ignore of extra counterpart | **P2 (needs decision)** |
| B4 | README claims "79/79 tests passing"; actual suite is 177 tests, **175 passed / 2 failed**. | `README.md:133-134` | Stale docs | P3 |
| B5 | No OCR/VLM/PDF extraction (stub). | `model/ingestion/parser.py:66-78` | Invoice/PDF unsupported | P2 |
| B6 | No embeddings/vector DB/reranker — RAG is exact-ID SQL only (adequate for structured data, but no semantic doc QA). | `model/tools/qa_tools.py` | No document QA | P3 |
| B7 | Working-capital optimization absent although listed as a capability. | (no file) | Missing capability | P3 |
| B8 | Dead code: Gemini client, `verification/{matchers,scorer,verifier}.py` (rapidfuzz), Razorpay stub. | `model/agents/gemini_client.py`, `model/verification/*`, `model/integrations/razorpay/client.py` | Maintainability/misleading inventory | P3 |

---

## 6. Reference repository inventory

| Repo | Main model/algorithm | Exact files | Active? | Strongest feature | Weakness | Reuse |
|---|---|---|---|---|---|---|
| `agent-for-accounting` (TS, MIT) | Deterministic greedy reconcile tool + Claude agent | `agent/lib/reconcile.ts`, `agent/lib/money.ts`, `agent/tools/reconcile.ts` | Yes | Order-independent matcher; 1:2 **split detection** both directions without double-booking; `needsHumanReview` count; integer-cent money | TypeScript (needs port to Python) | Port algorithm pattern |
| `financialreconciliation` (11ty docs) | pydantic+rapidfuzz+Decimal design reference | `content/transaction-matching-algorithms-logic/**` | Docs only | 3-stage cascade; canonical Decimal/UTC/`source_hash`; absolute+relative tolerance; hash-chained audit | Not runnable code | Design guidance + thresholds |
| `financial-reconciliation-agent` (Py) | "LLM proposes; deterministic disposes": `reconcile.py` (deterministic) + `model.py` (provider wrapper + mock fallback) | `src/reconcile.py`, `src/model.py`, `src/categorize.py`, `src/schema.py`, `src/ledger.py`, `src/policy_rag.py` | Yes | Provider wrapper + offline mock fallback; abstain on uncertainty; chart-of-accounts contract; measured eval (100% recon; 53.6%→100% categor w/ RAG) | float money; no license shown in README | Adopt provider-wrapper + abstain + contract patterns; **do not copy float arithmetic** |
| `itr-agent` (TS MCP, MIT) | Deterministic tax engine over versioned JSON rule packs | `src/engine/{compute,reconcile,rulepack}.ts`, `data/fy2025-26.json` | Yes | Rule-pack versioning; paise-safe summing; tiered tolerance; findings w/ severity+remedy+`noticePreempted`; 109 statute tests; read-only tools | JS + India-specific | Port rule-pack + tolerance-tier + remedy patterns |
| `template-workflow-extract-reconcile-invoice` (Py, LlamaCloud) | LLM structured extraction (`LlamaExtract`) + LLM contract matching | `src/extraction_review/process_file.py`, `config.py` | Yes (hosted) | Pydantic extraction schema + field metadata + file-hash dedup | Hosted stack; **reconciliation is LLM-selected (unsafe)**; needs API keys | Adopt Pydantic-schema extraction pattern only; **reject LLM reconciliation** |
| `statsforecast` (Nixtla, Apache-2.0) | Statistical forecasting: `AutoARIMA/AutoETS/AutoCES/MSTL/Theta` | package | Yes | Fast CPU, prediction intervals, sklearn API | Needs enough history; Python dep | Optional statistical fallback tier |
| `neuralforecast` (Nixtla) | Neural: `NBEATS/NHITS/TFT/PatchTST/TiDE` | package | Yes | SOTA, interpretability | Training + GPU + RAM, overkill | DO NOT adopt now |
| `working-capital-optimizer` (TS+Py, MIT) | Gemini-2.5-Flash agent mesh; Kahn topological orchestration | (README) | Yes (hosted) | CCC=DSO+DIO−DPO design; AR/AP/inventory agents | Forecasting computed by LLM (unsafe) | Design only; compute CCC in code |
| `rag-document-qa` (Py, MIT) | RAG w/ citations + IDF-weighted refusal | (README/eval) | Yes | IDF refusal gate; citation ledger; no-credential eval; 65 tests | extractive reader floor | Adopt refusal-gate pattern |
| `agentic-rag-financial` (Py, MIT) | Hybrid dense+sparse + RRF + cross-encoder rerank + agent loop | (README/pyproject) | Yes | Full RAG stack; table-aware PDF ingest | Heavy (reranker ~1GB+, hosted LLM) | Reference only; DO NOT adopt wholesale |
| `ask-the-docs` (Py) | docling → bge-small-en-v1.5 → Chroma → Claude; numeric-backing check | (README/requirements) | Yes | `bge-small-en-v1.5` (384-d, ~130MB local); deterministic numeric-backing check (mirrors Layer 5) | HDFC-specific | Adopt lightweight embeddings + numeric-backing check |

---

## 7. Model selection per task (recommendations)

| Task | Recommended | Why | Mode | Fallback | Validation |
|---|---|---|---|---|---|
| Reconciliation | Keep deterministic pandas engine | Correct, auditable, fast (>700 rec/s) | Local | — | Tests + invariant tests |
| Add: 1:N split detection | Port greedy symmetric matcher + `possibleSplits` from `agent-for-accounting` | Genuine gap; order-independent; no double-booking | Local deterministic | — | New tests (split symmetry/row-conservation) |
| Transaction categorization | Keep `role_classifier` + optionally LLM categorize w/ abstain | Deterministic already works; LLM only for free-text memo fallback | Local (+ optional API) | role_classifier | off-chart rejection + conf threshold |
| Tax matching | Keep Decimal engine; add rule-pack versioning + tiered tolerance + per-line severities | itr-agent pattern | Local | — | Golden-case tests |
| Invoice extraction (future) | Structured-extraction LLM/VLM bound to Pydantic schema; deterministic reconciliation on extracted fields | template-workflow extraction pattern; **never LLM match-selection** | API (on demand) | None; mark UNPROCESSED | Pydantic validation + field metadata |
| Forecasting | Keep deterministic DOW-MA; optional `statsforecast` AutoETS/AutoARIMA behind history threshold | Safe, explainable; statistical tier only when ≥N datapoints | Local | INSUFFICIENT_DATA | CI tests |
| Working capital | New deterministic CCC code (DSO/DIO/DPO); LLM explains only | No code exists; arithmetic must be code | Local | — | Invariant tests |
| Settlement/document QA | Keep deterministic SQL + Groq synthesis (validated) | Already correct | Local + API | deterministic formatter | Layer 5 |
| Document RAG (future) | `bge-small-en-v1.5` (local) + SQLite/Chroma + IDF refusal + numeric-backing check | Lightweight, mirrors Layer 5 | Local (on demand) | keyword/exact ID | refusal + citation tests |
| Embeddings | `bge-small-en-v1.5` (384-d, ~130MB) if/once RAG added | cheapest local, CPU | Local | hashing embedding | — |
| Reranking | Do NOT adopt cross-encoder now | heavy, unnecessary at current scale | — | — | — |
| Routing / tool selection / planning | Keep deterministic regex/if-elif/planner | correct, auditable, cheap | Local | — | routing tests |
| Decision explanation | Groq `llama-3.3-70b-versatile` (keep) | cheap, fast, already integrated; deterministic fallback | API | deterministic formatter | Layer 5 |

**Model classification:**
- MAIN ACTIVE MODEL: Groq `llama-3.3-70b-versatile` (explanation only).
- SECONDARY/FALLBACK: deterministic formatter (always).
- EMBEDDING (proposed, optional): `bge-small-en-v1.5` local.
- RERANKER: none (DO NOT).
- DETERMINISTIC ALGORITHMS: reconciliation, tax, forecast, classification, routing, planning, guardrails.
- UNUSED: Gemini, `verification/{matchers,scorer,verifier}`.
- STUB: Razorpay client, PDF parser.

---

## 8. Recommended target architecture

```
User / UI (Next.js)
    │  HTTP (thread-scoped)
    ▼
FastAPI routes ── 6-layer guardrails ── Orchestrator (deterministic routing)
    ├─ Reconciliation   → role_classifier → schema_mapper → planner → pandas_reconciler (deterministic)
    ├─ Tax              → tax_matcher (Decimal, rule-pack versioned)
    ├─ Forecast         → cash_forecaster (deterministic; optional statsforecast tier)
    ├─ Working capital  → NEW deterministic CCC module
    ├─ Document ingest  → registry (SHA-256 + fingerprint)  [+ future Pydantic extraction]
    └─ QA/Q&A           → deterministic tools (SQL) → formatter → [optional Groq, Layer-5 validated]
                              └─ (future) local embeddings + IDF refusal + numeric-backing check
    │
    ▼
SQLite (append-only audit_logs + results)  ·  LangSmith (optional tracing)
```

Deterministic code must continue to own: monetary arithmetic, tax, FX, tolerance, dates, balances, ledger updates, final status, DB writes, compliance. LLM may only: classify/extract/summarize/explain/propose/route/answer-from-evidence — never finalize a figure or status.

---

## 9. Resource / privacy / agent design (concise)

- **RAM/CPU:** all active paths are CPU + in-memory pandas, low RAM. No GPU. Only cost = Groq API (cheap; `llama-3.3-70b`).
- **Lazy/on-demand:** only Groq (already lazy) and — if adopted — local `bge-small` embeddings (load once, ~130MB) and a statsforecast tier (import on demand) should be loaded lazily.
- **Privacy:** `.env` holds secrets (present, not committed — verify `.gitignore` covers `.env`); LangSmith tracing defaults **off** (`observability/langsmith.py::is_tracing_active`); QA tools transmit only evidence to Groq. AIS/document PII transmission must be reviewed before any hosted extraction (template-workflow) is adopted — the itr-agent "local-first" stance is the safer default.
- **Parallel-agent/context overload:** current design already avoids concurrency; keep QA tools strictly per-request and SQLite-scoped.
- **Decision-log fields:** already strong (`audit_logs`: action/agent/tool/parameters/result_summary + timestamp). For LLM decisions, record `answer_source` (`llm_validated` vs `deterministic`) — already done in `qa_graph.py`.

---

## 10. Testing plan

- Reconciliation invariant tests: order-independence, row-conservation (every row claimed exactly once), split symmetry, currency-mismatch, duplicate, tolerance boundary, 0%-match diagnostics.
- Tax golden-case tests (existing `test_tax_matcher.py`) + new rule-pack/tolerance-tier cases.
- Forecast: fallback `INSUFFICIENT_DATA`, horizon validation 1..90, preset 7/14/30, stale-dataset note, history-derived baseline.
- QA/routing: SPECIFIC_RECORD vs GENERAL (fix B2), fact-check grounding, refusal, injection, cross-thread isolation.
- Settlement tool: new tests hitting the query type (currently no coverage → B1 escaped).
- API tests (`test_api_comprehensive.py`), security (`test_security_audit.py`), duplicates, threads.

---

## 11. Phased implementation roadmap

| Phase | Feature | Files | Dependencies | Tests | Risk |
|---|---|---|---|---|---|
| **P0 now** | Fix settlement tool columns (B1) | `model/tools/qa_tools.py` | none | new + existing API/QA | low |
| **P1 now** | Fix ID+amount routing (B2) | `model/agents/qa_graph.py` | none | `test_real_user_flow`, `test_qa_tools` | low |
| P2 | Decide multi-way semantics (B3); reconcile planner label with engine, or implement true multi-counterpart | `planner.py`, `pandas_reconciler.py` | none | `test_pandas_reconciler` (3-file) | medium (feature decision) |
| P2 | Invoice extraction (Pydantic schema + structured LLM/VLM) | new module + `parser.py` | hosted VLM/LLM (needs approval) | extraction + validation tests | high (privacy) |
| P3 | Optional `statsforecast` tier + working-capital CCC module | `cash_forecaster.py`, new module | `statsforecast` | forecast fallback + CCC invariant | medium |
| P3 | Optional local document RAG (`bge-small`, IDF refusal, numeric-backing) | new module | `sentence-transformers`/`chromadb` | refusal + citation tests | medium |
| P3 | Remove/annotate dead code (Gemini, rapidfuzz module, Razorpay stub); refresh README test count | several | none | — | low |

---

## 12. Risks and unresolved questions

- **Unresolved:** is multi-source reconciliation intended to be supported or rejected? (Determines B3 fix direction.)
- **Unresolved:** what is the desired `GROQ_MODEL` value / is token-router relevant? (`.env` has values; not inspected to avoid leaking secrets.)
- **Risk:** adopting hosted invoice extraction/VLM will transmit document content externally — requires explicit sign-off (cf. §13 of original brief).
- **Risk:** `bge-small`/`statsforecast` add dependencies; keep optional and lazy-loaded.
- **Not executed (reference repos):** their test suites were NOT run (no Node/pnpm or niche deps installed, per resource rules).

---

## 13. Evidence appendix

- **Finance Controller files read (source of truth):** all listed in §3/§5 (do not re-read these in follow-up phases without a specific question).
- **Reference repos inspected:** `agent-for-accounting`, `financialreconciliation`, `financial-reconciliation-agent` (PHASE 3); `itr-agent`, `template-workflow-extract-reconcile-invoice` (PHASE 4); `statsforecast`, `neuralforecast`, `working-capital-optimizer` (PHASE 5); `rag-document-qa`, `agentic-rag-financial`, `ask-the-docs` (PHASE 6).
- **Tests executed (this project):**
  - `python -m pytest model/tests -q` → **175 passed, 2 failed** (5.35s).
  - `python -m pytest model/tests/test_pandas_reconciler.py::test_pandas_reconciler_multi_document_three_files -q` → **1 failed**.
  - Reference-repo tests: NOT EXECUTED (reason: avoid installing Node/pnpm and niche deps during audit).
- **Unverified claims:** "measured" accuracy figures in `financial-reconciliation-agent` README (not reproduced); any claim in the docs-only `financialreconciliation` site (design guidance, not code).