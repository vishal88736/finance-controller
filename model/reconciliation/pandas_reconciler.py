"""
Pure Deterministic Pandas + NumPy Financial Reconciliation Engine.
Processes ALL uploaded documents in a thread:
    1. Inspects schemas and maps semantically equivalent columns.
    2. Vectorized normalization of references, dates, amounts, and entities.
    3. Duplicate detection within files via pandas.
    4. Multi-pass matching using pandas merges and NumPy comparisons:
       - Pass 1: Exact Reference Match (100% confidence)
       - Pass 2: Fee Schedule / Tolerance Variance Match
       - Pass 3: Amount + Date Window Match (±3 business days)
       - Pass 4: Entity Similarity + Fuzzy Reference Cluster Match
    5. Exception classification (Normal vs Material) with failure diagnostics.
    6. Complete document and row provenance tracking for every record.
"""

import math
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Set

import numpy as np
import pandas as pd

from .schema_mapper import (
    schema_mapper,
    SchemaMappingResult,
    DocumentSchema,
    normalize_canonical_transaction_id,
)
from .role_classifier import (
    role_classifier,
    DocumentRole,
    DocumentRoleClassification,
)
from .planner import (
    reconciliation_planner,
    ReconciliationPlan,
    EnrichmentPlanItem,
)
from ..verification.normalizers import (
    normalize_amount,
    normalize_date,
    normalize_currency,
    normalize_entity_name,
    normalize_transaction_id,
    _is_nan,
)


