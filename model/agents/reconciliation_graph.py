"""
LangGraph Reconciliation Agent.
Re-exports from model.graph.reconciliation_graph for backward compatibility.

The canonical implementation is in model/graph/reconciliation_graph.py.
"""

# Re-export everything from the canonical location
from ..graph.reconciliation_graph import (
    reconciliation_graph,
    build_reconciliation_graph,
    analyze_request_node,
    load_documents_node,
    normalize_records_node,
    generate_candidates_node,
    match_records_node,
    verify_matches_node,
    create_exceptions_node,
    calculate_metrics_node,
)

# Also re-export score_record_pair for backward compatibility
from ..reconciliation.engine import score_record_pair
