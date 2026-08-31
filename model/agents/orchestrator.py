"""
Finance Controller Orchestrator.
Routes user requests based on intent and thread scope:
- Reconciliation Agent (Core deterministic matching pipeline)
- QA & Financial Copilot Agent (Structured query & evidence retrieval)
- Guardrails (Rejection of off-topic or malicious queries)
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from .reconciliation_graph import reconciliation_graph
from .qa_graph import qa_graph
from .guardrails import guardrails, OFF_TOPIC_REFUSAL
from .state import ReconciliationState, QAState
from ..database.repositories import log_audit
from ..observability.langsmith import get_langsmith_config


class Orchestrator:
    def __init__(self):
        pass

    def route_intent(self, user_prompt: str) -> str:
        """Classify user intent into RECONCILIATION, QA, or OFF_TOPIC."""
        is_allowed, refusal = guardrails.validate_input(user_prompt)
        if not is_allowed:
            return "OFF_TOPIC"

        prompt = user_prompt.lower()
        if any(kw in prompt for kw in [
            "reconcil", "match these", "run reconciliation", "process files",
            "start matching", "compare records", "run 200", "batch"
        ]):
            return "RECONCILIATION"
        else:
            return "QA"

    def handle_request(
        self,
        db: Session,
        thread_id: str,
        user_prompt: str,
        run_id: Optional[str] = None,
        uploaded_files: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Main orchestration entrypoint for all thread interactions.
        """
        intent = self.route_intent(user_prompt)

        # ── 1. Off-Topic Rejection ──
        if intent == "OFF_TOPIC":
            log_audit(
                db=db,
                thread_id=thread_id,
                action="OFF_TOPIC_REJECTED",
                agent="Guardrail_Layer",
                parameters={"prompt": user_prompt},
                result_summary="Refusal message dispatched"
            )
            return {
                "intent": "OFF_TOPIC",
                "status": "REFUSED",
                "answer": OFF_TOPIC_REFUSAL,
                "retrieved_records": [],
                "retrieved_exceptions": [],
                "retrieved_metrics": {}
            }

        # ── 2. Reconciliation Execution ──
        elif intent == "RECONCILIATION":
            config = get_langsmith_config(thread_id=thread_id, run_id=run_id, agent_name="Reconciliation_Agent")
            initial_state: ReconciliationState = {
                "thread_id": thread_id,
                "run_id": run_id or f"run_{thread_id[:8]}",
                "user_request": user_prompt,
                "uploaded_files": uploaded_files or [],
                "documents": [],
                "normalized_records": [],
                "candidates": [],
                "matches": [],
                "exceptions": [],
                "metrics": {},
                "final_report": {},
                "current_step": "init",
                "step_progress": [],
                "error": None,
                "db_session": db
            }

            output_state = reconciliation_graph.invoke(initial_state, config=config)
            
            log_audit(
                db=db,
                thread_id=thread_id,
                run_id=initial_state["run_id"],
                action="RECONCILIATION_COMPLETED",
                agent="Reconciliation_Agent",
                parameters={"prompt": user_prompt, "file_count": len(uploaded_files or [])},
                result_summary=f"Matched {len(output_state.get('matches', []))} pairs, {len(output_state.get('exceptions', []))} exceptions"
            )

            return {
                "intent": "RECONCILIATION",
                "status": "COMPLETED",
                "run_id": initial_state["run_id"],
                "result": output_state.get("final_report", {}),
                "matches": output_state.get("matches", []),
                "exceptions": output_state.get("exceptions", []),
                "metrics": output_state.get("metrics", {}),
                "step_progress": output_state.get("step_progress", [])
            }

        # ── 3. QA Copilot Query ──
        else:
            config = get_langsmith_config(thread_id=thread_id, run_id=run_id, agent_name="QA_Copilot_Agent")
            initial_qa_state: QAState = {
                "thread_id": thread_id,
                "run_id": run_id,
                "question": user_prompt,
                "guardrail_passed": True,
                "guardrail_refusal": None,
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
                "db_session": db
            }

            output_state = qa_graph.invoke(initial_qa_state, config=config)

            return {
                "intent": "QA",
                "status": "COMPLETED",
                "answer": output_state.get("answer"),
                "query_type": output_state.get("query_type"),
                "retrieved_records": output_state.get("retrieved_records", []),
                "retrieved_exceptions": output_state.get("retrieved_exceptions", []),
                "retrieved_metrics": output_state.get("retrieved_metrics", {}),
                "retrieved_documents": output_state.get("retrieved_documents", []),
                "tools_called": output_state.get("tools_called", [])
            }


orchestrator = Orchestrator()
