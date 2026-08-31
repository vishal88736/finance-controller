"""
LangSmith Observability & Tracing Integration.
Configures tracing hierarchy:
Thread -> Agent Run -> Router -> Tools -> Decision -> Q&A -> Final Response.
"""

import os
from typing import Optional, Dict, Any
from contextlib import contextmanager

# Read standard LangChain / LangSmith environment variables
LANGSMITH_TRACING = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() in ["true", "1", "yes"]
LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "ai-finance-controller")
LANGSMITH_API_KEY = os.environ.get("LANGCHAIN_API_KEY")


def get_langsmith_config(thread_id: str, run_id: Optional[str] = None, agent_name: str = "FinanceController") -> Dict[str, Any]:
    """
    Generate LangSmith run metadata and tags for execution tracing.
    """
    return {
        "tags": [
            f"thread:{thread_id}",
            f"agent:{agent_name}",
            f"env:{os.environ.get('ENVIRONMENT', 'development')}"
        ],
        "metadata": {
            "thread_id": thread_id,
            "run_id": run_id,
            "agent_name": agent_name,
            "project": LANGSMITH_PROJECT
        }
    }


def is_tracing_active() -> bool:
    """Check if LangSmith tracing is currently enabled with an API key."""
    return bool(LANGSMITH_TRACING and LANGSMITH_API_KEY)
