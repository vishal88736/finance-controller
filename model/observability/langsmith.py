"""
LangSmith Observability & Tracing Integration.

Provides genuinely functional tracing:
- Detects whether LangSmith is actually configured (env vars + API key).
- Produces proper `RunnableConfig` dicts consumed by LangGraph `.invoke(config=...)`,
  so nested runs (graph -> nodes -> tools) are traced with metadata/tags.
- Offers a tracing context manager (`traced_operation`) so non-LLM work like the
  REST reconciliation endpoint and QA tools create their own trace roots.
- Emits ONLY safe metadata (thread_id, run_id, agent, operation, document_ids,
  counts). NEVER document contents, secrets, ground truth, or user prompts.

Environment (standard LangSmith variables, both prefixes honored):
    LANGSMITH_TRACING_V2=true            (or LANGCHAIN_TRACING_V2)
    LANGSMITH_API_KEY=lsv2_pt_...        (or LANGCHAIN_API_KEY)
    LANGSMITH_PROJECT=ai-finance-controller  (or LANGCHAIN_PROJECT)
    LANGSMITH_ENDPOINT=https://api.smith.langchain.com (or LANGCHAIN_ENDPOINT)
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Environment resolution (LANGSMITH_* takes priority, LANGCHAIN_* fallback)
# ---------------------------------------------------------------------------


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    for prefix in ("LANGSMITH", "LANGCHAIN"):
        val = os.environ.get(f"{prefix}_{name}")
        if val:
            return val
    return default


def _env_bool(name: str, default: bool = False) -> bool:
    val = _env(name)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


TRACING_ENABLED_ENV = _env_bool("TRACING_V2", default=False) or _env_bool("TRACING", default=False)
API_KEY = _env("API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
PROJECT_NAME = _env("PROJECT") or "ai-finance-controller"
ENDPOINT = _env("ENDPOINT") or "https://api.smith.langchain.com"

# Safe identifiers allowed in trace metadata
_SAFE_META_KEYS = {"thread_id", "run_id", "agent", "operation", "document_ids", "env", "source"}


def is_tracing_active() -> bool:
    """
    True only when tracing is genuinely enabled:
    env flag on AND a usable API key present.
    """
    return bool(TRACING_ENABLED_ENV and API_KEY)


def _clone_client_if_available():
    """Create a fresh langsmith client lazily (test-safe import)."""
    try:
        from langsmith import Client

        return Client(api_key=API_KEY, api_url=ENDPOINT)
    except Exception:
        return None


def get_langsmith_config(
    thread_id: str,
    run_id: Optional[str] = None,
    agent_name: str = "FinanceController",
    operation: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build a LangGraph `RunnableConfig` for tracing.

    If tracing is active, returns config with run_name, tags and metadata that
    LangGraph propagates to all child runs (nodes, tools). If tracing is not
    configured, the config still carries the metadata (harmless) but enables no
    callbacks — we never claim tracing when it is off.
    """
    metadata: Dict[str, Any] = {
        "thread_id": thread_id,
        "agent": agent_name,
    }
    if run_id:
        metadata["run_id"] = run_id
    if operation:
        metadata["operation"] = operation
    if document_ids:
        metadata["document_ids"] = list(document_ids)[:50]  # ids only, never contents
    metadata["env"] = os.environ.get("ENVIRONMENT", "development")

    config: Dict[str, Any] = {"metadata": metadata}

    if is_tracing_active():
        config["run_name"] = f"{agent_name}"
        config["tags"] = [f"thread:{thread_id}", f"agent:{agent_name}"]
        if run_id:
            config["tags"].append(f"run:{run_id}")

    return config


@contextmanager
def traced_operation(
    name: str,
    thread_id: Optional[str] = None,
    run_id: Optional[str] = None,
    operation: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
):
    """
    Trace a non-graph operation (REST endpoint, tool execution, LLM call) as a
    LangSmith root run when tracing is genuinely active; otherwise a no-op.

    Usage:
        with traced_operation("REST /reconcile", thread_id=tid, run_id=rid) as run:
            ... do work ...
            run.metadata.update({"document_ids": [...]})   # optional, safe fields only
    """
    if not is_tracing_active():
        yield None
        return

    try:
        from langsmith.run_helpers import tracing_context

        meta: Dict[str, Any] = {}
        if thread_id:
            meta["thread_id"] = thread_id
        if run_id:
            meta["run_id"] = run_id
        if operation:
            meta["operation"] = operation
        if document_ids:
            meta["document_ids"] = list(document_ids)[:50]

        with tracing_context(project_name=PROJECT_NAME, enabled=True) as _ctx:
            try:
                from langsmith import Client

                client = Client(api_key=API_KEY, api_url=ENDPOINT)
            except Exception:
                yield None
                return

            run = client.create_run(
                name=name,
                inputs={},
                run_type="chain",
                tags=([f"thread:{thread_id}"] if thread_id else []),
                extra={"metadata": {k: v for k, v in meta.items() if k in _SAFE_META_KEYS}},
            )
            try:
                yield run
                client.update_run(run.id, outputs={"status": "ok"})
            except Exception as e:
                client.update_run(
                    run.id,
                    outputs={"status": "error", "error_type": type(e).__name__},
                )
                raise
            finally:
                try:
                    client.flush()
                except Exception:
                    pass
    except ImportError:
        yield None
