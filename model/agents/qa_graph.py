"""
LangGraph QA Agent for Financial Investigation & Querying.

Pipeline (every layer actually executes):
    guard_input (Layers 1+2: safety & domain)
        → refuse_off_topic (audit + refusal)
    understand_question (intent + id extraction)
    retrieve_relevant_records (Layer 3 thread scope, Layer 4 tool permission)
    generate_answer (deterministic formatter, optional LLM, Layer 5 evidence
                     validation, Layer 6 output sanitization)

No node ever opens its own DB session — the orchestrator passes the request's
session through state (`db_session`) and it is used exclusively.
"""

import re
from typing import Dict, Any, List

from langgraph.graph import StateGraph, START, END

from .state import QAState
from .guardrails import (
    guardrails,
    check_input_safety,
    check_domain_intent,
    OFF_TOPIC_REFUSAL,
    BENCHMARK_REFUSAL,
    INJECTION_REFUSAL,
    GuardrailVerdict,
)
from .groq_client import groq_client, LLM_UNAVAILABLE
from ..database.repositories import log_audit
from ..observability.langsmith import traced_operation
from ..tools.qa_tools import (
    get_thread_documents_tool,
    get_reconciliation_summary_tool,
    get_unmatched_transactions_tool,
    get_ambiguous_transactions_tool,
    get_transaction_result_tool,
    get_material_exceptions_tool,
    get_metrics_tool,
    run_cash_forecast_tool,
    run_tax_match_tool,
)


# ─────────────────────────────────────────────────────────────
# Node 1: Guard input (Layer 1 + Layer 2)
# ─────────────────────────────────────────────────────────────

def guard_input_node(state: QAState) -> Dict[str, Any]:
    """Layers 1 & 2: input safety, then domain/intent validation."""
    question = state.get("question", "")

    verdict, refusal = check_input_safety(question)
    if verdict == GuardrailVerdict.BLOCK:
        return {"guardrail_passed": False, "guardrail_refusal": refusal, "guardrail_layer": "INPUT_SAFETY"}

    verdict, refusal = check_domain_intent(question)
    if verdict == GuardrailVerdict.BLOCK:
        return {"guardrail_passed": False, "guardrail_refusal": refusal, "guardrail_layer": "DOMAIN_INTENT"}

    return {"guardrail_passed": True, "guardrail_refusal": None, "guardrail_layer": None}


def route_guardrail(state: QAState) -> str:
    if state.get("guardrail_passed"):
        return "understand_question"
    return "refuse_off_topic"


def refuse_off_topic_node(state: QAState) -> Dict[str, Any]:
    """Persist the guardrail decision to the audit trail and emit refusal."""
    question = state.get("question", "")
    refusal = state.get("guardrail_refusal") or OFF_TOPIC_REFUSAL
    layer = state.get("guardrail_layer") or "UNKNOWN"
    thread_id = state.get("thread_id", "")
    db = state.get("db_session")

    if db is not None:
        log_audit(
            db=db,
            thread_id=thread_id,
            action="GUARDRAIL_BLOCK",
            agent="Guardrail_Layer",
            parameters={"layer": layer},
            result_summary=refusal[:200],
        )

    return {
        "answer": refusal,
        "answer_source": "refusal",
        "query_type": "OFF_TOPIC",
        "retrieved_records": [],
        "retrieved_exceptions": [],
        "retrieved_metrics": {},
        "retrieved_documents": [],
    }


# ─────────────────────────────────────────────────────────────
# Node 2: Understand question (intent + identifiers)
# ─────────────────────────────────────────────────────────────

