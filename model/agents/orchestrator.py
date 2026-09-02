"""
Finance Controller Orchestrator.
Routes user requests based on intent and thread scope:
- Reconciliation Agent (canonical service → deterministic matching pipeline)
- QA & Financial Copilot Agent (structured query & evidence retrieval)
- Guardrails (six-layer validation before any execution)

Chat reconciliation uses the SAME canonical ReconciliationService as the REST
endpoint — documents come from the current thread only, and results are
persisted identically (run, matches, exceptions, evidence, audit, message).
"""

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .qa_graph import qa_graph
from .guardrails import guardrails, OFF_TOPIC_REFUSAL
from .state import QAState
from ..database.repositories import log_audit, add_message, get_thread
from ..observability.langsmith import get_langsmith_config
from ..services.reconciliation_service import run_reconciliation, ReconciliationError


class Orchestrator:
    """Single orchestration entrypoint for all thread interactions."""

    # ── Intent routing ──
    # These patterns match EXECUTION requests only — queries about existing
    # reconciliation results/summaries/metrics are handled by QA.
    RECONCILIATION_PATTERNS = [
        r"\b(run|start|execute|do|perform|kick\s+off|trigger|launch|begin)\s+(the\s+|a\s+)?(reconciliation|reconcile|matching)\b",
        r"\breconcile\s+(these|the|all|my|our)\s+(records|documents|files|data|transactions|sources)\b",
        r"\breconcile\s+(them|everything|it|now)\b",
        r"\bprocess\s+(the\s+|these\s+)?(files|documents|records)\b",
        r"\bcompare\s+(records|the\s+files|sources)\b",
        r"\bmatch\s+(these|the|all|my)\b.{0,20}\b(records|documents|files|transactions|data)\b",
        r"\banalyze\s+(my\s+)?(documents|files|uploads)\b",
        r"\bplease\s+reconcile\b",
    ]


    def __init__(self):
        pass

    def route_intent(self, user_prompt: str) -> str:
        """Classify user intent into RECONCILIATION, QA, or OFF_TOPIC (guarded)."""
        is_allowed, refusal = guardrails.validate_input(user_prompt)
        if not is_allowed:
            return "OFF_TOPIC"

        text = user_prompt.lower()
        if any(re.search(pat, text) for pat in self.RECONCILIATION_PATTERNS):
            return "RECONCILIATION"
        return "QA"

    # ── Main entrypoint ──
    def handle_request(
        self,
        db: Session,
        thread_id: str,
        user_prompt: str,
        run_id: Optional[str] = None,
        uploaded_files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Route a chat message. `db` is the caller's request-scoped session and is
        passed down through graph state — never re-created inside nodes.
        """
        # Thread must exist before doing anything (thread scope layer)
        scope_ok, scope_refusal = guardrails.validate_thread_scope(db, thread_id)
        if not scope_ok:
            return {
                "intent": "OFF_TOPIC",
                "status": "REFUSED",
                "answer": scope_refusal or OFF_TOPIC_REFUSAL,
                "retrieved_records": [],
                "retrieved_exceptions": [],
                "retrieved_metrics": {},
            }

        intent = self.route_intent(user_prompt)

        # ── 1. Off-topic rejection (audit-logged) ──
        if intent == "OFF_TOPIC":
            log_audit(
                db=db,
                thread_id=thread_id,
                action="GUARDRAIL_BLOCK",
                agent="Guardrail_Layer",
                parameters={"prompt": (user_prompt or "")[:200]},
                result_summary="Refusal message dispatched",
            )
            return {
                "intent": "OFF_TOPIC",
                "status": "REFUSED",
                "answer": OFF_TOPIC_REFUSAL,
                "retrieved_records": [],
                "retrieved_exceptions": [],
                "retrieved_metrics": {},
            }

        # ── 2. Reconciliation — canonical service over thread documents ──
        if intent == "RECONCILIATION":
            try:
                result = run_reconciliation(
                    db=db,
                    thread_id=thread_id,
                    user_prompt=user_prompt,
                    run_id=run_id,
                )
            except ReconciliationError as e:
                return {
                    "intent": "RECONCILIATION",
                    "status": "FAILED",
                    "answer": str(e),
                    "retrieved_records": [],
                    "retrieved_exceptions": [],
                    "retrieved_metrics": {},
                    "result": {},
                }

            return {
                "intent": "RECONCILIATION",
                "status": "COMPLETED",
                "run_id": result["run_id"],
                "answer": "",  # summary message already appended by the service
                "result": result["summary"],
                "matches": [],
                "exceptions": [],
                "metrics": result["summary"].get("evaluation_metrics", {}),
                "step_progress": result["step_progress"],
            }

        # ── 3. QA Copilot ──
        config = get_langsmith_config(
            thread_id=thread_id, run_id=run_id, agent_name="QA_Copilot_Agent", operation="qa"
        )
        initial_qa_state: QAState = {
            "thread_id": thread_id,
            "run_id": run_id,
            "question": user_prompt,
            "guardrail_passed": True,
            "guardrail_refusal": None,
            "guardrail_layer": None,
            "query_type": "GENERAL",
            "extracted_entities": [],
            "extracted_record_ids": [],
            "retrieved_records": [],
            "retrieved_exceptions": [],
            "retrieved_metrics": {},
            "retrieved_documents": [],
            "evidence": {},
            "tools_called": [],
            "answer": "",
            "answer_source": "deterministic",
            "db_session": db,
        }

        output_state = qa_graph.invoke(initial_qa_state, config=config)

        return {
            "intent": "QA",
            "status": "COMPLETED",
            "answer": output_state.get("answer"),
            "answer_source": output_state.get("answer_source", "deterministic"),
            "query_type": output_state.get("query_type"),
            "retrieved_records": output_state.get("retrieved_records", []),
            "retrieved_exceptions": output_state.get("retrieved_exceptions", []),
            "retrieved_metrics": output_state.get("retrieved_metrics", {}),
            "retrieved_documents": output_state.get("retrieved_documents", []),
            "tools_called": output_state.get("tools_called", []),
        }


orchestrator = Orchestrator()
