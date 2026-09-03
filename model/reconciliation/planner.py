"""
Role-Aware Reconciliation Planner.
Analyzes classified documents and their schemas to construct an explicit ReconciliationPlan:
1. Identifies the primary Source ↔ Counterpart document pair.
2. Identifies enrichment / adjustment documents (FEES, REFUNDS, CHARGEBACKS, TAXES).
3. Establishes the authoritative Source Population Denominator (never the sum of all uploaded rows).
4. Evaluates cross-document value overlap between candidate identifier columns.
5. Emits an explicit plan contract before execution.
"""

from typing import Dict, List, Any, Optional, Tuple, Set
import pandas as pd
from pydantic import BaseModel, Field

from .role_classifier import DocumentRole, DocumentRoleClassification
from .schema_mapper import SchemaMappingResult, DocumentSchema, normalize_canonical_transaction_id


class EnrichmentPlanItem(BaseModel):
    document_id: str
    filename: str
    role: DocumentRole
    adjustment_type: str  # "FEE_ADJUSTMENT", "TAX_VERIFICATION", "REFUND_REVERSAL", "DISPUTE_HOLD"
    record_count: int


class ReconciliationPlan(BaseModel):
    """Explicit, role-aware plan governing deterministic reconciliation."""
    relationship: str  # e.g. "TRANSACTION_SETTLEMENT", "LEDGER_BANK", "INVOICE_PAYOUT"
    source_doc_id: str
    source_filename: str
    source_role: DocumentRole
    source_population_count: int  # THE AUTHORITATIVE RECONCILIATION DENOMINATOR!

    counterpart_doc_id: Optional[str] = None
    counterpart_doc_ids: List[str] = Field(default_factory=list)
    counterpart_filename: Optional[str] = None
    counterpart_role: Optional[DocumentRole] = None
    counterpart_population_count: int = 0

    enrichment_docs: List[EnrichmentPlanItem] = Field(default_factory=list)
    unknown_docs: List[str] = Field(default_factory=list)

    primary_matching_key: Dict[str, Any] = Field(default_factory=dict)
    fallback_matching_keys: List[str] = Field(default_factory=list)

    amount_tolerance: float = 0.05
    fee_tolerance: float = 2.50
    date_window_days: int = 3
    is_valid_pair: bool = True
    plan_explanation: str = ""


# Priority rankings for selecting the primary source role
PRIMARY_SOURCE_ROLES = [
    DocumentRole.TRANSACTION,
    DocumentRole.LEDGER,
    DocumentRole.INVOICE,
]

# Priority rankings for selecting the primary counterpart role
PRIMARY_COUNTERPART_ROLES = [
    DocumentRole.SETTLEMENT,
    DocumentRole.BANK_STATEMENT,
    DocumentRole.PAYOUT,
]

# Secondary enrichment roles (must never contaminate the primary denominator)
ENRICHMENT_ROLES = {
    DocumentRole.FEE: "FEE_ADJUSTMENT",
    DocumentRole.TAX: "TAX_VERIFICATION",
    DocumentRole.REFUND: "REFUND_REVERSAL",
    DocumentRole.CHARGEBACK: "DISPUTE_HOLD",
}


def _compute_column_overlap(
    series_a: pd.Series, series_b: pd.Series
) -> Tuple[int, float]:
    """Calculate exact intersection count and overlap ratio between two series."""
    vals_a = {
        normalize_canonical_transaction_id(v)
        for v in series_a.dropna()
        if str(v).strip() and str(v).lower() not in ["nan", "none", "null", ""]
    }
    vals_b = {
        normalize_canonical_transaction_id(v)
        for v in series_b.dropna()
        if str(v).strip() and str(v).lower() not in ["nan", "none", "null", ""]
    }

    if not vals_a or not vals_b:
        return 0, 0.0

    overlap = len(vals_a & vals_b)
    denom = min(len(vals_a), len(vals_b))
    ratio = overlap / max(denom, 1)
    return overlap, ratio


