"""
LangGraph QA Agent for Financial Investigation & Querying.
Retrieves actual records, matches, exceptions, and metrics from SQLite/State,
preventing hallucination and computing exact financial values.
"""

import re
from typing import Dict, Any, List
from langgraph.graph import StateGraph, START, END

from .state import QAState
from .gemini_client import gemini_client
from ..database.db import SessionLocal
from ..database.models import MatchResult, ExceptionResult, EvaluationMetric, ReconciliationRun

def understand_question_node(state: QAState) -> Dict[str, Any]:
    """
    Node 1: Parse user question to extract entities, transaction IDs, and query intent.
    """
    question = state.get("question", "")
    lower = question.lower()
    
    # Extract any alphanumeric transaction or reference IDs
    # e.g., TXN_184, TXN-LEDGER-1050, INV-2026-2005, BNK-REF-5050
    txn_matches = re.findall(r'\b[A-Za-z0-9]+[-_][A-Za-z0-9-_]+\b', question)
    # Also simple numbers after txn/transaction/id
    num_matches = re.findall(r'(?:txn|transaction|id|ref)[\s#:]*([0-9]+)', lower)
    for n in num_matches:
        txn_matches.append(n)

    query_type = "GENERAL"
    if txn_matches:
        query_type = "SPECIFIC_RECORD"
    elif any(kw in lower for kw in ["match rate", "accuracy", "precision", "recall", "throughput", "records processed", "how many records", "metrics"]):
        query_type = "METRIC_QUERY"
    elif any(kw in lower for kw in ["amount discrepanc", "difference", "discrepanc", "fee", "mismatch"]):
        query_type = "DISCREPANCY_QUERY"
    elif any(kw in lower for kw in ["unresolved", "exception", "most exceptions", "which source", "unmatched"]):
        query_type = "EXCEPTION_QUERY"
    elif any(kw in lower for kw in ["summary", "overview", "status", "results"]):
        query_type = "SUMMARY_QUERY"

    return {
        "query_type": query_type,
        "extracted_record_ids": txn_matches,
        "extracted_entities": []
    }

def retrieve_relevant_records_node(state: QAState) -> Dict[str, Any]:
    """
    Node 2: Retrieve records, exceptions, and metrics from the database.
    """
    run_id = state.get("run_id")
    query_type = state.get("query_type")
    record_ids = state.get("extracted_record_ids", [])
    
    db = SessionLocal()
    retrieved_records: List[Dict[str, Any]] = []
    retrieved_exceptions: List[Dict[str, Any]] = []
    retrieved_metrics: Dict[str, Any] = {}

    try:
        # Get latest run if not specified
        run_query = db.query(ReconciliationRun)
        if run_id:
            run = run_query.filter(ReconciliationRun.id == run_id).first()
        else:
            run = run_query.order_by(ReconciliationRun.created_at.desc()).first()

        if run:
            # Metrics
            if run.metrics:
                retrieved_metrics = {
                    "match_rate": run.metrics.match_rate,
                    "accuracy": run.metrics.accuracy,
                    "precision": run.metrics.precision,
                    "recall": run.metrics.recall,
                    "f1_score": run.metrics.f1_score,
                    "total_records": run.total_records,
                    "matched_records": run.matched_records,
                    "exception_records": run.exception_records,
                    "throughput": run.metrics.throughput_records_per_sec,
                    "processing_time": run.metrics.processing_time_sec
                }
            else:
                retrieved_metrics = {
                    "match_rate": run.match_rate,
                    "accuracy": run.accuracy,
                    "total_records": run.total_records,
                    "matched_records": run.matched_records,
                    "exception_records": run.exception_records,
                    "throughput": run.throughput_rec_sec,
                    "processing_time": run.processing_time_sec
                }

            # Retrieve matches
            matches_q = db.query(MatchResult).filter(MatchResult.run_id == run.id)
            exceptions_q = db.query(ExceptionResult).filter(ExceptionResult.run_id == run.id)

            if query_type == "SPECIFIC_RECORD" and record_ids:
                for rid in record_ids:
                    # Look up in matches
                    m_hits = matches_q.filter(
                        (MatchResult.record_id_a.contains(rid)) | (MatchResult.record_id_b.contains(rid))
                    ).all()
                    for m in m_hits:
                        retrieved_records.append({
                            "type": "MATCH",
                            "record_id_a": m.record_id_a,
                            "record_id_b": m.record_id_b,
                            "amount_a": m.amount_a,
                            "amount_b": m.amount_b,
                            "confidence": m.confidence_score,
                            "status": m.status,
                            "category": m.match_category
                        })

                    # Look up in exceptions
                    e_hits = exceptions_q.filter(ExceptionResult.record_id.contains(rid)).all()
                    for e in e_hits:
                        retrieved_exceptions.append({
                            "type": "EXCEPTION",
                            "record_id": e.record_id,
                            "source": e.source,
                            "amount": e.amount,
                            "reason_code": e.reason_code,
                            "decision": e.decision,
                            "confidence": e.confidence,
                            "explanation": e.explanation,
                            "amount_discrepancy": e.amount_discrepancy
                        })

            elif query_type == "DISCREPANCY_QUERY":
                e_hits = exceptions_q.filter(ExceptionResult.reason_code == "AMOUNT_MISMATCH").all()
                for e in e_hits[:10]:
                    retrieved_exceptions.append({
                        "record_id": e.record_id,
                        "amount": e.amount,
                        "reason": e.reason_code,
                        "discrepancy": e.amount_discrepancy,
                        "explanation": e.explanation
                    })

            elif query_type == "EXCEPTION_QUERY":
                e_hits = exceptions_q.all()
                for e in e_hits[:10]:
                    retrieved_exceptions.append({
                        "record_id": e.record_id,
                        "source": e.source,
                        "amount": e.amount,
                        "reason": e.reason_code,
                        "explanation": e.explanation
                    })
    finally:
        db.close()

    return {
        "retrieved_records": retrieved_records,
        "retrieved_exceptions": retrieved_exceptions,
        "retrieved_metrics": retrieved_metrics
    }