def _round_dec(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return default
    try:
        return float(val)
    except Exception:
        return default


def clean_for_json(obj: Any) -> Any:
    """Recursively converts NaN and Infinite floats to None for valid JSON serialization."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(clean_for_json(v) for v in obj)
    return obj


class PandasReconciliationEngine:
    """
    Production deterministic reconciliation engine built entirely on pandas and NumPy.
    All financial comparisons, merges, joins, and aggregations are computed deterministically.
    """

    def __init__(
        self,
        amount_tolerance: float = 0.05,
        fee_tolerance: float = 2.50,
        date_window_days: int = 3,
        confidence_threshold: float = 75.0,
    ):
        self.amount_tolerance = amount_tolerance
        self.fee_tolerance = fee_tolerance
        self.date_window_days = date_window_days
        self.confidence_threshold = confidence_threshold

    def reconcile_documents(
        self,
        document_tables: List[Tuple[pd.DataFrame, str, str, str]],  # (df, doc_id, filename, source_label)
        run_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        plan: Optional[ReconciliationPlan] = None,
    ) -> Dict[str, Any]:
        """
        Main deterministic reconciliation pipeline over ALL uploaded documents.
        Executes role-aware planning, cross-document identifier overlap matching,
        and authoritative source-population denominator reconciliation.
        """
        start_time = time.perf_counter()
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        thread_id = thread_id or "thread_default"

        if not document_tables:
            return self._empty_result(run_id, thread_id, "No documents provided for reconciliation.")

        # ── STAGE 1: Schema Detection & Semantic Column Mapping ──
        schema_result = schema_mapper.inspect_and_map_all(document_tables)
        if not schema_result.all_valid:
            diagnostics_msg = "; ".join(schema_result.diagnostics)
            if schema_result.summary["valid_documents"] == 0:
                return self._failed_schema_result(run_id, thread_id, schema_result, diagnostics_msg)

        # ── STAGE 2: Document Role Classification ──
        role_classifications = role_classifier.classify_all(document_tables)

        # ── STAGE 3: Role-Aware Reconciliation Plan ──
        if plan is None:
            plan = reconciliation_planner.create_plan(
                document_tables=document_tables,
                classifications=role_classifications,
                schemas=schema_result.schemas,
                amount_tolerance=self.amount_tolerance,
                fee_tolerance=self.fee_tolerance,
                date_window_days=self.date_window_days,
            )

        # Document metadata summary for transparency
        doc_meta_list: List[Dict[str, Any]] = []
        for df_raw, doc_id, filename, source_label in document_tables:
            schema = schema_result.schemas.get(doc_id)
            cls = role_classifications.get(doc_id)
            doc_meta_list.append({
                "document_id": doc_id,
                "filename": filename,
                "source_label": source_label,
                "row_count": len(df_raw),
                "document_role": cls.document_role.value if cls else "UNKNOWN",
                "role_confidence": cls.confidence if cls else 0.0,
                "role_reason": cls.reason if cls else "",
                "detected_schema": schema.raw_columns if schema else [],
                "mapped_columns": schema.mapped_columns if schema else {},
                "unmapped_columns": schema.unmapped_columns if schema else [],
            })

        total_ingested_records = sum(len(t[0]) for t in document_tables)
        if total_ingested_records == 0:
            return self._empty_result(run_id, thread_id, "Uploaded documents contain zero data rows.", schema_result)

        # ── Handle Single Document or Invalid Plan Pair Gracefully ──
        if not plan.is_valid_pair or not plan.counterpart_doc_id:
            source_tuple = next((t for t in document_tables if t[1] == plan.source_doc_id), document_tables[0])
            source_schema = schema_result.schemas.get(source_tuple[1])
            source_df = self._normalize_dataframe(source_tuple[0], source_schema, role=plan.source_role)
            unmatched_exceptions = self._generate_exceptions(
                source_df, pd.DataFrame(columns=source_df.columns), set(), set(), []
            )
            elapsed_sec = time.perf_counter() - start_time
            return {
                "run_id": run_id,
                "thread_id": thread_id,
                "status": "COMPLETED",
                "processing_engine": "Deterministic Python (pandas + NumPy)",
                "reconciliation_plan": plan.model_dump(),
                "role_classifications": {doc_id: c.model_dump() for doc_id, c in role_classifications.items()},
                "documents_processed": doc_meta_list,
                "detected_schemas": {m["document_id"]: m["detected_schema"] for m in doc_meta_list},
                "mapped_columns": {m["document_id"]: m["mapped_columns"] for m in doc_meta_list},
                "records_processed": total_ingested_records,
                "source_population": len(source_df),
                "counterpart_population": 0,
                "total_ingested_records": total_ingested_records,
                "candidate_pairs_evaluated": 0,
                "matched_records_count": 0,
                "unmatched_records_count": len(unmatched_exceptions),
                "duplicates_count": 0,
                "match_rate": 0.0,
                "exact_matches_count": 0,
                "fuzzy_matches_count": 0,
                "normal_discrepancies_count": 0,
                "material_discrepancies_count": len(unmatched_exceptions),
                "mismatch_reasons": {"missing_counterpart": len(source_df)},
                "totals_and_statistics": {
                    "total_primary_amount": round(_safe_float(source_df["amount"].sum()), 2),
                    "total_counterparty_amount": 0.0,
                    "matched_volume": 0.0,
                    "total_discrepancy_amount": round(_safe_float(source_df["amount"].sum()), 2),
                    "processing_time_sec": round(elapsed_sec, 3),
                    "throughput_records_sec": round(len(source_df) / elapsed_sec if elapsed_sec > 0 else 0.0, 1),
                },
                "diagnostics": {
                    "candidate_pairs_evaluated": 0,
                    "rejection_breakdown": {"missing_counterpart": len(source_df)},
                    "zero_match_diagnostics": plan.plan_explanation,
                },
                "matches": [],
                "exceptions": unmatched_exceptions,
            }

        # ── STAGE 4: Source and Counterpart Normalization with Plan Keys ──
        source_tuple = next((t for t in document_tables if t[1] == plan.source_doc_id), document_tables[0])
        source_schema = schema_result.schemas.get(source_tuple[1])
        source_key_col = plan.primary_matching_key.get("source_column")

        primary_df = self._normalize_dataframe(
            source_tuple[0], source_schema, role=plan.source_role, primary_key_col=source_key_col
        )

        counterpart_key_col = plan.primary_matching_key.get("counterpart_column")
        c_dfs = []
        for cid in plan.counterpart_doc_ids:
            c_tuple = next((t for t in document_tables if t[1] == cid), None)
            if c_tuple is not None:
                c_schema = schema_result.schemas.get(cid)
                c_cls = role_classifications.get(cid)
                c_role = c_cls.document_role if c_cls else plan.counterpart_role
                c_df = self._normalize_dataframe(
                    c_tuple[0], c_schema, role=c_role, primary_key_col=counterpart_key_col
                )
                c_dfs.append(c_df)

        if not c_dfs:
            secondary_df = pd.DataFrame(columns=primary_df.columns)
        else:
            secondary_df = pd.concat(c_dfs, ignore_index=True)

        # ── STAGE 5: Intra-Document Duplicate Detection ──
        dups_a = self._detect_duplicates_in_df(primary_df)
        dups_b = self._detect_duplicates_in_df(secondary_df)
        duplicate_records_list = dups_a + dups_b

        # ── STAGE 6: Deterministic Matching Pipeline (Pandas + NumPy) ──
        matches, matched_ids_a, matched_ids_b, pass_exceptions, diagnostics = self._run_matching_passes(
            primary_df, secondary_df
        )

        # ── STAGE 7: Exception Generation & Discrepancy Classification ──
        unmatched_exceptions = self._generate_exceptions(
            primary_df, secondary_df, matched_ids_a, matched_ids_b, duplicate_records_list
        )
        exceptions = pass_exceptions + unmatched_exceptions

        # ── STAGE 8: Enrichment Adjustments (Fees, Taxes, Refunds) ──
        enrichment_adjustments: List[Dict[str, Any]] = []
        for enrich_item in plan.enrichment_docs:
            e_table = next((t for t in document_tables if t[1] == enrich_item.document_id), None)
            if e_table is not None:
                e_df = e_table[0]
                enrichment_adjustments.append({
                    "document_id": enrich_item.document_id,
                    "filename": enrich_item.filename,
                    "role": enrich_item.role.value,
                    "adjustment_type": enrich_item.adjustment_type,
                    "records_count": len(e_df),
                })

        # ── STAGE 9: Authoritative Metrics (Source Population Denominator) ──
        elapsed_sec = time.perf_counter() - start_time
        source_pop = len(primary_df)
        counterpart_pop = len(secondary_df)
        throughput = (source_pop + counterpart_pop) / elapsed_sec if elapsed_sec > 0 else 0.0

        total_amt_a = _safe_float(primary_df["amount"].sum())
        total_amt_b = _safe_float(secondary_df["amount"].sum())
        matched_amt_a = sum(m["amount_a"] for m in matches)
        discrepancy_amt = sum(m["amount_diff"] for m in matches) + sum(e["amount_discrepancy"] for e in exceptions)

        exact_matches_count = sum(1 for m in matches if m["match_category"] == "EXACT_MATCH")
        fuzzy_matches_count = sum(1 for m in matches if m["match_category"] != "EXACT_MATCH")
        matched_records_count = len(matches)
        exceptions_count = len(exceptions)

        # THE CRITICAL METRIC RULE:
        # Denominator is strictly source_pop (the primary source population being reconciled)!
        match_rate = (matched_records_count / source_pop * 100.0) if source_pop > 0 else 0.0

        result = {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "COMPLETED",
            "processing_engine": "Deterministic Python (pandas + NumPy)",
            "reconciliation_plan": plan.model_dump(),
            "role_classifications": {doc_id: c.model_dump() for doc_id, c in role_classifications.items()},
            "documents_processed": doc_meta_list,
            "detected_schemas": {m["document_id"]: m["detected_schema"] for m in doc_meta_list},
            "mapped_columns": {m["document_id"]: m["mapped_columns"] for m in doc_meta_list},
            "records_processed": total_ingested_records,
            "source_population": source_pop,
            "counterpart_population": counterpart_pop,
            "total_ingested_records": total_ingested_records,
            "participating_records": source_pop + counterpart_pop,
            "candidate_pairs_evaluated": diagnostics["candidate_pairs_evaluated"],
            "matched_records_count": matched_records_count,
            "unmatched_records_count": exceptions_count,
            "duplicates_count": len(duplicate_records_list),
            "match_rate": round(match_rate, 1),
            "exact_matches_count": exact_matches_count,
            "fuzzy_matches_count": fuzzy_matches_count,
            "normal_discrepancies_count": sum(1 for m in matches if m["discrepancy_level"] == "NORMAL"),
            "material_discrepancies_count": sum(1 for e in exceptions if e["discrepancy_level"] == "MATERIAL"),
            "mismatch_reasons": diagnostics["rejection_breakdown"],
            "enrichment_adjustments": enrichment_adjustments,
            "totals_and_statistics": {
                "total_primary_amount": round(total_amt_a, 2),
                "total_counterparty_amount": round(total_amt_b, 2),
                "matched_volume": round(matched_amt_a, 2),
                "total_discrepancy_amount": round(discrepancy_amt, 2),
                "processing_time_sec": round(elapsed_sec, 3),
                "throughput_records_sec": round(throughput, 1),
            },
            "diagnostics": diagnostics,
            "matches": matches,
            "exceptions": exceptions,
        }

        return clean_for_json(result)

    # ─────────────────────────────────────────────────────────────
    # NORMALIZATION HELPER
    # ─────────────────────────────────────────────────────────────

    def _normalize_dataframe(
        self,
        df_raw: pd.DataFrame,
        schema: DocumentSchema,
        role: Optional[DocumentRole] = None,
        primary_key_col: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Normalize raw DataFrame into standard fields while keeping provenance.
        """
        n_rows = len(df_raw)
        df = pd.DataFrame(index=np.arange(n_rows))
        mapped = schema.mapped_columns

        # Provenance columns
        df["_doc_id"] = [schema.document_id] * n_rows
        df["_doc_name"] = [schema.filename] * n_rows
        df["_source_label"] = [schema.source_label] * n_rows
        df["_row_idx"] = np.arange(n_rows)

        # Raw data dict per row with NaN sanitized to None
        clean_raw_records = [clean_for_json(r) for r in df_raw.to_dict(orient="records")]
        df["_raw_data"] = clean_raw_records

        # Document role for provenance
        if role is not None:
            df["_doc_role"] = [role.value] * n_rows
        else:
            lbl_lower = (schema.source_label + " " + schema.filename).lower()
            if "settle" in lbl_lower:
                doc_role = "SETTLEMENT"
            elif "bank" in lbl_lower:
                doc_role = "BANK_STATEMENT"
            elif "invoice" in lbl_lower or "bill" in lbl_lower:
                doc_role = "INVOICE"
            elif "payout" in lbl_lower:
                doc_role = "PAYOUT"
            else:
                doc_role = "TRANSACTION"
            df["_doc_role"] = [doc_role] * n_rows

        # 1. Transaction ID & Provenance Record Identifier
        if "transaction_id" in mapped and mapped["transaction_id"] in df_raw.columns:
            df["transaction_id"] = df_raw[mapped["transaction_id"]].astype(str).str.strip()
        elif "reference_id" in mapped and mapped["reference_id"] in df_raw.columns:
            df["transaction_id"] = df_raw[mapped["reference_id"]].astype(str).str.strip()
        elif primary_key_col and primary_key_col in df_raw.columns:
            df["transaction_id"] = df_raw[primary_key_col].astype(str).str.strip()
        else:
            df["transaction_id"] = [f"{schema.source_label}_{i}" for i in range(n_rows)]

        # 2. Canonical Business Matching Identity
        if primary_key_col and primary_key_col in df_raw.columns:
            raw_canon = df_raw[primary_key_col].astype(str).str.strip()
            df["canonical_transaction_id"] = [normalize_canonical_transaction_id(r) for r in raw_canon]
        else:
            df["canonical_transaction_id"] = [normalize_canonical_transaction_id(r) for r in df["transaction_id"]]

        # 2. Member / Customer / Account ID (grouping/context ONLY - NEVER a reconciliation match key!)
        if "member_id" in mapped and mapped["member_id"] in df_raw.columns:
            df["member_id"] = df_raw[mapped["member_id"]].astype(str).str.strip()
        elif "member_id" in df_raw.columns:
            df["member_id"] = df_raw["member_id"].astype(str).str.strip()
        else:
            df["member_id"] = None

        # 3. Reference ID & Clean Reference Token
        if "reference_id" in mapped and mapped["reference_id"] in df_raw.columns:
            raw_ref = df_raw[mapped["reference_id"]].astype(str).str.strip()
        elif "transaction_id" in mapped and mapped["transaction_id"] in df_raw.columns:
            raw_ref = df_raw[mapped["transaction_id"]].astype(str).str.strip()
        else:
            raw_ref = df["transaction_id"]

        df["raw_reference_id"] = raw_ref
        df["clean_reference_id"] = [normalize_transaction_id(r) for r in raw_ref]

        # 4. Amount
        if "amount" in mapped and mapped["amount"] in df_raw.columns:
            df["amount"] = [float(normalize_amount(v)) for v in df_raw[mapped["amount"]]]
        elif "taxable_amount" in df_raw.columns:
            df["amount"] = [float(normalize_amount(v)) for v in df_raw["taxable_amount"]]
        elif "total_amount" in df_raw.columns:
            df["amount"] = [float(normalize_amount(v)) for v in df_raw["total_amount"]]
        else:
            debit_col = mapped.get("debit_amount") or next((c for c in df_raw.columns if "debit" in c.lower()), None)
            credit_col = mapped.get("credit_amount") or next((c for c in df_raw.columns if "credit" in c.lower()), None)
            if debit_col and debit_col in df_raw.columns:
                df["amount"] = [float(normalize_amount(v)) for v in df_raw[debit_col]]
            elif credit_col and credit_col in df_raw.columns:
                df["amount"] = [float(normalize_amount(v)) for v in df_raw[credit_col]]
            else:
                df["amount"] = 0.0

        # Fee, Refund, Chargeback Netting
        if "fee_amount" in mapped and mapped["fee_amount"] in df_raw.columns:
            df["fee_amount"] = [float(normalize_amount(v)) for v in df_raw[mapped["fee_amount"]]]
        else:
            df["fee_amount"] = 0.0

        if "refund_amount" in mapped and mapped["refund_amount"] in df_raw.columns:
            df["refund_amount"] = [float(normalize_amount(v)) for v in df_raw[mapped["refund_amount"]]]
        else:
            df["refund_amount"] = 0.0

        if "chargeback_amount" in mapped and mapped["chargeback_amount"] in df_raw.columns:
            df["chargeback_amount"] = [float(normalize_amount(v)) for v in df_raw[mapped["chargeback_amount"]]]
        else:
            df["chargeback_amount"] = 0.0

        # Calculate Net Amount (Assuming 'amount' is Gross if fees exist)
        # In financial systems, if fees/refunds are present, the settled amount is net.
        df["net_amount"] = df["amount"] - df["fee_amount"] - df["refund_amount"] - df["chargeback_amount"]

        # 4. Date & ISO Date
        if "date" in mapped and mapped["date"] in df_raw.columns:
            df["iso_date"] = [normalize_date(v) for v in df_raw[mapped["date"]]]
            # Convert to pandas datetime for vectorized day difference
            df["dt_date"] = pd.to_datetime(df["iso_date"], errors="coerce")
        else:
            df["iso_date"] = "1970-01-01"
            df["dt_date"] = pd.to_datetime("1970-01-01")

        # 5. Entity
        if "entity" in mapped and mapped["entity"] in df_raw.columns:
            df["raw_entity"] = df_raw[mapped["entity"]].astype(str).str.strip()
            df["clean_entity"] = [normalize_entity_name(e) for e in df["raw_entity"]]
        else:
            df["raw_entity"] = "Unknown"
            df["clean_entity"] = "unknown"

        # 6. Description
        if "description" in mapped and mapped["description"] in df_raw.columns:
            df["raw_description"] = df_raw[mapped["description"]].astype(str).str.strip()
        else:
            df["raw_description"] = ""

        # 7. Currency
        if "currency" in mapped and mapped["currency"] in df_raw.columns:
            df["currency"] = [normalize_currency(c) for c in df_raw[mapped["currency"]]]
        else:
            df["currency"] = "USD"

        return df

    # ─────────────────────────────────────────────────────────────
    # DUPLICATE DETECTION (PANDAS)
    # ─────────────────────────────────────────────────────────────

    def _detect_duplicates_in_df(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Detect intra-file duplicate transactions using pandas grouping.
        """
        if len(df) == 0:
            return []

        duplicates: List[Dict[str, Any]] = []

        # 1. Duplicate canonical_transaction_id (when available and non-empty)
        if "canonical_transaction_id" in df.columns:
            valid_canon = df[df["canonical_transaction_id"].str.len() > 0]
            if len(valid_canon) > 0:
                dup_canon_mask = valid_canon.duplicated(subset=["canonical_transaction_id"], keep=False)
                dup_canon_df = valid_canon[dup_canon_mask]
                if len(dup_canon_df) > 0:
                    for canon_id, group in dup_canon_df.groupby("canonical_transaction_id"):
                        records_in_group = [
                            {
                                "record_id": row["transaction_id"],
                                "canonical_transaction_id": canon_id,
                                "document_id": row["_doc_id"],
                                "filename": row["_doc_name"],
                                "row_index": int(row["_row_idx"]),
                                "amount": float(row["amount"]),
                                "date": row["iso_date"],
                            }
                            for _, row in group.iterrows()
                        ]
                        duplicates.append({
                            "duplicate_group_id": f"DUP-CANON-{canon_id}",
                            "reference_id": canon_id,
                            "amount": float(group["amount"].iloc[0]),
                            "count": len(group),
                            "records": records_in_group,
                            "explanation": f"Duplicate transaction: {len(group)} records share canonical ID '{canon_id}'.",
                        })

        # 2. Duplicate clean reference IDs with same amount
        subset_cols = ["clean_reference_id", "amount"]
        dup_mask = df.duplicated(subset=subset_cols, keep=False)
        dup_df = df[dup_mask]

        if len(dup_df) > 0:
            grouped = dup_df.groupby(subset_cols)
            for (clean_ref, amt), group in grouped:
                if clean_ref and len(group) > 1:
                    records_in_group = [
                        {
                            "record_id": row["transaction_id"],
                            "canonical_transaction_id": row.get("canonical_transaction_id", ""),
                            "document_id": row["_doc_id"],
                            "filename": row["_doc_name"],
                            "row_index": int(row["_row_idx"]),
                            "amount": float(row["amount"]),
                            "date": row["iso_date"],
                        }
                        for _, row in group.iterrows()
                    ]
                    duplicates.append({
                        "duplicate_group_id": f"DUP-{clean_ref}",
                        "reference_id": clean_ref,
                        "amount": float(amt),
                        "count": len(group),
                        "records": records_in_group,
                        "explanation": f"Duplicate transaction: {len(group)} records share reference '{clean_ref}' and amount ${amt:.2f}.",
                    })
        return duplicates

    # ─────────────────────────────────────────────────────────────
    # DETERMINISTIC MATCHING PASSES (PANDAS + NUMPY)
    # ─────────────────────────────────────────────────────────────

    def _run_matching_passes(
        self, df_a: pd.DataFrame, df_b: pd.DataFrame
    ) -> Tuple[List[Dict[str, Any]], Set[str], Set[str], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Execute deterministic matching pipeline:
        1. PRIMARY MATCHING: Exact join on canonical_transaction_id.
           - Row position/order MUST NOT matter.
           - member_id is grouping/context ONLY (never a match key).
           - Multiple transactions per member are independent reconciliation units.
           - Same ID + matching amount -> MATCHED (100% confidence, matching_strategy="EXACT_TRANSACTION_ID").
           - Same ID + fee tolerance delta -> TOLERANCE_MATCH (95% confidence, matching_strategy="EXACT_TRANSACTION_ID_FEE_DELTA").
           - Same ID + amount discrepancy -> AMOUNT_MISMATCH exception directly! Neither record is passed to fallback fuzzy matching.
           - Duplicate ID conflicts -> DUPLICATE_TRANSACTION / AMBIGUOUS_CANDIDATE_CONFLICT.
        2. FALLBACK MATCHING (Only when canonical_transaction_id is unavailable or missing):
           - Fallback 1: Exact Reference ID (clean_reference_id)
           - Fallback 2: Exact Amount + Compatible Date Window (±3 days)
           - Fallback 3: Entity + Amount + Date Window
           - Ambiguous candidates (>1 match) are flagged as AMBIGUOUS_CANDIDATE_CONFLICT (never arbitrary matches[0]).
        """
        matches: List[Dict[str, Any]] = []
        pass_exceptions: List[Dict[str, Any]] = []
        matched_a: Set[str] = set()
        matched_b: Set[str] = set()

        rejection_breakdown = {
            "amount_mismatch": 0,
            "date_mismatch": 0,
            "currency_mismatch": 0,
            "missing_counterpart": 0,
            "ambiguous_candidate_conflict": 0,
        }

        total_candidate_pairs = 0

        # Helper to construct clean match entry with full row provenance
        def _build_match(row: pd.Series, strat: str, cat: str, conf: float, diff_val: float, days_diff: int, rule_name: str) -> Dict[str, Any]:
            id_a = str(row["transaction_id_a"])
            id_b = str(row["transaction_id_b"])
            canon_id = str(row.get("canonical_transaction_id_a") or row.get("canonical_transaction_id") or id_a)
            return {
                "id": f"match_{uuid.uuid4().hex[:10]}",
                "record_id_a": id_a,
                "record_id_b": id_b,
                "canonical_transaction_id": canon_id,
                "transaction_id": id_a,
                "transaction_document": str(row["_doc_name_a"]),
                "transaction_row": int(row["_row_idx_a"]),
                "settlement_document": str(row["_doc_name_b"]),
                "settlement_row": int(row["_row_idx_b"]),
                "matching_strategy": strat,
                "match_score": conf,
                "source_a": str(row["_source_label_a"]),
                "source_b": str(row["_source_label_b"]),
                "amount_a": float(row["amount_a"]) if "amount_a" in row else float(row["amount"]),
                "amount_b": float(row["amount_b"]) if "amount_b" in row else float(row["amount"]),
                "amount_diff": diff_val,
                "date_a": str(row["iso_date_a"]),
                "date_b": str(row["iso_date_b"]),
                "days_diff": days_diff,
                "currency_a": str(row["currency_a"]),
                "currency_b": str(row["currency_b"]),
                "entity_a": "" if _is_nan(row.get("raw_entity_a")) else str(row.get("raw_entity_a") or ""),
                "entity_b": "" if _is_nan(row.get("raw_entity_b")) else str(row.get("raw_entity_b") or ""),
                "member_id_a": None if _is_nan(row.get("member_id_a")) else (row.get("member_id_a") or None),
                "member_id_b": None if _is_nan(row.get("member_id_b")) else (row.get("member_id_b") or None),
                "match_category": cat,
                "discrepancy_level": "NORMAL" if diff_val <= 1.0 else "MATERIAL",
                "confidence_score": conf,
                "match_rule": rule_name,
                "counterpart_document_id": str(row["_doc_id_b"]),
                "counterpart_row_index": int(row["_row_idx_b"]),
                "provenance_a": {
                    "document_id": str(row["_doc_id_a"]),
                    "filename": str(row["_doc_name_a"]),
                    "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                    "row_index": int(row["_row_idx_a"]),
                    "canonical_transaction_id": canon_id,
                    "member_id": row.get("member_id_a"),
                    "raw_data": row["_raw_data_a"],
                },
                "provenance_b": {
                    "document_id": str(row["_doc_id_b"]),
                    "filename": str(row["_doc_name_b"]),
                    "document_role": str(row.get("_doc_role_b", "SETTLEMENTS")),
                    "row_index": int(row["_row_idx_b"]),
                    "canonical_transaction_id": canon_id,
                    "member_id": row.get("member_id_b"),
                    "raw_data": row["_raw_data_b"],
                },
                "evidence": {
                    "record_id_a": id_a,
                    "record_id_b": id_b,
                    "canonical_transaction_id": canon_id,
                    "matching_strategy": strat,
                    "transaction_document": str(row["_doc_name_a"]),
                    "transaction_row": int(row["_row_idx_a"]),
                    "settlement_document": str(row["_doc_name_b"]),
                    "settlement_row": int(row["_row_idx_b"]),
                    "amount_a": float(row["amount_a"]) if "amount_a" in row else float(row["amount"]),
                    "amount_b": float(row["amount_b"]) if "amount_b" in row else float(row["amount"]),
                    "net_amount_a": float(row.get("net_amount_a", row.get("net_amount", 0.0))),
                    "net_amount_b": float(row.get("net_amount_b", row.get("net_amount", 0.0))),
                    "fee_amount_a": float(row.get("fee_amount_a", row.get("fee_amount", 0.0))),
                    "fee_amount_b": float(row.get("fee_amount_b", row.get("fee_amount", 0.0))),
                    "refund_amount_a": float(row.get("refund_amount_a", row.get("refund_amount", 0.0))),
                    "refund_amount_b": float(row.get("refund_amount_b", row.get("refund_amount", 0.0))),
                    "chargeback_amount_a": float(row.get("chargeback_amount_a", row.get("chargeback_amount", 0.0))),
                    "chargeback_amount_b": float(row.get("chargeback_amount_b", row.get("chargeback_amount", 0.0))),
                    "date_a": str(row["iso_date_a"]),
                    "date_b": str(row["iso_date_b"]),
                    "reference_a": str(row.get("raw_reference_id_a", id_a)),
                    "reference_b": str(row.get("raw_reference_id_b", id_b)),
                    "clean_reference": str(row.get("clean_reference_id", canon_id)),
                    "amount_difference": f"${diff_val:.2f}",
                    "date_lag_days": days_diff,
                },
            }

        # ── PASS 1: PRIMARY EXACT MATCH ON CANONICAL_TRANSACTION_ID ──
        # Canonical business identity join. Row position/order has zero effect on the merge.
        valid_id_a = df_a[df_a["canonical_transaction_id"].str.len() > 0] if "canonical_transaction_id" in df_a.columns else pd.DataFrame()
        valid_id_b = df_b[df_b["canonical_transaction_id"].str.len() > 0] if "canonical_transaction_id" in df_b.columns else pd.DataFrame()

        if len(valid_id_a) > 0 and len(valid_id_b) > 0:
            merged_primary = pd.merge(
                valid_id_a, valid_id_b,
                on="canonical_transaction_id",
                suffixes=("_a", "_b")
            )
            total_candidate_pairs += len(merged_primary)

            if len(merged_primary) > 0:
                dup_ids_a = set(valid_id_a[valid_id_a.duplicated(subset=["canonical_transaction_id"], keep=False)]["canonical_transaction_id"])
                dup_ids_b = set(valid_id_b[valid_id_b.duplicated(subset=["canonical_transaction_id"], keep=False)]["canonical_transaction_id"])
                all_dup_ids = dup_ids_a | dup_ids_b

                for _, row in merged_primary.iterrows():
                    canon_id = str(row["canonical_transaction_id"])
                    id_a = str(row["transaction_id_a"])
                    id_b = str(row["transaction_id_b"])

                    if id_a in matched_a or id_b in matched_b:
                        continue

                    # Currency Mismatch Check
                    if str(row["currency_a"]) != str(row["currency_b"]):
                        rejection_breakdown["currency_mismatch"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "canonical_transaction_id": canon_id,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "CURRENCY_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": 0.0,
                            "explanation": f"Currency mismatch: {row['currency_a']} vs {row['currency_b']}. Currency conversion required.",
                            "recommended_action": "Manually convert currencies or configure FX rates.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": canon_id,
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a,
                                "record_id_b": id_b,
                                "canonical_transaction_id": canon_id,
                                "currency_a": str(row["currency_a"]),
                                "currency_b": str(row["currency_b"]),
                                "amount_a": float(row["amount_a"]),
                                "amount_b": float(row["amount_b"]),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                        continue

                    # Duplicate conflict
                    if canon_id in all_dup_ids:
                        rejection_breakdown["ambiguous_candidate_conflict"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "canonical_transaction_id": canon_id,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "DUPLICATE_TRANSACTION",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": float(row["amount_a"]),
                            "explanation": f"Ambiguous transaction ID '{canon_id}': appears multiple times in source files.",
                            "recommended_action": "Investigate duplicate settlement batch.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": canon_id,
                                "member_id": row.get("member_id_a"),
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a,
                                "record_id_b": id_b,
                                "canonical_transaction_id": canon_id,
                                "matching_strategy": "EXACT_TRANSACTION_ID",
                                "transaction_document": str(row["_doc_name_a"]),
                                "transaction_row": int(row["_row_idx_a"]),
                                "settlement_document": str(row["_doc_name_b"]),
                                "settlement_row": int(row["_row_idx_b"]),
                                "amount_a": float(row["amount_a"]),
                                "amount_b": float(row["amount_b"]),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                        continue

                    d_a = row["dt_date_a"]
                    d_b = row["dt_date_b"]
                    days_diff = abs((d_a - d_b).days) if (pd.notna(d_a) and pd.notna(d_b)) else 0
                    
                    amt_a = float(row["amount_a"])
                    amt_b = float(row["amount_b"])
                    net_a = float(row.get("net_amount_a", amt_a))
                    net_b = float(row.get("net_amount_b", amt_b))
                    
                    diff_val = round(abs(amt_a - amt_b), 2)
                    net_diff_val = min(
                        round(abs(net_a - amt_b), 2),
                        round(abs(amt_a - net_b), 2),
                        round(abs(net_a - net_b), 2)
                    )
                    best_diff = diff_val if diff_val <= self.amount_tolerance else net_diff_val

                    if best_diff <= self.amount_tolerance:
                        strat = "EXACT_TRANSACTION_ID"
                        cat = "EXACT_MATCH" if (best_diff == 0.0 and days_diff == 0) else "TOLERANCE_MATCH"
                        conf = 100.0 if cat == "EXACT_MATCH" else 98.0
                        rule = "Pass 1: Primary Canonical Transaction ID Match"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    elif best_diff <= self.fee_tolerance:
                        strat = "EXACT_TRANSACTION_ID_FEE_DELTA"
                        cat = "TOLERANCE_MATCH"
                        conf = 95.0
                        rule = "Pass 1: Canonical Transaction ID Match with Fee Delta"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    else:
                        # Same transaction ID + amount difference -> AMOUNT_MISMATCH
                        # Do NOT automatically fuzzy-match a different transaction ID when an exact ID exists!
                        rejection_breakdown["amount_mismatch"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "canonical_transaction_id": canon_id,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "AMOUNT_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": diff_val,
                            "explanation": (
                                f"Amount mismatch on canonical transaction ID '{canon_id}': "
                                f"{row['_source_label_a']} reports ${float(row['amount_a']):,.2f} vs "
                                f"{row['_source_label_b']} ${float(row['amount_b']):,.2f} (delta: ${diff_val:,.2f})."
                            ),
                            "recommended_action": "Reconcile payment processing fee or adjust rounding.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": canon_id,
                                "member_id": row.get("member_id_a"),
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a,
                                "record_id_b": id_b,
                                "canonical_transaction_id": canon_id,
                                "matching_strategy": "EXACT_TRANSACTION_ID",
                                "transaction_document": str(row["_doc_name_a"]),
                                "transaction_row": int(row["_row_idx_a"]),
                                "settlement_document": str(row["_doc_name_b"]),
                                "settlement_row": int(row["_row_idx_b"]),
                                "amount_a": float(row["amount_a"]),
                                "amount_b": float(row["amount_b"]),
                                "date_a": str(row["iso_date_a"]),
                                "date_b": str(row["iso_date_b"]),
                                "counterpart_record_id": id_b,
                                "counterpart_amount": float(row["amount_b"]),
                                "counterpart_source": str(row["_source_label_b"]),
                                "amount_delta": diff_val,
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)

        # ── PASS 2: FALLBACK 1 - EXACT REFERENCE ID MATCH ──
        # Used ONLY when canonical_transaction_id is unavailable or unmatched
        unmatched_df_a = df_a[~df_a["transaction_id"].isin(matched_a)]
        unmatched_df_b = df_b[~df_b["transaction_id"].isin(matched_b)]

        cand_ref_a = unmatched_df_a[unmatched_df_a["clean_reference_id"].str.len() > 0]
        cand_ref_b = unmatched_df_b[unmatched_df_b["clean_reference_id"].str.len() > 0]

        if len(cand_ref_a) > 0 and len(cand_ref_b) > 0:
            merged_ref = pd.merge(
                cand_ref_a, cand_ref_b,
                on="clean_reference_id",
                suffixes=("_a", "_b")
            )
            total_candidate_pairs += len(merged_ref)

            if len(merged_ref) > 0:
                counts_a = cand_ref_a["clean_reference_id"].value_counts()
                counts_b = cand_ref_b["clean_reference_id"].value_counts()

                for _, row in merged_ref.iterrows():
                    ref = str(row["clean_reference_id"])
                    id_a = str(row["transaction_id_a"])
                    id_b = str(row["transaction_id_b"])

                    if id_a in matched_a or id_b in matched_b:
                        continue

                    # Currency Mismatch Check
                    if str(row["currency_a"]) != str(row["currency_b"]):
                        rejection_breakdown["currency_mismatch"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "CURRENCY_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": 0.0,
                            "explanation": f"Currency mismatch: {row['currency_a']} vs {row['currency_b']}. Currency conversion required.",
                            "recommended_action": "Manually convert currencies or configure FX rates.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a,
                                "record_id_b": id_b,
                                "reference": ref,
                                "matching_strategy": "FALLBACK_EXACT_REFERENCE",
                                "currency_a": str(row["currency_a"]),
                                "currency_b": str(row["currency_b"]),
                                "amount_a": float(row["amount_a"]),
                                "amount_b": float(row["amount_b"]),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                        continue

                    # If multiple candidates remain: AMBIGUOUS_CANDIDATE_CONFLICT (never arbitrary matches[0])
                    if counts_a.get(ref, 0) > 1 or counts_b.get(ref, 0) > 1:
                        rejection_breakdown["ambiguous_candidate_conflict"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "AMBIGUOUS_CANDIDATE_CONFLICT",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": float(row["amount_a"]),
                            "explanation": f"Ambiguous reference match: reference '{ref}' has multiple candidates across files.",
                            "recommended_action": "Manual review required to resolve 1-to-many candidate conflict.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a,
                                "record_id_b": id_b,
                                "reference": ref,
                                "matching_strategy": "FALLBACK_EXACT_REFERENCE",
                                "amount_a": float(row["amount_a"]),
                                "amount_b": float(row["amount_b"]),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                        continue

                    d_a = row["dt_date_a"]
                    d_b = row["dt_date_b"]
                    days_diff = abs((d_a - d_b).days) if (pd.notna(d_a) and pd.notna(d_b)) else 0
                    
                    amt_a = float(row["amount_a"])
                    amt_b = float(row["amount_b"])
                    net_a = float(row.get("net_amount_a", amt_a))
                    net_b = float(row.get("net_amount_b", amt_b))
                    
                    diff_val = round(abs(amt_a - amt_b), 2)
                    net_diff_val = min(
                        round(abs(net_a - amt_b), 2),
                        round(abs(amt_a - net_b), 2),
                        round(abs(net_a - net_b), 2)
                    )
                    best_diff = diff_val if diff_val <= self.amount_tolerance else net_diff_val

                    if best_diff <= self.amount_tolerance:
                        strat = "FALLBACK_EXACT_REFERENCE"
                        cat = "EXACT_MATCH" if (best_diff == 0.0 and days_diff == 0) else "TOLERANCE_MATCH"
                        conf = 95.0
                        rule = "Pass 2: Fallback Exact Reference Match"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    elif best_diff <= self.fee_tolerance:
                        strat = "FALLBACK_REFERENCE_FEE_DELTA"
                        cat = "TOLERANCE_MATCH"
                        conf = 90.0
                        rule = "Pass 2: Fallback Reference Match with Fee Delta"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    else:
                        # Reference match with amount difference -> AMOUNT_MISMATCH
                        rejection_breakdown["amount_mismatch"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "AMOUNT_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": diff_val,
                            "explanation": (
                                f"Amount mismatch on reference '{ref}': {row['_source_label_a']} reports "
                                f"${float(row['amount_a']):,.2f} vs {row['_source_label_b']} ${float(row['amount_b']):,.2f} (delta: ${diff_val:,.2f})."
                            ),
                            "recommended_action": "Reconcile payment processing fee or adjust rounding.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a,
                                "record_id_b": id_b,
                                "reference": ref,
                                "counterpart_record_id": id_b,
                                "counterpart_amount": float(row["amount_b"]),
                                "counterpart_source": str(row["_source_label_b"]),
                                "amount_a": float(row["amount_a"]),
                                "amount_b": float(row["amount_b"]),
                                "amount_delta": diff_val,
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)

        # ── PASS 3: FALLBACK 2 - EXACT AMOUNT + COMPATIBLE DATE WINDOW (±3 DAYS) ──
        unmatched_df_a = df_a[~df_a["transaction_id"].isin(matched_a)]
        unmatched_df_b = df_b[~df_b["transaction_id"].isin(matched_b)]

        if len(unmatched_df_a) > 0 and len(unmatched_df_b) > 0:
            merged_3 = pd.merge(
                unmatched_df_a, unmatched_df_b,
                on="amount",
                suffixes=("_a", "_b")
            )
            total_candidate_pairs += len(merged_3)

            if len(merged_3) > 0:
                dt_a = merged_3["dt_date_a"]
                dt_b = merged_3["dt_date_b"]
                days_diff_3 = np.abs((dt_a - dt_b).dt.days)
                date_window_mask = (days_diff_3 <= self.date_window_days)
                rejection_breakdown["date_mismatch"] += int(np.sum(~date_window_mask))

                pass3_candidates = merged_3[date_window_mask]
                if len(pass3_candidates) > 0:
                    cand_counts_a = pass3_candidates["transaction_id_a"].value_counts()
                    cand_counts_b = pass3_candidates["transaction_id_b"].value_counts()

                    for _, row in pass3_candidates.iterrows():
                        id_a = str(row["transaction_id_a"])
                        id_b = str(row["transaction_id_b"])

                        if id_a in matched_a or id_b in matched_b:
                            continue

                        # If multiple candidates remain: AMBIGUOUS_CANDIDATE_CONFLICT (never arbitrary matches[0])
                        if cand_counts_a.get(id_a, 0) > 1 or cand_counts_b.get(id_b, 0) > 1:
                            rejection_breakdown["ambiguous_candidate_conflict"] += 1
                            pass_exceptions.append({
                                "id": f"exc_{uuid.uuid4().hex[:10]}",
                                "record_id": id_a,
                                "source": str(row["_source_label_a"]),
                                "reason_code": "AMBIGUOUS_CANDIDATE_CONFLICT",
                                "discrepancy_level": "MATERIAL",
                                "amount_discrepancy": float(row["amount"]),
                                "explanation": f"Ambiguous candidate conflict: multiple transactions match amount ${float(row['amount']):,.2f} within date window.",
                                "recommended_action": "Manual review required to identify specific payment counterpart.",
                                "provenance": {
                                    "document_id": str(row["_doc_id_a"]),
                                    "filename": str(row["_doc_name_a"]),
                                    "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                    "row_index": int(row["_row_idx_a"]),
                                    "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                                    "raw_data": row["_raw_data_a"],
                                },
                                "evidence": {
                                    "record_id_a": id_a,
                                    "record_id_b": id_b,
                                    "amount": float(row["amount"]),
                                    "matching_strategy": "FALLBACK_AMOUNT_DATE",
                                },
                            })
                            matched_a.add(id_a)
                            matched_b.add(id_b)
                            continue

                        # Check entity token overlap
                        ent_a = str(row["clean_entity_a"])
                        ent_b = str(row["clean_entity_b"])
                        tokens_a = set(ent_a.split())
                        tokens_b = set(ent_b.split())
                        has_entity_overlap = bool(tokens_a & tokens_b) or ent_a == ent_b

                        score = 85.0 if has_entity_overlap else 76.0
                        if score < self.confidence_threshold:
                            continue

                        d_diff = int(abs((row["dt_date_a"] - row["dt_date_b"]).days))
                        diff_val = 0.0
                        rule = "Pass 3: Fallback Amount + Date Window Match"
                        match_entry = _build_match(row, "FALLBACK_AMOUNT_DATE", "FUZZY_MATCH", score, diff_val, d_diff, rule)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)

        # ── PASS 4: FALLBACK 3 - ENTITY NAME MATCH + DATE WINDOW ──
        unmatched_df_a = df_a[~df_a["transaction_id"].isin(matched_a)]
        unmatched_df_b = df_b[~df_b["transaction_id"].isin(matched_b)]

        if len(unmatched_df_a) > 0 and len(unmatched_df_b) > 0:
            merged_4 = pd.merge(
                unmatched_df_a, unmatched_df_b,
                on="clean_entity",
                suffixes=("_a", "_b")
            )
            total_candidate_pairs += len(merged_4)

            if len(merged_4) > 0:
                amt_diff_4 = np.abs(merged_4["amount_a"] - merged_4["amount_b"])
                dt_a = merged_4["dt_date_a"]
                dt_b = merged_4["dt_date_b"]
                days_diff_4 = np.abs((dt_a - dt_b).dt.days)

                pass4_mask = (amt_diff_4 <= self.fee_tolerance) & (days_diff_4 <= self.date_window_days)
                pass4_candidates = merged_4[pass4_mask]

                if len(pass4_candidates) > 0:
                    cand_counts_a4 = pass4_candidates["transaction_id_a"].value_counts()
                    cand_counts_b4 = pass4_candidates["transaction_id_b"].value_counts()

                    for _, row in pass4_candidates.iterrows():
                        id_a = str(row["transaction_id_a"])
                        id_b = str(row["transaction_id_b"])

                        if id_a in matched_a or id_b in matched_b:
                            continue

                        if cand_counts_a4.get(id_a, 0) > 1 or cand_counts_b4.get(id_b, 0) > 1:
                            rejection_breakdown["ambiguous_candidate_conflict"] += 1
                            continue

                        d_diff = int(abs((row["dt_date_a"] - row["dt_date_b"]).days))
                        diff_val = round(float(abs(row["amount_a"] - row["amount_b"])), 2)
                        rule = "Pass 4: Fallback Entity + Date Window Cluster Match"
                        match_entry = _build_match(row, "FALLBACK_ENTITY_AMOUNT_DATE", "FUZZY_MATCH", 78.0, diff_val, d_diff, rule)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)

        # Unmatched counterpart count
        unmatched_a_count = len(df_a) - len(matched_a)
        unmatched_b_count = len(df_b) - len(matched_b)
        rejection_breakdown["missing_counterpart"] = unmatched_a_count + unmatched_b_count

        # Diagnostics evaluation
        diagnostics = {
            "candidate_pairs_evaluated": total_candidate_pairs,
            "pass_matches_count": len(matches),
            "rejection_breakdown": rejection_breakdown,
            "zero_match_diagnostics": None,
        }

        # 0% Match Diagnosis
        if len(matches) == 0 and (len(df_a) > 0 or len(df_b) > 0):
            if total_candidate_pairs == 0:
                diag_reason = (
                    "0% Match: Zero candidate pairs were generated. Documents share no overlapping "
                    "canonical transaction IDs, reference tokens, common amounts, or equivalent entity names."
                )
            elif rejection_breakdown["amount_mismatch"] > 0 and rejection_breakdown["amount_mismatch"] == total_candidate_pairs:
                diag_reason = (
                    "0% Match: Candidate transaction IDs or references matched, but all transaction amounts differed "
                    f"beyond the allowed tolerance (${self.amount_tolerance:.2f})."
                )
            elif rejection_breakdown["date_mismatch"] > 0 and rejection_breakdown["date_mismatch"] == total_candidate_pairs:
                diag_reason = (
                    "0% Match: Identical amounts found, but all transaction dates differed beyond the allowed "
                    f"settlement window ({self.date_window_days} days)."
                )
            else:
                diag_reason = (
                    f"0% Match: {total_candidate_pairs} candidate pairs evaluated, but none satisfied the "
                    "reconciliation confidence threshold."
                )
            diagnostics["zero_match_diagnostics"] = diag_reason

        return matches, matched_a, matched_b, pass_exceptions, diagnostics

    # ─────────────────────────────────────────────────────────────
    # EXCEPTION GENERATION & CLASSIFICATION
    # ─────────────────────────────────────────────────────────────

    def _generate_exceptions(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        matched_a: Set[str],
        matched_b: Set[str],
        duplicates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Generate structured exceptions for unmatched records and duplicate transactions.
        """
        exceptions: List[Dict[str, Any]] = []

        # Duplicate ID set
        dup_rec_ids = set()
        for d in duplicates:
            for r in d.get("records", []):
                dup_rec_ids.add(r["record_id"])

        # 1. Unmatched in Source A (Ledger)
        unmatched_a = df_a[~df_a["transaction_id"].isin(matched_a)]
        for _, row in unmatched_a.iterrows():
            rec_id = row["transaction_id"]
            clean_ref = str(row["clean_reference_id"])
            is_dup = rec_id in dup_rec_ids

            # Check if counterpart with same clean reference exists in df_b
            b_cands = df_b[df_b["clean_reference_id"] == clean_ref] if len(df_b) > 0 and clean_ref else pd.DataFrame()
            if is_dup:
                reason_code = "DUPLICATE_TRANSACTION"
                explanation = "Duplicate record in internal ledger."
                discrepancy_val = float(row["amount"])
                action = "Investigate duplicate ledger accrual."
                extra_ev = {}
            elif len(b_cands) > 1:
                reason_code = "AMBIGUOUS_CANDIDATE_CONFLICT"
                discrepancy_val = float(row["amount"])
                explanation = (
                    f"Ambiguous reference match: reference '{clean_ref}' has {len(b_cands)} "
                    "candidate counterpart records."
                )
                action = "Manual review required to resolve candidate conflict."
                extra_ev = {}
            elif len(b_cands) == 1:
                b_match = b_cands.iloc[0]
                reason_code = "AMOUNT_MISMATCH"
                amt_delta = round(float(abs(row["amount"] - b_match["amount"])), 2)
                discrepancy_val = amt_delta
                explanation = (
                    f"Amount discrepancy on reference '{clean_ref}': {row['_source_label']} reports "
                    f"${float(row['amount']):,.2f} vs {b_match['_source_label']} ${float(b_match['amount']):,.2f} (delta: ${amt_delta:,.2f})."
                )
                action = "Reconcile payment processing fee or adjust rounding."
                extra_ev = {
                    "record_id_a": rec_id,
                    "record_id_b": str(b_match["transaction_id"]),
                    "amount_a": float(row["amount"]),
                    "amount_b": float(b_match["amount"]),
                    "counterpart_record_id": str(b_match["transaction_id"]),
                    "counterpart_amount": float(b_match["amount"]),
                    "counterpart_source": str(b_match["_source_label"]),
                    "amount_delta": amt_delta,
                }
            else:
                reason_code = "MISSING_COUNTERPART"
                explanation = f"Ledger record {rec_id} (${float(row['amount']):,.2f}) has no matching bank or settlement counterpart."
                discrepancy_val = float(row["amount"])
                action = "Investigate unrecorded bank debit or reverse ledger accrual."
                extra_ev = {"record_id_a": rec_id, "amount_a": float(row["amount"])}

            exc_ev = {
                "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                "member_id": row.get("member_id"),
                "document_role": str(row.get("_doc_role", "TRANSACTIONS")),
                "row_index": int(row["_row_idx"]),
                "reference": row["raw_reference_id"],
                "date": row["iso_date"],
                "entity": row["raw_entity"],
                "amount": f"${float(row['amount']):,.2f}",
            }
            exc_ev.update(extra_ev)

            exceptions.append({
                "id": f"exc_{uuid.uuid4().hex[:10]}",
                "record_id": rec_id,
                "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                "source": row["_source_label"],
                "reason_code": reason_code,
                "discrepancy_level": "MATERIAL",
                "amount_discrepancy": discrepancy_val,
                "explanation": explanation,
                "recommended_action": action,
                "provenance": {
                    "document_id": row["_doc_id"],
                    "filename": row["_doc_name"],
                    "document_role": str(row.get("_doc_role", "TRANSACTIONS")),
                    "row_index": int(row["_row_idx"]),
                    "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                    "member_id": row.get("member_id"),
                    "raw_data": row["_raw_data"],
                },
                "evidence": exc_ev,
            })

        # 2. Unmatched in Source B (Counterparty / Bank)
        unmatched_b = df_b[~df_b["transaction_id"].isin(matched_b)]
        for _, row in unmatched_b.iterrows():
            rec_id = row["transaction_id"]
            clean_ref = str(row["clean_reference_id"])
            is_dup = rec_id in dup_rec_ids

            a_cands = df_a[df_a["clean_reference_id"] == clean_ref] if len(df_a) > 0 and clean_ref else pd.DataFrame()
            if is_dup:
                reason_code = "DUPLICATE_TRANSACTION"
                explanation = "Duplicate settlement entry in bank statement."
                discrepancy_val = float(row["amount"])
                action = "Investigate duplicate settlement batch."
                extra_ev = {}
            elif len(a_cands) > 1:
                reason_code = "AMBIGUOUS_CANDIDATE_CONFLICT"
                explanation = f"Ambiguous reference match: multiple records share reference '{clean_ref}'."
                discrepancy_val = float(row["amount"])
                action = "Manual review required to resolve candidate conflict."
                extra_ev = {}
            elif len(a_cands) == 1:
                a_match = a_cands.iloc[0]
                reason_code = "AMOUNT_MISMATCH"
                amt_delta = round(float(abs(row["amount"] - a_match["amount"])), 2)
                discrepancy_val = amt_delta
                explanation = (
                    f"Amount discrepancy on reference '{clean_ref}': {row['_source_label']} reports "
                    f"${float(row['amount']):,.2f} vs {a_match['_source_label']} ${float(a_match['amount']):,.2f} (delta: ${amt_delta:,.2f})."
                )
                action = "Reconcile payment processing fee or adjust rounding."
                extra_ev = {
                    "record_id_a": str(a_match["transaction_id"]),
                    "record_id_b": rec_id,
                    "amount_a": float(a_match["amount"]),
                    "amount_b": float(row["amount"]),
                    "counterpart_record_id": str(a_match["transaction_id"]),
                    "counterpart_amount": float(a_match["amount"]),
                    "counterpart_source": str(a_match["_source_label"]),
                    "amount_delta": amt_delta,
                }
            else:
                reason_code = "UNRECORDED_TRANSACTION"
                explanation = f"Bank transaction {rec_id} (${float(row['amount']):,.2f}) was processed by the bank but is unrecorded in internal books."
                discrepancy_val = float(row["amount"])
                action = "Post missing journal entry in internal ledger."
                extra_ev = {"record_id_b": rec_id, "amount_b": float(row["amount"])}

            exc_ev = {
                "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                "member_id": row.get("member_id"),
                "document_role": str(row.get("_doc_role", "SETTLEMENTS")),
                "row_index": int(row["_row_idx"]),
                "reference": row["raw_reference_id"],
                "date": row["iso_date"],
                "entity": row["raw_entity"],
                "amount": f"${float(row['amount']):,.2f}",
            }
            exc_ev.update(extra_ev)

            exceptions.append({
                "id": f"exc_{uuid.uuid4().hex[:10]}",
                "record_id": rec_id,
                "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                "source": row["_source_label"],
                "reason_code": reason_code,
                "discrepancy_level": "MATERIAL",
                "amount_discrepancy": discrepancy_val,
                "explanation": explanation,
                "recommended_action": action,
                "provenance": {
                    "document_id": row["_doc_id"],
                    "filename": row["_doc_name"],
                    "document_role": str(row.get("_doc_role", "SETTLEMENTS")),
                    "row_index": int(row["_row_idx"]),
                    "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                    "member_id": row.get("member_id"),
                    "raw_data": row["_raw_data"],
                },
                "evidence": exc_ev,
            })

        return exceptions

    # ─────────────────────────────────────────────────────────────
    # EMPTY / FAILURE RESULTS
    # ─────────────────────────────────────────────────────────────

    def _empty_result(
        self, run_id: str, thread_id: str, message: str, schema_result: Optional[SchemaMappingResult] = None
    ) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "COMPLETED_EMPTY",
            "message": message,
            "documents_processed": [],
            "detected_schemas": {},
            "mapped_columns": {},
            "records_processed": 0,
            "candidate_pairs_evaluated": 0,
            "matched_records_count": 0,
            "unmatched_records_count": 0,
            "duplicates_count": 0,
            "match_rate": 0.0,
            "exact_matches_count": 0,
            "fuzzy_matches_count": 0,
            "normal_discrepancies_count": 0,
            "material_discrepancies_count": 0,
            "mismatch_reasons": {},
            "totals_and_statistics": {
                "total_primary_amount": 0.0,
                "total_counterparty_amount": 0.0,
                "matched_volume": 0.0,
                "total_discrepancy_amount": 0.0,
                "processing_time_sec": 0.0,
                "throughput_records_sec": 0.0,
            },
            "diagnostics": {
                "candidate_pairs_evaluated": 0,
                "rejection_breakdown": {},
                "zero_match_diagnostics": message,
            },
            "matches": [],
            "exceptions": [],
        }

    def _failed_schema_result(
        self, run_id: str, thread_id: str, schema_result: SchemaMappingResult, message: str
    ) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "SCHEMA_MAPPING_FAILED",
            "message": message,
            "documents_processed": [
                {
                    "document_id": doc_id,
                    "filename": s.filename,
                    "detected_schema": s.raw_columns,
                    "mapped_columns": s.mapped_columns,
                    "missing_required_fields": s.missing_required_fields,
                }
                for doc_id, s in schema_result.schemas.items()
            ],
            "detected_schemas": {doc_id: s.raw_columns for doc_id, s in schema_result.schemas.items()},
            "mapped_columns": {doc_id: s.mapped_columns for doc_id, s in schema_result.schemas.items()},
            "records_processed": 0,
            "candidate_pairs_evaluated": 0,
            "matched_records_count": 0,
            "unmatched_records_count": 0,
            "duplicates_count": 0,
            "match_rate": 0.0,
            "exact_matches_count": 0,
            "fuzzy_matches_count": 0,
            "normal_discrepancies_count": 0,
            "material_discrepancies_count": 0,
            "mismatch_reasons": {"column_mapping_error": len(schema_result.diagnostics)},
            "totals_and_statistics": {
                "total_primary_amount": 0.0,
                "total_counterparty_amount": 0.0,
                "matched_volume": 0.0,
                "total_discrepancy_amount": 0.0,
                "processing_time_sec": 0.0,
                "throughput_records_sec": 0.0,
            },
            "diagnostics": {
                "candidate_pairs_evaluated": 0,
                "rejection_breakdown": {"column_mapping_error": len(schema_result.diagnostics)},
                "zero_match_diagnostics": f"Reconciliation could not start because column mapping failed: {message}",
            },
            "matches": [],
            "exceptions": [],
        }


pandas_reconciler = PandasReconciliationEngine()
