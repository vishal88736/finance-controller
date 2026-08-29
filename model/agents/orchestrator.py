"""
Finance Controller Orchestrator.
Routes user intents to:
- Reconciliation Agent (Core Hackathon Workflow)
- QA & Investigation Agent (Context-Aware Q&A)
- Future Stubs: Tax-Line Matching, Forward Cash Forecasting
"""

import re
from typing import Dict, Any, List, Optional
from .reconciliation_graph import reconciliation_graph
from .qa_graph import qa_graph

class Orchestrator:
    def __init__(self):
        pass

    def route_intent(self, user_prompt: str) -> str:
        prompt = user_prompt.lower()
        if any(kw in prompt for kw in ["reconcil", "match these", "run reconciliation", "process files", "start matching", "compare records"]):
            return "RECONCILIATION"
        elif any(kw in prompt for kw in ["tax", "tax line", "gst", "vat", "withholding"]):
            return "TAX_MATCHING_FUTURE"
        elif any(kw in prompt for kw in ["forecast", "cash forecast", "runway", "projection", "forward cash"]):
            return "CASH_FORECASTING_FUTURE"
        else:
            return "QA"

    def handle_request(
        self,
        user_prompt: str,
        run_id: Optional[str] = None,
        uploaded_files: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        intent = self.route_intent(user_prompt)

        if intent == "RECONCILIATION":
            initial_state = {
                "run_id": run_id or "RUN-DEFAULT",
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
                "error": None
            }
            output_state = reconciliation_graph.invoke(initial_state)
            return {
                "intent": "RECONCILIATION",
                "status": "COMPLETED",
                "result": output_state.get("final_report"),
                "matches": output_state.get("matches"),
                "exceptions": output_state.get("exceptions"),
                "metrics": output_state.get("metrics"),
                "step_progress": output_state.get("step_progress")
            }

        elif intent == "QA":
            initial_qa_state = {
                "run_id": run_id,
                "question": user_prompt,
                "query_type": "GENERAL",
                "extracted_entities": [],
                "extracted_record_ids": [],
                "retrieved_records": [],
                "retrieved_exceptions": [],
                "retrieved_metrics": {},
                "answer": ""
            }
            output_state = qa_graph.invoke(initial_qa_state)
            return {
                "intent": "QA",
                "status": "COMPLETED",
                "answer": output_state.get("answer"),
                "retrieved_records": output_state.get("retrieved_records"),
                "retrieved_exceptions": output_state.get("retrieved_exceptions"),
                "retrieved_metrics": output_state.get("retrieved_metrics")
            }

        elif intent == "TAX_MATCHING_FUTURE":
            return {
                "intent": "TAX_MATCHING_FUTURE",
                "status": "NOT_IMPLEMENTED_STUB",
                "answer": "Tax-Line Matching Agent is an extensible module planned for future releases. The core multi-source reconciliation loop is currently active."
            }

        elif intent == "CASH_FORECASTING_FUTURE":
            return {
                "intent": "CASH_FORECASTING_FUTURE",
                "status": "NOT_IMPLEMENTED_STUB",
                "answer": "Forward Cash Forecaster is an extensible module planned for future releases. The core multi-source reconciliation loop is currently active."
            }

orchestrator = Orchestrator()