def understand_question_node(state: QAState) -> Dict[str, Any]:
    question = state.get("question", "")
    lower = question.lower()

    # Extract transaction / reference IDs
    txn_matches = re.findall(r'\b[A-Za-z0-9]+[-_][A-Za-z0-9-_]+\b', question)
    num_matches = re.findall(r'(?:txn|transaction|id|ref)[\s#:]*([0-9]+)', lower)
    for n in num_matches:
        txn_matches.append(n)

    query_type = "GENERAL"
    if txn_matches:
        query_type = "SPECIFIC_RECORD"
    elif any(kw in lower for kw in ["cash forecast", "forecast cash", "forecast my cash", "cash position", "projected cash", "future cash", "inflow forecast", "outflow forecast", "ending cash", "forecast for the next", "forecast my"]):
        query_type = "CASH_FORECAST"
    elif any(kw in lower for kw in ["tax match", "tax-line", "tax line", "tax mismatch", "tax rate", "check whether tax", "show me tax", "tax differences", "gst", "vat", "tds"]):
        query_type = "TAX_MATCH"
    elif any(kw in lower for kw in ["material", "serious", "high priority", "critical", "severe"]):
        query_type = "MATERIAL_EXCEPTIONS"
    elif any(kw in lower for kw in ["ambiguous", "multiple candidate", "held"]):
        query_type = "AMBIGUOUS_QUERY"
    elif any(kw in lower for kw in ["match rate", "accuracy", "precision", "recall", "throughput", "metrics", "f1", "reconciliation rate"]):
        query_type = "METRIC_QUERY"
    elif any(kw in lower for kw in ["amount discrepanc", "difference", "discrepanc", "fee", "delta", "mismatch", "refund", "chargeback"]):
        query_type = "DISCREPANCY_QUERY"
    elif any(kw in lower for kw in ["unmatched", "failing", "why unmatched", "why are there", "exceptions", "unresolved", "missing", "explain", "explanation"]):
        query_type = "EXCEPTION_QUERY"
    elif any(kw in lower for kw in ["document", "uploaded", "files", "fingerprint", "sha256", "digest", "provenance"]):
        query_type = "DOCUMENT_QUERY"
    elif any(kw in lower for kw in ["summary", "overview", "status", "results"]):
        query_type = "SUMMARY_QUERY"
    elif any(kw in lower for kw in ["audit", "history", "log", "trail"]):
        query_type = "UNSUPPORTED_QUERY"

    return {
        "query_type": query_type,
        "extracted_record_ids": list(dict.fromkeys(txn_matches)),
        "extracted_entities": [],
    }


# ─────────────────────────────────────────────────────────────
# Node 3: Retrieve evidence (Layer 3 thread scope + Layer 4 tool permission)
# ─────────────────────────────────────────────────────────────