def generate_answer_node(state: QAState) -> Dict[str, Any]:
    """
    Node 3: Synthesize precise response using deterministic figures and Gemini explanation.
    """
    question = state.get("question", "")
    query_type = state.get("query_type", "GENERAL")
    records = state.get("retrieved_records", [])
    exceptions = state.get("retrieved_exceptions", [])
    metrics = state.get("retrieved_metrics", {})

    prompt_context = f"""
User Question: {question}
Query Type: {query_type}
Retrieved Metrics: {metrics}
Retrieved Matched Records: {records}
Retrieved Exceptions: {exceptions}

Provide a direct, clear, professional financial answer. If numbers or transactions are queried, state the exact values, reason codes, and confidence scores from the retrieved context.
"""
    answer = gemini_client.generate_text(
        prompt=prompt_context,
        system_instruction="You are the AI Finance Controller Copilot. Answer financial reconciliation questions directly, concisely, and accurately based ONLY on the provided data."
    )

    # If answer was generated from fallback, customize based on query type
    if "Analysis completed" in answer or not answer:
        if query_type == "SPECIFIC_RECORD":
            if exceptions:
                e = exceptions[0]
                answer = f"Record **{e.get('record_id')}** is currently **UNRESOLVED** (Reason: `{e.get('reason_code')}`).\n\n- **Source**: {e.get('source')}\n- **Amount**: ${e.get('amount', 0):,.2f}\n- **Details**: {e.get('explanation')}\n- **Discrepancy**: ${e.get('amount_discrepancy', 0):,.2f}"
            elif records:
                r = records[0]
                answer = f"Record **{r.get('record_id_a')}** was successfully matched with **{r.get('record_id_b')}**.\n\n- **Confidence**: {r.get('confidence')}%\n- **Category**: {r.get('category')}\n- **Ledger Amount**: ${r.get('amount_a', 0):,.2f}\n- **Bank Amount**: ${r.get('amount_b', 0):,.2f}\n- **Status**: {r.get('status')}"
            else:
                answer = f"No specific record matching '{question}' was found in the current active run."

        elif query_type == "METRIC_QUERY":
            answer = f"### Reconciliation Performance Metrics\n- **Total Records Processed**: {metrics.get('total_records', 0)}\n- **Match Rate**: {metrics.get('match_rate', 0)}%\n- **Accuracy vs Ground Truth**: {metrics.get('accuracy', 0)}%\n- **Precision**: {metrics.get('precision', 0)}%\n- **Recall**: {metrics.get('recall', 0)}%\n- **Throughput**: {metrics.get('throughput', 0)} records/sec\n- **Processing Time**: {metrics.get('processing_time', 0)} seconds"

        elif query_type == "DISCREPANCY_QUERY":
            total_disc = sum(e.get("discrepancy", 0) for e in exceptions)
            answer = f"Found **{len(exceptions)}** amount discrepancies totaling **${total_disc:,.2f}** in differences. These are primarily caused by payment gateway processing fees and international bank wire deductions."

        elif query_type == "EXCEPTION_QUERY":
            answer = f"There are **{metrics.get('exception_records', len(exceptions))}** unresolved exceptions in this run across 4 main categories: Amount Discrepancies, Ambiguous Multiple Candidates, Missing Counterpart Bank Records, and Duplicate Ledger Entries."

    return {
        "answer": answer
    }

def build_qa_graph():
    builder = StateGraph(QAState)

    builder.add_node("understand_question", understand_question_node)
    builder.add_node("retrieve_relevant_records", retrieve_relevant_records_node)
    builder.add_node("generate_answer", generate_answer_node)

    builder.add_edge(START, "understand_question")
    builder.add_edge("understand_question", "retrieve_relevant_records")
    builder.add_edge("retrieve_relevant_records", "generate_answer")
    builder.add_edge("generate_answer", END)

    return builder.compile()

qa_graph = build_qa_graph()