class ReconciliationPlanner:
    """Builds an explicit, role-aware plan from classified documents and schemas."""

    def create_plan(
        self,
        document_tables: List[Tuple[pd.DataFrame, str, str, str]],  # (df, doc_id, filename, source_label)
        classifications: Dict[str, DocumentRoleClassification],
        schemas: Dict[str, DocumentSchema],
        amount_tolerance: float = 0.05,
        fee_tolerance: float = 2.50,
        date_window_days: int = 3,
    ) -> ReconciliationPlan:
        """
        Evaluate uploaded documents, partition primary counterparts from enrichment files,
        and construct the authoritative reconciliation plan.
        """
        df_map = {doc_id: df for df, doc_id, _, _ in document_tables}
        fname_map = {doc_id: filename for _, doc_id, filename, _ in document_tables}

        # 1. Partition documents by role
        source_candidates: List[str] = []
        counterpart_candidates: List[str] = []
        enrichment_items: List[EnrichmentPlanItem] = []
        unknown_docs: List[str] = []

        for doc_id, cls in classifications.items():
            role = cls.document_role
            df = df_map.get(doc_id, pd.DataFrame())
            fname = fname_map.get(doc_id, doc_id)

            if role in ENRICHMENT_ROLES:
                enrichment_items.append(EnrichmentPlanItem(
                    document_id=doc_id,
                    filename=fname,
                    role=role,
                    adjustment_type=ENRICHMENT_ROLES[role],
                    record_count=len(df),
                ))
            elif role in PRIMARY_SOURCE_ROLES:
                source_candidates.append(doc_id)
            elif role in PRIMARY_COUNTERPART_ROLES:
                counterpart_candidates.append(doc_id)
            elif role == DocumentRole.UNKNOWN:
                unknown_docs.append(doc_id)
            else:
                # Fallback to general candidate
                source_candidates.append(doc_id)

        # 2. Select Primary Source and Counterpart
        # Case A: Both natural source and counterpart exist
        source_doc_id: Optional[str] = None
        counterpart_doc_ids: List[str] = []

        if source_candidates and counterpart_candidates:
            source_doc_id = source_candidates[0]
            counterpart_doc_ids = counterpart_candidates
            # Multiple primary source documents cannot all be the authoritative
            # denominator in a single pass. Surface the extras rather than
            # silently dropping them.
            for extra_id in source_candidates[1:]:
                unknown_docs.append(extra_id)
        elif len(document_tables) >= 2:
            # Fallback: Pick top two documents by record count / role ranking
            non_enrichment = [t[1] for t in document_tables if t[1] not in [e.document_id for e in enrichment_items]]
            if len(non_enrichment) >= 2:
                source_doc_id = non_enrichment[0]
                counterpart_doc_ids = non_enrichment[1:]
            else:
                source_doc_id = document_tables[0][1]
                counterpart_doc_ids = [t[1] for t in document_tables[1:]]
        elif len(document_tables) == 1:
            source_doc_id = document_tables[0][1]
            counterpart_doc_ids = []
        else:
            return ReconciliationPlan(
                relationship="EMPTY",
                source_doc_id="none",
                source_filename="none",
                source_role=DocumentRole.UNKNOWN,
                source_population_count=0,
                is_valid_pair=False,
                plan_explanation="No documents uploaded for reconciliation planning.",
            )

        counterpart_doc_id = counterpart_doc_ids[0] if counterpart_doc_ids else None

        source_df = df_map[source_doc_id]
        source_cls = classifications.get(source_doc_id)
        source_role = source_cls.document_role if source_cls else DocumentRole.TRANSACTION
        source_fname = fname_map.get(source_doc_id, source_doc_id)
        source_pop = len(source_df)

        if not counterpart_doc_id or counterpart_doc_id not in df_map:
            return ReconciliationPlan(
                relationship="SINGLE_DOCUMENT",
                source_doc_id=source_doc_id,
                source_filename=source_fname,
                source_role=source_role,
                source_population_count=source_pop,
                counterpart_doc_id=None,
                counterpart_doc_ids=[],
                counterpart_filename=None,
                counterpart_role=None,
                counterpart_population_count=0,
                enrichment_docs=enrichment_items,
                unknown_docs=unknown_docs,
                is_valid_pair=False,
                plan_explanation=(
                    f"Only one primary document '{source_fname}' ({source_pop} records) available. "
                    "Reconciliation requires at least two counterpart documents."
                ),
            )

        counterpart_df = df_map[counterpart_doc_id]
        counterpart_cls = classifications.get(counterpart_doc_id)
        counterpart_role = counterpart_cls.document_role if counterpart_cls else DocumentRole.SETTLEMENT
        counterpart_fname = ", ".join(fname_map.get(cid, cid) for cid in counterpart_doc_ids)
        counterpart_pop = sum(len(df_map[cid]) for cid in counterpart_doc_ids if cid in df_map)

        # 3. Cross-Document Identifier Overlap Analysis
        # Determine the shared canonical transaction key with highest mutual overlap
        schema_a = schemas.get(source_doc_id)
        schema_b = schemas.get(counterpart_doc_id)

        candidates_a = []
        candidates_b = []
        if schema_a:
            for field in ["transaction_id", "reference_id"]:
                if field in schema_a.mapped_columns:
                    candidates_a.append((field, schema_a.mapped_columns[field]))
        if schema_b:
            for field in ["transaction_id", "reference_id"]:
                if field in schema_b.mapped_columns:
                    candidates_b.append((field, schema_b.mapped_columns[field]))

        best_key_info: Dict[str, Any] = {
            "source_column": None,
            "counterpart_column": None,
            "overlap_count": 0,
            "overlap_ratio": 0.0,
            "key_name": "canonical_transaction_id",
        }

        # Check mutual intersections strictly between identifier candidates
        highest_overlap = 0
        for sem_a, col_a in candidates_a:
            for sem_b, col_b in candidates_b:
                if col_a in source_df.columns and col_b in counterpart_df.columns:
                    overlap_cnt, overlap_ratio = _compute_column_overlap(source_df[col_a], counterpart_df[col_b])
                    if overlap_cnt > highest_overlap:
                        highest_overlap = overlap_cnt
                        best_key_info = {
                            "source_column": col_a,
                            "source_semantic": sem_a,
                            "counterpart_column": col_b,
                            "counterpart_semantic": sem_b,
                            "overlap_count": overlap_cnt,
                            "overlap_ratio": round(overlap_ratio, 4),
                            "key_name": "canonical_transaction_id",
                        }

        # Fallback if no overlap discovered between candidate columns
        if best_key_info["source_column"] is None:
            col_a = (
                schema_a.mapped_columns.get("transaction_id")
                or schema_a.mapped_columns.get("reference_id")
                or (source_df.columns[0] if len(source_df.columns) > 0 else "")
            )
            col_b = (
                schema_b.mapped_columns.get("transaction_id")
                or schema_b.mapped_columns.get("reference_id")
                or (counterpart_df.columns[0] if len(counterpart_df.columns) > 0 else "")
            )
            best_key_info = {
                "source_column": col_a,
                "counterpart_column": col_b,
                "overlap_count": 0,
                "overlap_ratio": 0.0,
                "key_name": "canonical_transaction_id",
            }

        rel_name = f"{source_role.value}_{counterpart_role.value}"
        explanation = (
            f"Reconciliation Plan: Source '{source_fname}' ({source_role.value}, {source_pop} records) "
            f"reconciled against Counterpart '{counterpart_fname}' ({counterpart_role.value}, {counterpart_pop} records). "
            f"Primary matching key: '{best_key_info['source_column']}' ↔ '{best_key_info['counterpart_column']}' "
            f"({best_key_info['overlap_count']} overlapping IDs). "
            f"Enrichment documents: {len(enrichment_items)}."
        )
        if unknown_docs:
            explanation += (
                f" {len(unknown_docs)} additional document(s) were not part of the primary "
                f"source↔counterpart scope and were not reconciled in this run."
            )

        return ReconciliationPlan(
            relationship=rel_name,
            source_doc_id=source_doc_id,
            source_filename=source_fname,
            source_role=source_role,
            source_population_count=source_pop,
            counterpart_doc_id=counterpart_doc_id,
            counterpart_doc_ids=counterpart_doc_ids,
            counterpart_filename=counterpart_fname,
            counterpart_role=counterpart_role,
            counterpart_population_count=counterpart_pop,
            enrichment_docs=enrichment_items,
            unknown_docs=unknown_docs,
            primary_matching_key=best_key_info,
            fallback_matching_keys=["reference_id", "amount+date", "entity+date"],
            amount_tolerance=amount_tolerance,
            fee_tolerance=fee_tolerance,
            date_window_days=date_window_days,
            is_valid_pair=True,
            plan_explanation=explanation,
        )


reconciliation_planner = ReconciliationPlanner()