def retrieve_relevant_records_node(state: QAState) -> Dict[str, Any]:
    """
    Execute deterministic tools, each individually permission-checked and
    traced. Requires a db_session — never opens its own SessionLocal().
    """
    thread_id = state.get("thread_id", "")
    run_id = state.get("run_id")
    question = state.get("question", "")
    lower = question.lower()
    query_type = state.get("query_type", "GENERAL")
    record_ids = state.get("extracted_record_ids", [])
    db = state.get("db_session")

    if db is None:
        return {
            "retrieved_records": [],
            "retrieved_exceptions": [],
            "retrieved_metrics": {},
            "retrieved_documents": [],
            "tools_called": [],
            "answer": "Internal error: database session is not available for this request.",
            "answer_source": "deterministic",
        }

    # Layer 3: thread scope must be valid before any tool runs
    scope_ok, scope_refusal = guardrails.validate_thread_scope(db, thread_id)
    if not scope_ok:
        return {
            "retrieved_records": [],
            "retrieved_exceptions": [],
            "retrieved_metrics": {},
            "retrieved_documents": [],
            "tools_called": [],
            "answer": scope_refusal,
            "answer_source": "refusal",
        }

    retrieved_records: List[Dict[str, Any]] = []
    retrieved_exceptions: List[Dict[str, Any]] = []
    retrieved_metrics: Dict[str, Any] = {}
    retrieved_documents: List[Dict[str, Any]] = []
    tools_called: List[str] = []

    def run_tool(tool_name: str, fn):
        """Layer 4: verify tool permission before execution, then trace it."""
        if not guardrails.validate_tool_permission(tool_name):
            log_audit(
                db=db, thread_id=thread_id, action="TOOL_PERMISSION_DENIED",
                agent="Guardrail_Layer", tool=tool_name,
                result_summary="Blocked unauthorized tool invocation",
            )
            return None
        tools_called.append(tool_name)
        with traced_operation(tool_name, thread_id=thread_id, run_id=run_id, operation="qa_tool"):
            log_audit(
                db=db, thread_id=thread_id, action="QA_TOOL_CALL",
                agent="QA_Copilot_Agent", tool=tool_name,
                parameters={"query_type": query_type},
                run_id=run_id,
            )
            return fn()

    # 1. SPECIFIC RECORD QUERY
    if query_type == "SPECIFIC_RECORD" and record_ids:
        for rid in record_ids:
            res = run_tool(
                "get_transaction_result_tool",
                lambda rid=rid: get_transaction_result_tool(db, thread_id=thread_id, record_id=rid),
            )
            if not res:
                continue
            if res.get("type") in ["MATCHED", "DOCUMENT_RECORD", "AMBIGUOUS"]:
                retrieved_records.append(res)
            elif res.get("type") == "EXCEPTION":
                retrieved_exceptions.append(res)
            elif res.get("type") == "NOT_FOUND":
                retrieved_records.append(res)

    # 2. MATERIAL DISCREPANCIES
    elif query_type == "MATERIAL_EXCEPTIONS":
        mat_excs = run_tool(
            "get_material_exceptions_tool",
            lambda: get_material_exceptions_tool(db, thread_id=thread_id, limit=20),
        )
        retrieved_exceptions.extend(mat_excs or [])

    # 3. AMBIGUOUS TRANSACTIONS
    elif query_type == "AMBIGUOUS_QUERY":
        amb_excs = run_tool(
            "get_ambiguous_transactions_tool",
            lambda: get_ambiguous_transactions_tool(db, thread_id=thread_id, limit=20),
        )
        retrieved_exceptions.extend(amb_excs or [])

    # 4. METRICS
    elif query_type == "METRIC_QUERY":
        retrieved_metrics = run_tool(
            "get_metrics_tool",
            lambda: get_metrics_tool(db, thread_id=thread_id),
        ) or {}

    # 5. DISCREPANCY / FEE QUERY
    elif query_type == "DISCREPANCY_QUERY":
        unmatched = run_tool(
            "get_unmatched_transactions_tool",
            lambda: get_unmatched_transactions_tool(db, thread_id=thread_id, limit=20),
        ) or []
        fee_diffs = [e for e in unmatched if e.get("reason_code") == "AMOUNT_MISMATCH"]
        retrieved_exceptions.extend(fee_diffs if fee_diffs else unmatched)

    # 6. EXCEPTION QUERY
    elif query_type == "EXCEPTION_QUERY":
        unmatched = run_tool(
            "get_unmatched_transactions_tool",
            lambda: get_unmatched_transactions_tool(db, thread_id=thread_id, limit=20),
        ) or []
        retrieved_exceptions.extend(unmatched)

    # 7. DOCUMENT QUERY
    elif query_type == "DOCUMENT_QUERY":
        docs = run_tool(
            "get_thread_documents_tool",
            lambda: get_thread_documents_tool(db, thread_id=thread_id),
        )
        retrieved_documents.extend(docs or [])

    # 8. CASH FORECAST QUERY
    elif query_type == "CASH_FORECAST":
        h_days = 30 if ("30" in lower or "month" in lower) else 7
        fct_res = run_tool(
            "run_cash_forecast_tool",
            lambda: run_cash_forecast_tool(db, thread_id=thread_id, horizon_days=h_days),
        )
        if fct_res:
            retrieved_metrics["cash_forecast"] = fct_res

    # 9. TAX-LINE MATCH QUERY
    elif query_type == "TAX_MATCH":
        tax_res = run_tool(
            "run_tax_match_tool",
            lambda: run_tax_match_tool(db, thread_id=thread_id),
        )
        if tax_res:
            retrieved_metrics["tax_match"] = tax_res

    # 10. GENERAL / SUMMARY
    else:
        retrieved_metrics = run_tool(
            "get_reconciliation_summary_tool",
            lambda: get_reconciliation_summary_tool(db, thread_id=thread_id, run_id=run_id),
        ) or {}

    return {
        "retrieved_records": retrieved_records,
        "retrieved_exceptions": retrieved_exceptions,
        "retrieved_metrics": retrieved_metrics,
        "retrieved_documents": retrieved_documents,
        "tools_called": tools_called,
    }


