"""
LangGraph Reconciliation Agent.
Re-exports from model.graph.reconciliation_graph for backward compatibility.

The canonical implementation is in model/graph/reconciliation_graph.py.
"""

from ..graph.reconciliation_graph import (
    reconciliation_graph,
    build_reconciliation_graph,
    analyze_request_node,
    load_all_documents_node,
    detect_schemas_and_map_columns_node,
    python_reconciliation_node,
    compile_results_and_diagnostics_node,
    calculate_metrics_node,
)

# Backward-compatibility aliases
load_documents_node = load_all_documents_node
normalize_records_node = detect_schemas_and_map_columns_node
generate_candidates_node = detect_schemas_and_map_columns_node
match_records_node = python_reconciliation_node
verify_matches_node = compile_results_and_diagnostics_node
create_exceptions_node = compile_results_and_diagnostics_node

# Also re-export score_record_pair for backward compatibility
from ..reconciliation.engine import score_record_pair