# ─────────────────────────────────────────────────────────────
# Deterministic evidence formatter (offline / fallback path)
# ─────────────────────────────────────────────────────────────

def _fmt_amount(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def format_deterministic_answer(state: QAState) -> str:
    """
    Compose a response strictly from retrieved evidence. If nothing was
    retrieved, say so honestly — never fabricate numbers.
    """
    question = state.get("question", "")
    query_type = state.get("query_type", "GENERAL")
    records = state.get("retrieved_records", [])
    exceptions = state.get("retrieved_exceptions", [])
    metrics = state.get("retrieved_metrics", {})
    documents = state.get("retrieved_documents", [])
    thread_id = state.get("thread_id", "")

    if query_type == "UNSUPPORTED_QUERY":
        return "I am unable to answer queries about audit history or system logs as they are outside my supported capabilities. I can help you with reconciliation status, mismatched amounts, missing transactions, fees, tax, and cash forecasting."

    # ── Honest no-data states ──
    if query_type == "CASH_FORECAST":
        fct = metrics.get("cash_forecast") or {}
        if fct.get("status") == "INSUFFICIENT_DATA":
            return fct.get("message", "Insufficient historical transactions or settlement records in this thread to project future cash flows.")
        horizon = fct.get("horizon_days", 7)
        curr = _fmt_amount(fct.get("current_cash_balance", 0.0))
        baseline_src = (fct.get("baseline_source") or "UNAVAILABLE").replace("_", " ").title()
        inflows = _fmt_amount(fct.get("projected_inflows", 0.0))
        outflows = _fmt_amount(fct.get("projected_outflows", 0.0))
        net = _fmt_amount(fct.get("net_projected_change", 0.0))
        ending = _fmt_amount(fct.get("projected_ending_cash", 0.0))
        confidence = fct.get("confidence_level", "MEDIUM")

        lines = [
            f"**Deterministic Cash Position Forecast ({horizon}-Day Horizon)**",
            "",
            f"• **Current / Baseline Cash:** {curr} (Source: {baseline_src})",
            f"• **Expected Inflows:** {inflows} (Forecast)",
            f"• **Expected Outflows / Fees:** {outflows} (Forecast)",
            f"• **Net Projected Change:** {net}",
            f"• **Projected Ending Cash Position:** {ending} (FORECAST)",
            f"• **Confidence Level:** {confidence}",
            "",
            "**Forecasting Methodology:**",
            f"{fct.get('methodology', 'Deterministic moving average')}",
            "",
            "**Assumptions:**",
        ]
        for a in fct.get("assumptions", []):
            lines.append(f"• {a}")
        return "\n".join(lines)

    if query_type == "TAX_MATCH":
        tax_res = metrics.get("tax_match") or {}
        if tax_res.get("status") == "NO_DATA":
            return tax_res.get("message", "No financial records found in this thread to perform tax matching.")
        tot = tax_res.get("total_records", 0)
        eligible = tax_res.get("tax_eligible_count", tot)
        matched = tax_res.get("matched_count", 0)
        mismatched = tax_res.get("mismatched_count", 0)
        missing = tax_res.get("missing_count", 0)
        not_applicable = tax_res.get("not_applicable_count", 0)
        unavailable = tax_res.get("unavailable_count", 0)
        rate = tax_res.get("tax_match_rate", 0.0)
        exp_tax = _fmt_amount(tax_res.get("total_tax_expected", 0.0))
        rep_tax = _fmt_amount(tax_res.get("total_tax_reported", 0.0))
        diff = _fmt_amount(tax_res.get("total_tax_discrepancy", 0.0))
        net_var = _fmt_amount(tax_res.get("net_tax_variance", 0.0))

        lines = [
            f"**Tax-Line Matching Analysis ({rate:.1f}% Match Rate)**",
            "",
            f"• **Total Financial Records Analyzed:** {tot}",
            f"• **Tax-Eligible Lines:** {eligible}",
            f"• **Matched Lines:** {matched} ({rate:.1f}% of eligible)",
            f"• **Tax Mismatches:** {mismatched}",
            f"• **Missing Tax Lines:** {missing}",
            f"• **Not Tax Applicable:** {not_applicable}",
        ]
        if unavailable:
            lines.append(f"• **Tax Data Unavailable:** {unavailable}")
        lines += [
            f"• **Total Expected Tax:** {exp_tax} (Calculated: taxable × rate)",
            f"• **Total Reported Tax:** {rep_tax}",
            f"• **Absolute Tax Variance:** {diff}",
            f"• **Net (Signed) Tax Variance:** {net_var}",
        ]
        if mismatched > 0 or missing > 0:
            lines.append("\n**Discrepancy Details:**")
            discrepancies = [t for t in tax_res.get("tax_lines", []) if t.get("status") in ("MISMATCH", "MISSING")][:5]
            for d in discrepancies:
                lines.append(f"• Record `{d.get('record_id')}` ({d.get('status')}): {d.get('explanation')}")
        return "\n".join(lines)

    if query_type == "METRIC_QUERY" or query_type == "SUMMARY_QUERY" or query_type == "GENERAL":
        if metrics.get("status") == "NO_DATA":
            return "There is not enough processed data in this thread to answer that question. No documents have been uploaded and no reconciliation has been run."
        if metrics.get("status") == "PENDING_RECONCILIATION":
            return metrics.get("message", "Reconciliation has not been run for this thread yet.")
        if metrics.get("status") == "INVALID_THREAD":
            return "Thread ID is required to answer this question."
        if not metrics:
            return "There is not enough processed data in this thread to answer that question."

    if query_type == "SPECIFIC_RECORD":
        for res in records:
            if res.get("type") == "NOT_FOUND":
                return res.get(
                    "message",
                    f"No such transaction exists in this thread.",
                )
            if res.get("type") == "AMBIGUOUS":
                return res.get("message", "The identifier matches multiple records in this thread. Please provide a more specific identifier.")

    # ── SPECIFIC RECORD ──
    if query_type == "SPECIFIC_RECORD":
        for e in exceptions:
            if e.get("type") == "EXCEPTION":
                return (
                    f"Record **{e.get('record_id')}** is currently **UNRESOLVED** (Reason: `{e.get('reason_code')}`).\n\n"
                    f"- **Source**: {e.get('source')}\n"
                    f"- **Amount**: {_fmt_amount(e.get('amount'))}\n"
                    f"- **Explanation**: {e.get('explanation')}\n"
                    f"- **Difference**: {_fmt_amount(e.get('amount_discrepancy'))}\n"
                    f"- **Severity**: `{e.get('discrepancy_category', 'MATERIAL')}`\n\n"
                    f"Evidence: exception `{e.get('exception_id')}` in thread `{thread_id}`."
                )
        for r in records:
            if r.get("type") == "DOCUMENT_RECORD":
                return (
                    f"Record **{r.get('record_id')}** is uploaded in source **{r.get('source')}** "
                    f"with recorded amount **{_fmt_amount(r.get('amount'))}** "
                    f"(Reference: `{r.get('reference_id', 'N/A')}`, Date: {r.get('date', 'N/A')}, Entity: {r.get('entity', 'N/A')}). "
                    f"It has not been reconciled yet."
                )
            if r.get("type") == "MATCHED":
                ev = r.get("evidence", {})
                return (
                    f"Record **{r.get('record_id_a')}** was matched with **{r.get('record_id_b')}**.\n\n"
                    f"- **Confidence Score**: {r.get('confidence_score')}%\n"
                    f"- **Match Category**: {r.get('match_category')}\n"
                    f"- **Ledger Amount**: {_fmt_amount(r.get('amount_a'))}\n"
                    f"- **Bank Amount**: {_fmt_amount(r.get('amount_b'))}\n"
                    f"- **Date Difference**: {ev.get('date_difference_days', 0)} day(s)\n"
                    f"- **Status**: {r.get('status')}\n\n"
                    f"Evidence: match `{r.get('match_id')}` in thread `{thread_id}`."
                )
        return "No such transaction exists in this thread."

    # ── MATERIAL EXCEPTIONS ──
    if query_type == "MATERIAL_EXCEPTIONS":
        if not exceptions:
            return "There are no material exceptions in this thread."
        lines = [f"Found **{len(exceptions)}** material discrepancies requiring controller review:"]
        limit = 25
        for e in exceptions[:limit]:
            lines.append(
                f"- **{e.get('record_id')}** ({e.get('source')}): {e.get('explanation')}"
            )
        if len(exceptions) > limit:
            lines.append(f"...and {len(exceptions) - limit} more.")
            lines.append("[View all exceptions in Investigator](action:view_exceptions)")
        return "\n".join(lines)

    # ── EXCEPTION / DISCREPANCY QUERY ──
    if query_type in ("EXCEPTION_QUERY", "DISCREPANCY_QUERY"):
        if not exceptions:
            return "There are no unresolved exceptions in this thread."
        reason_counts: Dict[str, int] = {}
        for e in exceptions:
            rc = e.get("reason_code", "OTHER")
            reason_counts[rc] = reason_counts.get(rc, 0) + 1

        lines = [f"There are **{len(exceptions)}** exceptions in this thread:"]
        for rc, count in sorted(reason_counts.items()):
            if rc == "AMOUNT_MISMATCH":
                lines.append(f"- **{count}** have amount mismatches (fee deductions or partial settlements).")
            elif rc == "AMBIGUOUS_CANDIDATE_CONFLICT":
                lines.append(f"- **{count}** have multiple candidate matches with close scores.")
            elif rc == "MISSING_COUNTERPART":
                lines.append(f"- **{count}** have no counterpart transaction in the other source.")
            elif rc == "DUPLICATE_TRANSACTION":
                lines.append(f"- **{count}** are duplicate bookings.")
            elif rc == "UNRECORDED_TRANSACTION":
                lines.append(f"- **{count}** were processed by the counterpart but are unrecorded in the ledger.")
            else:
                lines.append(f"- **{count}** classified under `{rc}`.")
        if query_type == "DISCREPANCY_QUERY":
            top = sorted(
                (e for e in exceptions if e.get("amount_discrepancy")),
                key=lambda e: e.get("amount_discrepancy", 0),
                reverse=True,
            )[:3]
            for e in top:
                lines.append(
                    f"- Largest: **{e.get('record_id')}** differs by {_fmt_amount(e.get('amount_discrepancy'))} ({e.get('reason_code')})."
                )
        return "\n".join(lines)

    # ── AMBIGUOUS QUERY ──
    if query_type == "AMBIGUOUS_QUERY":
        if not exceptions:
            return "There are no ambiguous multi-candidate transactions held for review in this thread."
        lines = [f"Found **{len(exceptions)}** transactions held for review due to ambiguous candidates:"]
        for e in exceptions[:5]:
            cand_ids = [c.get("target_record_id") for c in (e.get("candidates") or [])[:2]]
            lines.append(f"- **{e.get('record_id')}**: candidates {', '.join(cand_ids) if cand_ids else 'multiple'}")
        return "\n".join(lines)

    # ── METRIC / SUMMARY QUERY ──
    if query_type in ("METRIC_QUERY", "SUMMARY_QUERY", "GENERAL"):
        evaluated = metrics.get("evaluated", False)
        lines = [
            f"### Reconciliation Summary (Thread: {thread_id})",
            f"- **Total Records Processed**: {metrics.get('total_records', 0)}",
            f"- **Reconciled Pairs**: {metrics.get('matched_count', 0)}",
            f"- **Exceptions**: {metrics.get('exceptions_count', 0)}",
            f"- **Match Rate**: {metrics.get('match_rate', 0):.1f}%",
        ]
        diag = metrics.get("diagnostics", {})
        if diag and isinstance(diag, dict):
            zero_diag = diag.get("zero_match_diagnostics")
            if zero_diag:
                lines.append(f"- **Diagnostics**: {zero_diag}")
            brk = diag.get("rejection_breakdown", {})
            if brk and isinstance(brk, dict):
                active_rejections = [f"{k}: {v}" for k, v in brk.items() if v > 0]
                if active_rejections:
                    lines.append(f"- **Rejection Breakdown**: {', '.join(active_rejections)}")

        mapped = metrics.get("mapped_columns", {})
        if mapped and isinstance(mapped, dict):
            lines.append(f"- **Semantic Column Mappings**: Active across {len(mapped)} document(s)")

        if evaluated:
            lines += [
                f"- **Accuracy**: {metrics.get('accuracy', 0):.1f}%",
                f"- **Precision**: {metrics.get('precision', 0):.1f}%",
                f"- **Recall**: {metrics.get('recall', 0):.1f}%",
                f"- **F1**: {metrics.get('f1_score', 0):.1f}%",
            ]
        else:
            lines.append("- **Evaluation**: not available for this run (no authorized ground truth was associated with it).")
        lines.append(f"- **Throughput**: {metrics.get('throughput_records_sec', 0):.0f} records/sec")
        return "\n".join(lines)

    # ── DOCUMENT QUERY ──
    if query_type == "DOCUMENT_QUERY":
        if not documents:
            return "No documents have been uploaded to this thread yet."
        lines = [f"Found **{len(documents)}** registered documents in this thread:"]
        for d in documents[:8]:
            lines.append(
                f"- **{d.get('filename')}** ({d.get('document_type')}): {d.get('record_count')} records (SHA256: `{(d.get('sha256') or '')[:16]}…`)"
            )
        return "\n".join(lines)

    # Empty retrieval for other intents
    if not records and not exceptions and not documents and not metrics:
        return "There is not enough processed data in this thread to answer that question."

    return "There is not enough processed data in this thread to answer that question."


# ─────────────────────────────────────────────────────────────
# Node 4: Generate answer (LLM path + Layer 5 + Layer 6)
# ─────────────────────────────────────────────────────────────

def generate_answer_node(state: QAState) -> Dict[str, Any]:
    question = state.get("question", "")
    query_type = state.get("query_type", "GENERAL")
    thread_id = state.get("thread_id", "")
    records = [r for r in state.get("retrieved_records", [])]
    exceptions = [e for e in state.get("retrieved_exceptions", [])]
    metrics = dict(state.get("retrieved_metrics", {}))
    documents = list(state.get("retrieved_documents", []))
    db = state.get("db_session")

    # Strip internal evidence metadata before prompting/validating
    def strip_meta(items):
        cleaned = []
        for it in items:
            if isinstance(it, dict):
                it = {k: v for k, v in it.items() if k != "_meta"}
                if "evidence" in it and isinstance(it["evidence"], dict):
                    it["evidence"] = {k: v for k, v in it["evidence"].items() if k != "_meta"}
            cleaned.append(it)
        return cleaned

    records_clean = strip_meta(records)
    exceptions_clean = strip_meta(exceptions)
    metrics_clean = {k: v for k, v in metrics.items() if k != "_meta"}
    documents_clean = strip_meta(documents)

    # 1) Deterministic answer — always computed first (grounding baseline)
    deterministic_answer = format_deterministic_answer(state)

    # Passthrough: retrieval node may have already produced a terminal answer
    # (thread-scope refusal or missing-session internal error).
    passthrough_answer = state.get("answer") or ""
    if passthrough_answer and state.get("answer_source") in ("refusal", "deterministic"):
        if passthrough_answer.startswith("Internal error:") or state.get("answer_source") == "refusal":
            sanitized = guardrails.validate_output(passthrough_answer)
            return {
                "answer": sanitized,
                "answer_source": state.get("answer_source", "refusal"),
                "retrieved_records": records,
                "retrieved_exceptions": exceptions,
                "retrieved_metrics": metrics,
                "retrieved_documents": documents,
            }

    answer = deterministic_answer
    answer_source = "deterministic"

    # 2) Optional LLM synthesis via Groq — ONLY over the retrieved evidence
    if groq_client.is_available:
        evidence_prompt = (
            f"Thread ID: {thread_id}\n"
            f"User Question: {question}\n"
            f"Query Intent: {query_type}\n"
            f"Retrieved Metrics: {metrics_clean}\n"
            f"Retrieved Records: {records_clean}\n"
            f"Retrieved Exceptions: {exceptions_clean}\n"
            f"Retrieved Documents: {documents_clean}\n\n"
            "Instructions:\n"
            "1. Answer ONLY from the retrieved evidence above. Never invent numbers or IDs.\n"
            "2. If the user asserts a value that differs from the evidence (e.g. asks 'is TX01 $999?' when evidence says $1,500.00), "
            "explicitly correct them with the recorded value.\n"
            "3. Cite the relevant transaction / exception / document ids from the evidence.\n"
            "4. If the evidence is empty or a NO_DATA/PENDING status is present, say there is not enough processed data.\n"
        )
        with traced_operation("groq_answer", thread_id=thread_id, operation="llm_answer"):
            llm_answer = groq_client.generate_text(
                prompt=evidence_prompt,
                system_instruction=(
                    "You are the AI Finance Controller Copilot. Answer financial reconciliation "
                    "questions concisely and accurately using ONLY the provided evidence. Never fabricate."
                ),
            )
        if llm_answer not in ("", None, LLM_UNAVAILABLE):
            # Layer 5: numeric consistency — every number must come from evidence
            ok, reason = guardrails.validate_evidence(
                llm_answer,
                retrieved_records=records_clean,
                retrieved_exceptions=exceptions_clean,
                retrieved_metrics=metrics_clean,
                retrieved_documents=documents_clean,
            )
            if ok:
                answer = llm_answer
                answer_source = "llm_validated"
            else:
                # Unverified LLM output must never be shown; fall back to the
                # deterministic answer and record the rejection.
                answer = deterministic_answer
                answer_source = "deterministic"
                if db is not None:
                    log_audit(
                        db=db,
                        thread_id=thread_id,
                        action="QA_EVIDENCE_VALIDATION_FAILED",
                        agent="Guardrail_Layer",
                        parameters={"query_type": query_type},
                        result_summary=(reason or "")[:200],
                    )

    # Layer 6: output safety
    sanitized = guardrails.validate_output(answer)

    # Audit the Q&A exchange
    if db is not None:
        log_audit(
            db=db,
            thread_id=thread_id,
            action="QA_QUESTION_ANSWERED",
            agent="QA_Copilot_Agent",
            parameters={"query_type": query_type, "tools_called": state.get("tools_called", [])},
            result_summary=f"[{answer_source}] {sanitized[:120]}",
        )

    return {
        "answer": sanitized,
        "answer_source": answer_source,
        "retrieved_records": records,
        "retrieved_exceptions": exceptions,
        "retrieved_metrics": metrics,
        "retrieved_documents": documents,
    }


# ─────────────────────────────────────────────────────────────
# Graph compilation
# ─────────────────────────────────────────────────────────────

def build_qa_graph():
    builder = StateGraph(QAState)

    builder.add_node("guard_input", guard_input_node)
    builder.add_node("refuse_off_topic", refuse_off_topic_node)
    builder.add_node("understand_question", understand_question_node)
    builder.add_node("retrieve_relevant_records", retrieve_relevant_records_node)
    builder.add_node("generate_answer", generate_answer_node)

    builder.add_edge(START, "guard_input")
    builder.add_conditional_edges(
        "guard_input",
        route_guardrail,
        {
            "understand_question": "understand_question",
            "refuse_off_topic": "refuse_off_topic"
        }
    )
    builder.add_edge("refuse_off_topic", END)
    builder.add_edge("understand_question", "retrieve_relevant_records")
    builder.add_edge("retrieve_relevant_records", "generate_answer")
    builder.add_edge("generate_answer", END)

    return builder.compile()


qa_graph = build_qa_graph()
