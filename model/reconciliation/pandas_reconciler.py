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
    parse_optional_amount,
    is_missing_amount_value,
    normalize_date,
    normalize_currency,
    normalize_entity_name,
    normalize_transaction_id,
    _is_nan,
)


# Explicit FX conversion rate table (populated only via explicit caller input).
# NEVER invent rates: empty dict means no conversion is possible and any
# cross-currency comparison must emit CURRENCY_MISMATCH / CURRENCY_CONVERSION_REQUIRED.
FX_RATES: Dict[Tuple[str, str], float] = {}


def get_fx_rate(from_ccy: str, to_ccy: str, fx_rates: Optional[Dict[Tuple[str, str], float]] = None) -> Optional[float]:
    """Return an explicit FX rate if reliably available, else None. Never invents rates."""
    if not from_ccy or not to_ccy or str(from_ccy).upper() == str(to_ccy).upper():
        return 1.0
    table = fx_rates if fx_rates is not None else FX_RATES
    key = (str(from_ccy).upper(), str(to_ccy).upper())
    if key in table:
        try:
            r = float(table[key])
            if r and r > 0 and math.isfinite(r):
                return r
        except Exception:
            return None
    return None


def build_fx_evidence(
    amount_a: Any,
    currency_a: str,
    amount_b: Any,
    currency_b: str,
    fx_rates: Optional[Dict[Tuple[str, str], float]] = None,
    conversion_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Safe FX evidence block. Preserves originals, records conversion path only
    when a reliable explicit rate exists; otherwise marks conversion required
    and leaves converted fields as None. Never compares USD 100 and EUR 100
    as equal merely because numerics match.
    """
    rate = get_fx_rate(currency_a, currency_b, fx_rates)
    if rate is not None and rate != 1.0:
        try:
            converted = round(float(amount_a) * float(rate), 2) if amount_a is not None else None
        except Exception:
            converted = None
        return {
            "original_amount": amount_a,
            "original_currency": currency_a,
            "counterpart_amount": amount_b,
            "counterpart_currency": currency_b,
            "exchange_rate": rate,
            "converted_amount": converted,
            "conversion_source": conversion_source or "EXPLICIT_RATE_TABLE",
            "fx_status": "CONVERTED",
        }
    if str(currency_a) != str(currency_b):
        return {
            "original_amount": amount_a,
            "original_currency": currency_a,
            "counterpart_amount": amount_b,
            "counterpart_currency": currency_b,
            "exchange_rate": None,
            "converted_amount": None,
            "conversion_source": None,
            "fx_status": "CURRENCY_CONVERSION_REQUIRED",
        }
    return {
        "original_amount": amount_a,
        "original_currency": currency_a,
        "counterpart_amount": amount_b,
        "counterpart_currency": currency_b,
        "exchange_rate": 1.0,
        "converted_amount": amount_b,
        "conversion_source": "SAME_CURRENCY",
        "fx_status": "NOT_REQUIRED",
    }


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
        fx_rates: Optional[Dict[str, float]] = None,
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
            primary_df, secondary_df,
            fx_rates=fx_rates,
        )

        # ── STAGE 6b: Two-way split detection (1:2 / 2:1) over unmatched rows ──
        split_matches, split_ids_a, split_ids_b = self._detect_two_way_splits(
            primary_df, secondary_df, matched_ids_a, matched_ids_b
        )
        matched_ids_a |= split_ids_a
        matched_ids_b |= split_ids_b

        # ── STAGE 7: Exception Generation & Discrepancy Classification ──
        unmatched_exceptions = self._generate_exceptions(
            primary_df, secondary_df, matched_ids_a, matched_ids_b, duplicate_records_list
        )
        exceptions = pass_exceptions + unmatched_exceptions

        # ── STAGE 8: Enrichment Adjustments (Fees, Taxes, Refunds) ──
        # Deterministic join of separate fee/refund/chargeback documents onto
        # primary/counterpart rows via canonical transaction ID, with provenance.
        enrichment_adjustments: List[Dict[str, Any]] = []
        enrichment_join_provenance: List[Dict[str, Any]] = []
        for enrich_item in plan.enrichment_docs:
            e_table = next((t for t in document_tables if t[1] == enrich_item.document_id), None)
            if e_table is not None:
                e_df_raw = e_table[0]
                e_schema = schema_result.schemas.get(enrich_item.document_id)
                try:
                    e_norm = self._normalize_dataframe(e_df_raw, e_schema, role=enrich_item.role) if e_schema else None
                except Exception:
                    e_norm = None
                joined = 0
                unjoined = 0
                join_details: List[Dict[str, Any]] = []
                if e_norm is not None and len(e_norm) > 0:
                    # Build adjustment map: canonical ID -> adjustment amount (prefer amount, else fee/refund/cb).
                    for _, erow in e_norm.iterrows():
                        canon = str(erow.get("canonical_transaction_id") or "")
                        if not canon:
                            unjoined += 1
                            continue
                        adj_amt = None
                        for _c in ["amount", "fee_amount", "refund_amount", "chargeback_amount", "net_amount"]:
                            try:
                                _v = float(erow.get(_c))
                                if _v is not None and not (isinstance(_v, float) and (math.isnan(_v) or math.isinf(_v))):
                                    if abs(_v) > 0:
                                        adj_amt = _v
                                        break
                            except Exception:
                                continue
                        # Find target rows in primary/secondary with same canonical ID.
                        targets_a = primary_df[primary_df["canonical_transaction_id"] == canon] if "canonical_transaction_id" in primary_df.columns else pd.DataFrame()
                        targets_b = secondary_df[secondary_df["canonical_transaction_id"] == canon] if "canonical_transaction_id" in secondary_df.columns else pd.DataFrame()
                        if len(targets_a) == 0 and len(targets_b) == 0:
                            unjoined += 1
                            join_details.append({"canonical_transaction_id": canon, "status": "UNRESOLVED_NO_JOIN_KEY",
                                                 "reason": "No primary/counterpart row shares this canonical ID."})
                        else:
                            joined += 1
                            join_details.append({"canonical_transaction_id": canon, "status": "JOINED",
                                                 "targets_primary": len(targets_a), "targets_counterpart": len(targets_b),
                                                 "adjustment_amount": adj_amt,
                                                 "provenance": {"document_id": enrich_item.document_id,
                                                                "filename": enrich_item.filename,
                                                                "role": enrich_item.role.value,
                                                                "adjustment_type": enrich_item.adjustment_type}})
                            enrichment_join_provenance.append({
                                "canonical_transaction_id": canon,
                                "enrichment_document_id": enrich_item.document_id,
                                "adjustment_type": enrich_item.adjustment_type,
                                "adjustment_amount": adj_amt,
                            })
                enrichment_adjustments.append({
                    "document_id": enrich_item.document_id,
                    "filename": enrich_item.filename,
                    "role": enrich_item.role.value,
                    "adjustment_type": enrich_item.adjustment_type,
                    "records_count": len(e_df_raw),
                    "joined_records": joined,
                    "unjoined_records": unjoined,
                    "join_status": "JOINED" if joined > 0 and unjoined == 0 else ("PARTIAL" if joined > 0 else "UNRESOLVED"),
                    "join_details": join_details[:20],
                })

        # ── STAGE 8b: Multi-Source Grouping Overlay (deterministic, additive) ──
        # Groups ALL normalized documents by canonical transaction ID, preserving
        # source-level provenance and reporting which sources agree/disagree.
        # This never replaces the authoritative 2-way result; it is an overlay.
        try:
            multi_source = self._compute_multi_source_groups(
                document_tables, schema_result, role_classifications)
        except Exception:
            multi_source = {"groups": [], "summary": {"total_groups": 0, "status": "UNAVAILABLE"}}

        # ── STAGE 9: Authoritative Metrics (Source Population Denominator) ──
        elapsed_sec = time.perf_counter() - start_time
        source_pop = len(primary_df)
        counterpart_pop = len(secondary_df)
        throughput = (source_pop + counterpart_pop) / elapsed_sec if elapsed_sec > 0 else 0.0

        def _nan_safe_sum(series) -> float:
            try:
                s = pd.to_numeric(series, errors="coerce").fillna(0.0)
                return float(s.sum())
            except Exception:
                return 0.0

        total_amt_a = _nan_safe_sum(primary_df["amount"]) if "amount" in primary_df.columns else 0.0
        total_amt_b = _nan_safe_sum(secondary_df["amount"]) if "amount" in secondary_df.columns else 0.0
        matched_amt_a = sum((m.get("amount_a") or 0.0) for m in matches if m.get("amount_a") is not None)
        discrepancy_amt = sum((m.get("amount_diff") or 0.0) for m in matches if m.get("amount_diff") is not None) + sum(
            (e.get("amount_discrepancy") or 0.0) for e in exceptions if e.get("amount_discrepancy") is not None)

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
            "split_matches_count": len(split_matches),
            "match_rate": round(match_rate, 1),
            "exact_matches_count": exact_matches_count,
            "fuzzy_matches_count": fuzzy_matches_count,
            "normal_discrepancies_count": sum(1 for m in matches if m["discrepancy_level"] == "NORMAL"),
            "material_discrepancies_count": sum(1 for e in exceptions if e["discrepancy_level"] == "MATERIAL"),
            "mismatch_reasons": diagnostics["rejection_breakdown"],
            "enrichment_adjustments": enrichment_adjustments,
            "enrichment_join_provenance": enrichment_join_provenance,
            "multi_source_reconciliation": multi_source,
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
            "split_matches": split_matches,
        }

        return clean_for_json(result)

    # ─────────────────────────────────────────────────────────────
    # MULTI-SOURCE GROUPING OVERLAY
    # ─────────────────────────────────────────────────────────────

    def _compute_multi_source_groups(
        self,
        document_tables: List[Tuple[pd.DataFrame, str, str, str]],
        schema_result: Any,
        role_classifications: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Deterministic multi-source grouping across ALL uploaded documents.

        Groups rows by canonical_transaction_id, preserving per-source provenance
        and reporting agreement: ALL_AGREE | ONE_DISAGREES | MULTIPLE_DISAGREE |
        MISSING_SOURCE | AMBIGUOUS | CURRENCY_MISMATCH | INVALID_RECORD.

        Never reduces to a misleading two-way result: every participating source
        is listed explicitly with its amount/currency/row provenance.
        """
        # Normalize every document independently.
        norm_frames: List[pd.DataFrame] = []
        for df_raw, doc_id, filename, source_label in document_tables:
            schema = schema_result.schemas.get(doc_id) if schema_result else None
            if schema is None:
                continue
            cls = role_classifications.get(doc_id) if role_classifications else None
            role = cls.document_role if cls else None
            try:
                ndf = self._normalize_dataframe(df_raw, schema, role=role)
                norm_frames.append(ndf)
            except Exception:
                continue
        if not norm_frames:
            return {"groups": [], "summary": {"total_groups": 0, "status": "NO_DATA"}}
        all_rows = pd.concat(norm_frames, ignore_index=True)
        if len(all_rows) == 0:
            return {"groups": [], "summary": {"total_groups": 0, "status": "NO_DATA"}}
        # Only rows with a canonical ID participate in grouping.
        grouped = all_rows[all_rows["canonical_transaction_id"].str.len() > 0].groupby("canonical_transaction_id")
        groups: List[Dict[str, Any]] = []
        _counts = {"ALL_AGREE": 0, "ONE_DISAGREES": 0, "MULTIPLE_DISAGREE": 0,
                   "MISSING_SOURCE": 0, "AMBIGUOUS": 0, "CURRENCY_MISMATCH": 0, "INVALID_RECORD": 0}
        # Expected sources = distinct source labels uploaded.
        expected_sources = sorted(all_rows["_source_label"].dropna().unique().tolist())
        for canon_id, g in grouped:
            sources: List[Dict[str, Any]] = []
            for _, r in g.iterrows():
                try:
                    _a = float(r["amount"])
                    _a = None if (isinstance(_a, float) and (math.isnan(_a) or math.isinf(_a))) else _a
                except Exception:
                    _a = None
                try:
                    _n = float(r.get("net_amount"))
                    _n = None if (isinstance(_n, float) and (math.isnan(_n) or math.isinf(_n))) else _n
                except Exception:
                    _n = None
                sources.append({
                    "source": str(r["_source_label"]),
                    "document_id": str(r["_doc_id"]),
                    "filename": str(r["_doc_name"]),
                    "document_role": str(r.get("_doc_role", "UNKNOWN")),
                    "row_index": int(r["_row_idx"]),
                    "record_id": str(r["transaction_id"]),
                    "amount": _a,
                    "net_amount": _n,
                    "currency": str(r.get("currency", "USD")),
                    "date": str(r.get("iso_date")),
                    "entity": str(r.get("raw_entity") or ""),
                    "amount_missing": bool(_a is None),
                })
            # Duplicate within same source => AMBIGUOUS
            _src_counts: Dict[str, int] = {}
            for s in sources:
                _src_counts[s["source"]] = _src_counts.get(s["source"], 0) + 1
            if any(c > 1 for c in _src_counts.values()):
                status = "AMBIGUOUS"
            elif any(s["amount_missing"] for s in sources):
                status = "INVALID_RECORD"
            elif len({s["currency"] for s in sources}) > 1:
                status = "CURRENCY_MISMATCH"
            elif len(sources) < len(expected_sources):
                # Present in a strict subset of uploaded sources.
                status = "MISSING_SOURCE"
            else:
                # All sources present: compare amounts within tolerance.
                _amts = [s["amount"] for s in sources if s["amount"] is not None]
                if not _amts:
                    status = "INVALID_RECORD"
                else:
                    _base = _amts[0]
                    _out = [abs(a - _base) for a in _amts]
                    _bad = sum(1 for d in _out if d > self.amount_tolerance and d > self.fee_tolerance)
                    # Fee-level deltas count as disagreement but flagged separately?
                    _tol_bad = sum(1 for d in _out if d > self.amount_tolerance)
                    if _bad == 0 and _tol_bad == 0:
                        status = "ALL_AGREE"
                    elif _tol_bad == 1:
                        status = "ONE_DISAGREES"
                    elif _tol_bad > 1:
                        status = "MULTIPLE_DISAGREE"
                    else:
                        status = "ONE_DISAGREES"
            _counts[status] = _counts.get(status, 0) + 1
            # Which source disagrees? (median-based outlier when numeric)
            disagreeing: List[str] = []
            if status in ("ONE_DISAGREES", "MULTIPLE_DISAGREE") and len(sources) >= 2:
                try:
                    import statistics as _st
                    _vals = sorted([s["amount"] for s in sources if s["amount"] is not None])
                    _med = _st.median(_vals) if _vals else None
                    if _med is not None:
                        for s in sources:
                            if s["amount"] is not None and abs(s["amount"] - _med) > self.fee_tolerance:
                                disagreeing.append(s["source"])
                except Exception:
                    pass
            present = sorted({s["source"] for s in sources})
            missing = [s for s in expected_sources if s not in present]
            groups.append({
                "canonical_transaction_id": str(canon_id),
                "status": status,
                "sources_present": present,
                "sources_missing": missing,
                "sources_agree": [s for s in present if s not in disagreeing] if disagreeing else present,
                "sources_disagree": disagreeing,
                "entries": sources,
            })
        # Deterministic ordering.
        groups.sort(key=lambda g: g["canonical_transaction_id"])
        summary = {"total_groups": len(groups), "status": "COMPLETED",
                   "expected_sources": expected_sources, **_counts}
        return {"groups": groups, "summary": summary}

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

        # 4. Amount — missing amounts are preserved as NaN (None), NEVER coerced to 0.0.
        # Records without amounts are excluded from amount-based matching and
        # surfaced as INVALID_RECORD / MISSING_AMOUNT exceptions.
        def _opt_float_list(series_vals) -> List[Any]:
            out: List[Any] = []
            for v in series_vals:
                d = parse_optional_amount(v)
                out.append(float(d) if d is not None else float("nan"))
            return out

        amount_col = None
        if "amount" in mapped and mapped["amount"] in df_raw.columns:
            amount_col = mapped["amount"]
            df["amount"] = _opt_float_list(df_raw[amount_col])
        elif "taxable_amount" in df_raw.columns:
            amount_col = "taxable_amount"
            df["amount"] = _opt_float_list(df_raw["taxable_amount"])
        elif "total_amount" in df_raw.columns:
            amount_col = "total_amount"
            df["amount"] = _opt_float_list(df_raw["total_amount"])
        else:
            debit_col = mapped.get("debit_amount") or next((c for c in df_raw.columns if "debit" in c.lower()), None)
            credit_col = mapped.get("credit_amount") or next((c for c in df_raw.columns if "credit" in c.lower()), None)
            if debit_col and debit_col in df_raw.columns:
                amount_col = debit_col
                df["amount"] = _opt_float_list(df_raw[debit_col])
            elif credit_col and credit_col in df_raw.columns:
                amount_col = credit_col
                df["amount"] = _opt_float_list(df_raw[credit_col])
            else:
                amount_col = None
                df["amount"] = [float("nan")] * n_rows

        df["_amount_missing"] = df["amount"].isna()
        df["_amount_source_column"] = [amount_col] * n_rows
        # Gross amount: the ingested gross figure (may be NaN when missing).
        df["gross_amount"] = df["amount"]

        # Fee, Refund, Chargeback Netting — preserve provenance.
        # Absent column => business rule allows zero (no adjustment schedule present).
        # Present-but-blank cell => missing adjustment (NaN), NOT silently zero.
        def _adjustment_col(mapped_key: str) -> Tuple[Any, Any]:
            col = mapped.get(mapped_key) if mapped_key in mapped else None
            # Fallback: scan raw columns for known synonyms not caught by mapper
            if (not col or col not in df_raw.columns) and n_rows > 0:
                _syns = {
                    "fee_amount": ["gateway_fee", "mdr", "mdr_fee", "fees_deducted", "transaction_fee",
                                   "processing_fee", "platform_fee", "commission", "service_charge",
                                   "service_fee", "convenience_fee"],
                    "refund_amount": ["refund", "refund_amount", "return_amount", "reversal",
                                      "refunded_amount", "credit_note_amount"],
                    "chargeback_amount": ["chargeback", "chargeback_amount", "dispute_amount",
                                          "dispute", "dispute_fee", "chargeback_fee"],
                }.get(mapped_key, [])
                for c in df_raw.columns:
                    nc = str(c).strip().lower().replace(" ", "_").replace("-", "_")
                    if nc in _syns:
                        col = c
                        break
            if col and col in df_raw.columns:
                vals: List[Any] = []
                present: List[bool] = []
                for v in df_raw[col]:
                    if is_missing_amount_value(v) and not (isinstance(v, (int, float)) and float(v) == 0.0):
                        # Blank cell in a present column: missing adjustment, not zero.
                        # Treat as 0.0 for arithmetic but flag provenance.
                        vals.append(0.0)
                        present.append(False)
                    else:
                        d = parse_optional_amount(v)
                        vals.append(float(d) if d is not None else 0.0)
                        # Present when a genuine numeric (including explicit zero) was supplied.
                        present.append(d is not None)
                return vals, present, col
            return [0.0] * n_rows, [False] * n_rows, None

        fee_vals, fee_present, fee_col = _adjustment_col("fee_amount")
        df["fee_amount"] = fee_vals
        df["_fee_present"] = fee_present
        df["_fee_source_column"] = [fee_col] * n_rows

        ref_vals, ref_present, ref_col = _adjustment_col("refund_amount")
        df["refund_amount"] = ref_vals
        df["_refund_present"] = ref_present
        df["_refund_source_column"] = [ref_col] * n_rows

        cb_vals, cb_present, cb_col = _adjustment_col("chargeback_amount")
        df["chargeback_amount"] = cb_vals
        df["_chargeback_present"] = cb_present
        df["_chargeback_source_column"] = [cb_col] * n_rows

        # Calculate Net Amount (Gross - Fee - Refund - Chargeback).
        # NaN gross => NaN net (missing, excluded from amount matching).
        df["net_amount"] = df["gross_amount"] - df["fee_amount"] - df["refund_amount"] - df["chargeback_amount"]

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
        self, df_a: pd.DataFrame, df_b: pd.DataFrame, fx_rates: Optional[Dict[str, float]] = None
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
            "missing_amount": 0,
            "invalid_record": 0,
        }

        total_candidate_pairs = 0

        # Helper to construct clean match entry with full row provenance
        def _safe_amt(v: Any) -> Optional[float]:
            try:
                f = float(v)
                if math.isnan(f) or math.isinf(f):
                    return None
                return f
            except Exception:
                return None

        def _build_match(row: pd.Series, strat: str, cat: str, conf: float, diff_val: float, days_diff: int, rule_name: str,
                         gross_diff: Optional[float] = None, net_diff: Optional[float] = None,
                         match_basis: Optional[str] = None) -> Dict[str, Any]:
            id_a = str(row["transaction_id_a"])
            id_b = str(row["transaction_id_b"])
            canon_id = str(row.get("canonical_transaction_id_a") or row.get("canonical_transaction_id") or id_a)
            amt_a = _safe_amt(row["amount_a"]) if "amount_a" in row else _safe_amt(row.get("amount"))
            amt_b = _safe_amt(row["amount_b"]) if "amount_b" in row else _safe_amt(row.get("amount"))
            gross_a = _safe_amt(row.get("gross_amount_a", amt_a))
            gross_b = _safe_amt(row.get("gross_amount_b", amt_b))
            net_a = _safe_amt(row.get("net_amount_a", row.get("net_amount")))
            net_b = _safe_amt(row.get("net_amount_b", row.get("net_amount")))
            fee_a = _safe_amt(row.get("fee_amount_a", row.get("fee_amount", 0.0))) or 0.0
            fee_b = _safe_amt(row.get("fee_amount_b", row.get("fee_amount", 0.0))) or 0.0
            ref_a = _safe_amt(row.get("refund_amount_a", row.get("refund_amount", 0.0))) or 0.0
            ref_b = _safe_amt(row.get("refund_amount_b", row.get("refund_amount", 0.0))) or 0.0
            cb_a = _safe_amt(row.get("chargeback_amount_a", row.get("chargeback_amount", 0.0))) or 0.0
            cb_b = _safe_amt(row.get("chargeback_amount_b", row.get("chargeback_amount", 0.0))) or 0.0
            if gross_diff is None:
                gross_diff = round(abs((amt_a or 0.0) - (amt_b or 0.0)), 2) if amt_a is not None and amt_b is not None else None
            if net_diff is None:
                if net_a is not None and net_b is not None:
                    net_diff = round(abs(net_a - net_b), 2)
                elif net_a is not None and amt_b is not None:
                    net_diff = round(abs(net_a - amt_b), 2)
                elif amt_a is not None and net_b is not None:
                    net_diff = round(abs(amt_a - net_b), 2)
                else:
                    net_diff = None
            if match_basis is None:
                # Infer basis: gross if gross diff drives the match, else net.
                if gross_diff is not None and gross_diff <= self.amount_tolerance:
                    match_basis = "GROSS"
                elif net_diff is not None and net_diff <= max(self.amount_tolerance, self.fee_tolerance):
                    match_basis = "NET"
                else:
                    match_basis = "GROSS"
            fx_ev = build_fx_evidence(amt_a, str(row["currency_a"]), amt_b, str(row["currency_b"]), fx_rates=fx_rates)
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
                "amount_a": amt_a,
                "amount_b": amt_b,
                "gross_amount_a": gross_a,
                "gross_amount_b": gross_b,
                "fee_amount_a": fee_a,
                "fee_amount_b": fee_b,
                "refund_amount_a": ref_a,
                "refund_amount_b": ref_b,
                "chargeback_amount_a": cb_a,
                "chargeback_amount_b": cb_b,
                "net_amount_a": net_a,
                "net_amount_b": net_b,
                "gross_diff": gross_diff,
                "net_diff": net_diff,
                "match_basis": match_basis,
                "amount_diff": diff_val,
                "date_a": str(row["iso_date_a"]),
                "date_b": str(row["iso_date_b"]),
                "days_diff": days_diff,
                "currency_a": str(row["currency_a"]),
                "currency_b": str(row["currency_b"]),
                "fx": fx_ev,
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
                    "amount_a": _safe_amt(row["amount_a"]) if "amount_a" in row else _safe_amt(row.get("amount")),
                    "amount_b": _safe_amt(row["amount_b"]) if "amount_b" in row else _safe_amt(row.get("amount")),
                    "gross_amount_a": _safe_amt(row.get("gross_amount_a")),
                    "gross_amount_b": _safe_amt(row.get("gross_amount_b")),
                    "net_amount_a": _safe_amt(row.get("net_amount_a")),
                    "net_amount_b": _safe_amt(row.get("net_amount_b")),
                    "fee_amount_a": _safe_amt(row.get("fee_amount_a")) or 0.0,
                    "fee_amount_b": _safe_amt(row.get("fee_amount_b")) or 0.0,
                    "refund_amount_a": _safe_amt(row.get("refund_amount_a")) or 0.0,
                    "refund_amount_b": _safe_amt(row.get("refund_amount_b")) or 0.0,
                    "chargeback_amount_a": _safe_amt(row.get("chargeback_amount_a")) or 0.0,
                    "chargeback_amount_b": _safe_amt(row.get("chargeback_amount_b")) or 0.0,
                    "gross_diff": gross_diff,
                    "net_diff": net_diff,
                    "match_basis": match_basis,
                    "fx": build_fx_evidence(_safe_amt(row.get("amount_a")), str(row["currency_a"]), _safe_amt(row.get("amount_b")), str(row["currency_b"]), fx_rates=fx_rates),
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

                    # Missing-amount guard: amount-less records can NEVER amount-match.
                    _miss_a = bool(pd.isna(row.get("amount_a")))
                    _miss_b = bool(pd.isna(row.get("amount_b")))
                    if _miss_a or _miss_b:
                        rejection_breakdown["missing_amount"] += 1
                        _miss_side = "both sides" if (_miss_a and _miss_b) else (
                            str(row["_source_label_a"]) if _miss_a else str(row["_source_label_b"]))
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "canonical_transaction_id": canon_id,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "MISSING_AMOUNT",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": 0.0,
                            "explanation": (
                                f"Invalid record on canonical transaction ID '{canon_id}': "
                                f"missing financial amount on {_miss_side}. Amount-less records are excluded "
                                f"from amount-based matching."
                            ),
                            "recommended_action": "Supply a valid numeric amount for the record and re-run reconciliation.",
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
                                "amount_a": _safe_amt(row.get("amount_a")),
                                "amount_b": _safe_amt(row.get("amount_b")),
                                "amount_missing_a": bool(_miss_a),
                                "amount_missing_b": bool(_miss_b),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                        continue

                    # Currency Mismatch Check — never compare numerics across currencies.
                    if str(row["currency_a"]) != str(row["currency_b"]):
                        rejection_breakdown["currency_mismatch"] += 1
                        _fx = build_fx_evidence(_safe_amt(row.get("amount_a")), str(row["currency_a"]),
                                                _safe_amt(row.get("amount_b")), str(row["currency_b"]), fx_rates=fx_rates)
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
                                "amount_a": _safe_amt(row.get("amount_a")),
                                "amount_b": _safe_amt(row.get("amount_b")),
                                "original_amount": _safe_amt(row.get("amount_a")),
                                "original_currency": str(row["currency_a"]),
                                "counterpart_amount": _safe_amt(row.get("amount_b")),
                                "counterpart_currency": str(row["currency_b"]),
                                "exchange_rate": _fx.get("exchange_rate"),
                                "converted_amount": _fx.get("converted_amount"),
                                "conversion_source": _fx.get("conversion_source"),
                                "fx_status": _fx.get("fx_status"),
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

                    amt_a = _safe_amt(row.get("amount_a"))
                    amt_b = _safe_amt(row.get("amount_b"))
                    # Missing amounts already guarded above; this is defensive.
                    if amt_a is None or amt_b is None:
                        continue
                    net_a = _safe_amt(row.get("net_amount_a"))
                    net_b = _safe_amt(row.get("net_amount_b"))
                    net_a = net_a if net_a is not None else amt_a
                    net_b = net_b if net_b is not None else amt_b

                    gross_diff = round(abs(amt_a - amt_b), 2)
                    _cands = [round(abs(net_a - amt_b), 2), round(abs(amt_a - net_b), 2), round(abs(net_a - net_b), 2)]
                    net_diff_val = min(_cands)
                    # Best gross/net difference: prefer gross when within tolerance, else best net.
                    if gross_diff <= self.amount_tolerance:
                        best_diff, match_basis = gross_diff, "GROSS"
                    else:
                        best_diff, match_basis = net_diff_val, "NET"

                    if best_diff <= self.amount_tolerance:
                        strat = "EXACT_TRANSACTION_ID"
                        cat = "EXACT_MATCH" if (best_diff == 0.0 and days_diff == 0) else "TOLERANCE_MATCH"
                        conf = 100.0 if cat == "EXACT_MATCH" else 98.0
                        rule = "Pass 1: Primary Canonical Transaction ID Match"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule,
                                                   gross_diff=gross_diff, net_diff=net_diff_val, match_basis=match_basis)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    elif best_diff <= self.fee_tolerance:
                        strat = "EXACT_TRANSACTION_ID_FEE_DELTA"
                        cat = "TOLERANCE_MATCH"
                        conf = 95.0
                        rule = "Pass 1: Canonical Transaction ID Match with Fee Delta"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule,
                                                   gross_diff=gross_diff, net_diff=net_diff_val, match_basis=match_basis)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    else:
                        # Same transaction ID + amount difference -> AMOUNT_MISMATCH
                        # Do NOT automatically fuzzy-match a different transaction ID when an exact ID exists!
                        rejection_breakdown["amount_mismatch"] += 1
                        _aa1 = _safe_amt(row.get("amount_a"))
                        _ab1 = _safe_amt(row.get("amount_b"))
                        _rep1 = gross_diff if gross_diff is not None else 0.0
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "canonical_transaction_id": canon_id,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "AMOUNT_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": _rep1,
                            "explanation": (
                                f"Amount mismatch on canonical transaction ID '{canon_id}': "
                                f"{row['_source_label_a']} reports ${(_aa1 or 0.0):,.2f} vs "
                                f"{row['_source_label_b']} ${(_ab1 or 0.0):,.2f} (delta: ${(_rep1 or 0.0):,.2f})."
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
                                "amount_a": _aa1,
                                "amount_b": _ab1,
                                "gross_diff": gross_diff,
                                "net_diff": net_diff_val,
                                "date_a": str(row["iso_date_a"]),
                                "date_b": str(row["iso_date_b"]),
                                "counterpart_record_id": id_b,
                                "counterpart_amount": _ab1,
                                "counterpart_source": str(row["_source_label_b"]),
                                "amount_delta": _rep1,
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

                    # Missing-amount guard for Pass 2
                    if bool(pd.isna(row.get("amount_a"))) or bool(pd.isna(row.get("amount_b"))):
                        rejection_breakdown["missing_amount"] += 1
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "MISSING_AMOUNT",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": 0.0,
                            "explanation": (
                                f"Invalid record on reference '{ref}': missing financial amount. "
                                f"Amount-less records are excluded from amount-based matching."
                            ),
                            "recommended_action": "Supply a valid numeric amount and re-run reconciliation.",
                            "provenance": {
                                "document_id": str(row["_doc_id_a"]),
                                "filename": str(row["_doc_name_a"]),
                                "document_role": str(row.get("_doc_role_a", "TRANSACTIONS")),
                                "row_index": int(row["_row_idx_a"]),
                                "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                                "raw_data": row["_raw_data_a"],
                            },
                            "evidence": {
                                "record_id_a": id_a, "record_id_b": id_b, "reference": ref,
                                "amount_a": _safe_amt(row.get("amount_a")),
                                "amount_b": _safe_amt(row.get("amount_b")),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                        continue

                    # Currency Mismatch Check
                    if str(row["currency_a"]) != str(row["currency_b"]):
                        rejection_breakdown["currency_mismatch"] += 1
                        _fx2 = build_fx_evidence(_safe_amt(row.get("amount_a")), str(row["currency_a"]),
                                                 _safe_amt(row.get("amount_b")), str(row["currency_b"]), fx_rates=fx_rates)
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
                                "amount_a": _safe_amt(row.get("amount_a")),
                                "amount_b": _safe_amt(row.get("amount_b")),
                                "original_amount": _safe_amt(row.get("amount_a")),
                                "original_currency": str(row["currency_a"]),
                                "exchange_rate": _fx2.get("exchange_rate"),
                                "converted_amount": _fx2.get("converted_amount"),
                                "conversion_source": _fx2.get("conversion_source"),
                                "fx_status": _fx2.get("fx_status"),
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

                    amt_a = _safe_amt(row.get("amount_a"))
                    amt_b = _safe_amt(row.get("amount_b"))
                    if amt_a is None or amt_b is None:
                        continue
                    net_a = _safe_amt(row.get("net_amount_a"))
                    net_b = _safe_amt(row.get("net_amount_b"))
                    net_a = net_a if net_a is not None else amt_a
                    net_b = net_b if net_b is not None else amt_b

                    gross_diff = round(abs(amt_a - amt_b), 2)
                    net_diff_val = min(
                        round(abs(net_a - amt_b), 2),
                        round(abs(amt_a - net_b), 2),
                        round(abs(net_a - net_b), 2)
                    )
                    if gross_diff <= self.amount_tolerance:
                        best_diff, match_basis = gross_diff, "GROSS"
                    else:
                        best_diff, match_basis = net_diff_val, "NET"

                    if best_diff <= self.amount_tolerance:
                        strat = "FALLBACK_EXACT_REFERENCE"
                        cat = "EXACT_MATCH" if (best_diff == 0.0 and days_diff == 0) else "TOLERANCE_MATCH"
                        conf = 95.0
                        rule = "Pass 2: Fallback Exact Reference Match"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule,
                                                   gross_diff=gross_diff, net_diff=net_diff_val, match_basis=match_basis)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    elif best_diff <= self.fee_tolerance:
                        strat = "FALLBACK_REFERENCE_FEE_DELTA"
                        cat = "TOLERANCE_MATCH"
                        conf = 90.0
                        rule = "Pass 2: Fallback Reference Match with Fee Delta"
                        match_entry = _build_match(row, strat, cat, conf, best_diff, days_diff, rule,
                                                   gross_diff=gross_diff, net_diff=net_diff_val, match_basis=match_basis)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                    else:
                        # Reference match with amount difference -> AMOUNT_MISMATCH
                        rejection_breakdown["amount_mismatch"] += 1
                        _rep_diff = gross_diff if gross_diff is not None else (best_diff or 0.0)
                        _aa = _safe_amt(row.get("amount_a"))
                        _ab = _safe_amt(row.get("amount_b"))
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "source": str(row["_source_label_a"]),
                            "reason_code": "AMOUNT_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": _rep_diff,
                            "explanation": (
                                f"Amount mismatch on reference '{ref}': {row['_source_label_a']} reports "
                                f"${(_aa or 0.0):,.2f} vs {row['_source_label_b']} ${(_ab or 0.0):,.2f} (delta: ${(_rep_diff or 0.0):,.2f})."
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
                                "counterpart_amount": _ab,
                                "counterpart_source": str(row["_source_label_b"]),
                                "amount_a": _aa,
                                "amount_b": _ab,
                                "gross_diff": gross_diff,
                                "net_diff": net_diff_val,
                                "amount_delta": _rep_diff,
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)

        # ── PASS 3: FALLBACK 2 - AMOUNT (GROSS OR NET) + COMPATIBLE DATE WINDOW (±3 DAYS) ──
        # Currency-guarded: cross-currency pairs NEVER match; they emit CURRENCY_MISMATCH.
        # Missing-amount records are excluded (MISSING_AMOUNT) and never merge-matched.
        # Net-aware: gross merge + net merge candidates are unioned; best gross/net diff wins.
        unmatched_df_a = df_a[~df_a["transaction_id"].isin(matched_a)]
        unmatched_df_b = df_b[~df_b["transaction_id"].isin(matched_b)]
        # Exclude amount-less records from amount-based matching entirely.
        unmatched_df_a = unmatched_df_a[~unmatched_df_a["amount"].isna()]
        unmatched_df_b = unmatched_df_b[~unmatched_df_b["amount"].isna()]

        if len(unmatched_df_a) > 0 and len(unmatched_df_b) > 0:
            # Gross candidates: exact gross amount equality.
            merged_gross = pd.merge(unmatched_df_a, unmatched_df_b, on="amount", suffixes=("_a", "_b"))
            # Net candidates: net_amount equality (rounded to cents) with distinct IDs.
            _a_net = unmatched_df_a.copy()
            _b_net = unmatched_df_b.copy()
            _a_net["_net_key"] = _a_net["net_amount"].round(2)
            _b_net["_net_key"] = _b_net["net_amount"].round(2)
            _a_net = _a_net[~_a_net["_net_key"].isna()]
            _b_net = _b_net[~_b_net["_net_key"].isna()]
            if len(_a_net) > 0 and len(_b_net) > 0:
                merged_net = pd.merge(_a_net, _b_net, on="_net_key", suffixes=("_a", "_b"))
                # Drop net pairs already covered by gross equality to avoid double-counting.
                if len(merged_net) > 0 and len(merged_gross) > 0:
                    _gross_pairs = set(zip(merged_gross["transaction_id_a"], merged_gross["transaction_id_b"]))
                    merged_net = merged_net[~merged_net.apply(
                        lambda r: (str(r["transaction_id_a"]), str(r["transaction_id_b"])) in _gross_pairs, axis=1)]
                merged_net["gross_diff"] = (merged_net["amount_a"] - merged_net["amount_b"]).abs().round(2)
                merged_net["net_diff"] = (merged_net["net_amount_a"] - merged_net["net_amount_b"]).abs().round(2)
                merged_net["_match_basis_hint"] = "NET"
            else:
                merged_net = pd.DataFrame()
            if len(merged_gross) > 0:
                merged_gross["gross_diff"] = 0.0
                # net diff for gross pairs (may be nonzero when fees differ)
                try:
                    merged_gross["net_diff"] = (merged_gross["net_amount_a"] - merged_gross["net_amount_b"]).abs().round(2)
                except Exception:
                    merged_gross["net_diff"] = 0.0
                merged_gross["_match_basis_hint"] = "GROSS"
            if len(merged_net) > 0 and len(merged_gross) > 0:
                # Align columns before concat.
                for _c in ["gross_diff", "net_diff", "_match_basis_hint"]:
                    if _c not in merged_gross.columns:
                        merged_gross[_c] = None
                    if _c not in merged_net.columns:
                        merged_net[_c] = None
                merged_3 = pd.concat([merged_gross, merged_net], ignore_index=True, sort=False)
            elif len(merged_net) > 0:
                merged_3 = merged_net
            else:
                merged_3 = merged_gross
            total_candidate_pairs += len(merged_3)

            if len(merged_3) > 0:
                dt_a = merged_3["dt_date_a"]
                dt_b = merged_3["dt_date_b"]
                days_diff_3 = np.abs((dt_a - dt_b).dt.days)
                date_window_mask = (days_diff_3 <= self.date_window_days)
                rejection_breakdown["date_mismatch"] += int(np.sum(~date_window_mask))

                pass3_candidates = merged_3[date_window_mask].copy()
                if len(pass3_candidates) > 0:
                    cand_counts_a = pass3_candidates["transaction_id_a"].value_counts()
                    cand_counts_b = pass3_candidates["transaction_id_b"].value_counts()

                    for _, row in pass3_candidates.iterrows():
                        id_a = str(row["transaction_id_a"])
                        id_b = str(row["transaction_id_b"])

                        if id_a in matched_a or id_b in matched_b:
                            continue

                        # Currency guard: prevent cross-currency matches, emit CURRENCY_MISMATCH.
                        if str(row["currency_a"]) != str(row["currency_b"]):
                            rejection_breakdown["currency_mismatch"] += 1
                            _fx3 = build_fx_evidence(_safe_amt(row.get("amount_a")), str(row["currency_a"]),
                                                     _safe_amt(row.get("amount_b")), str(row["currency_b"]), fx_rates=fx_rates)
                            pass_exceptions.append({
                                "id": f"exc_{uuid.uuid4().hex[:10]}",
                                "record_id": id_a,
                                "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                                "source": str(row["_source_label_a"]),
                                "reason_code": "CURRENCY_MISMATCH",
                                "discrepancy_level": "MATERIAL",
                                "amount_discrepancy": 0.0,
                                "explanation": (
                                    f"Currency mismatch on amount/date candidate {id_a} ↔ {id_b}: "
                                    f"{row['currency_a']} vs {row['currency_b']}. Currency conversion required."
                                ),
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
                                    "record_id_a": id_a, "record_id_b": id_b,
                                    "matching_strategy": "FALLBACK_AMOUNT_DATE",
                                    "currency_a": str(row["currency_a"]), "currency_b": str(row["currency_b"]),
                                    "amount_a": _safe_amt(row.get("amount_a")), "amount_b": _safe_amt(row.get("amount_b")),
                                    "original_amount": _safe_amt(row.get("amount_a")),
                                    "original_currency": str(row["currency_a"]),
                                    "exchange_rate": _fx3.get("exchange_rate"),
                                    "converted_amount": _fx3.get("converted_amount"),
                                    "conversion_source": _fx3.get("conversion_source"),
                                    "fx_status": _fx3.get("fx_status"),
                                },
                            })
                            matched_a.add(id_a)
                            matched_b.add(id_b)
                            continue

                        # If multiple candidates remain: AMBIGUOUS_CANDIDATE_CONFLICT (never arbitrary matches[0])
                        if cand_counts_a.get(id_a, 0) > 1 or cand_counts_b.get(id_b, 0) > 1:
                            rejection_breakdown["ambiguous_candidate_conflict"] += 1
                            _amt3 = _safe_amt(row.get("amount_a"))
                            pass_exceptions.append({
                                "id": f"exc_{uuid.uuid4().hex[:10]}",
                                "record_id": id_a,
                                "source": str(row["_source_label_a"]),
                                "reason_code": "AMBIGUOUS_CANDIDATE_CONFLICT",
                                "discrepancy_level": "MATERIAL",
                                "amount_discrepancy": _amt3 if _amt3 is not None else 0.0,
                                "explanation": f"Ambiguous candidate conflict: multiple transactions match amount ${(_amt3 or 0.0):,.2f} within date window.",
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
                                    "amount": _amt3,
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
                        _g3 = _safe_amt(row.get("gross_diff"))
                        _n3 = _safe_amt(row.get("net_diff"))
                        _hint3 = str(row.get("_match_basis_hint") or "GROSS")
                        if _hint3 == "NET" and _n3 is not None:
                            diff_val = _n3
                            match_basis3 = "NET"
                        else:
                            diff_val = _g3 if _g3 is not None else 0.0
                            match_basis3 = "GROSS"
                        rule = "Pass 3: Fallback Amount + Date Window Match"
                        match_entry = _build_match(row, "FALLBACK_AMOUNT_DATE", "FUZZY_MATCH", score, diff_val, d_diff, rule,
                                                   gross_diff=_g3, net_diff=_n3, match_basis=match_basis3)
                        matches.append(match_entry)
                        matched_a.add(id_a)
                        matched_b.add(id_b)

        # ── PASS 4: FALLBACK 3 - ENTITY NAME MATCH + DATE WINDOW ──
        # Currency-guarded and net-aware: best gross/net difference must be within tolerance.
        unmatched_df_a = df_a[~df_a["transaction_id"].isin(matched_a)]
        unmatched_df_b = df_b[~df_b["transaction_id"].isin(matched_b)]
        unmatched_df_a = unmatched_df_a[~unmatched_df_a["amount"].isna()]
        unmatched_df_b = unmatched_df_b[~unmatched_df_b["amount"].isna()]

        if len(unmatched_df_a) > 0 and len(unmatched_df_b) > 0:
            merged_4 = pd.merge(
                unmatched_df_a, unmatched_df_b,
                on="clean_entity",
                suffixes=("_a", "_b")
            )
            total_candidate_pairs += len(merged_4)

            if len(merged_4) > 0:
                # Compute gross and net diffs vectorized (NaN-safe).
                _g4 = (merged_4["amount_a"] - merged_4["amount_b"]).abs().round(2)
                _n4a = (merged_4["net_amount_a"] - merged_4["amount_b"]).abs().round(2)
                _n4b = (merged_4["amount_a"] - merged_4["net_amount_b"]).abs().round(2)
                _n4c = (merged_4["net_amount_a"] - merged_4["net_amount_b"]).abs().round(2)
                merged_4["_gross_diff"] = _g4
                merged_4["_net_diff"] = pd.concat([_n4a, _n4b, _n4c], axis=1).min(axis=1).round(2)
                merged_4["_best_diff"] = pd.concat([_g4, merged_4["_net_diff"]], axis=1).min(axis=1)
                dt_a = merged_4["dt_date_a"]
                dt_b = merged_4["dt_date_b"]
                days_diff_4 = np.abs((dt_a - dt_b).dt.days)

                # Currency guard first: cross-currency entity pairs emit CURRENCY_MISMATCH.
                _fx_mask = (merged_4["currency_a"] != merged_4["currency_b"])
                _fx_rows = merged_4[_fx_mask & (days_diff_4 <= self.date_window_days)]
                for _, row in _fx_rows.iterrows():
                    id_a = str(row["transaction_id_a"])
                    id_b = str(row["transaction_id_b"])
                    if id_a in matched_a or id_b in matched_b:
                        continue
                    # Only emit when amounts would otherwise be plausible (best diff within fee tolerance).
                    try:
                        _bd = float(row["_best_diff"])
                    except Exception:
                        continue
                    if _bd <= self.fee_tolerance:
                        rejection_breakdown["currency_mismatch"] += 1
                        _fx4 = build_fx_evidence(_safe_amt(row.get("amount_a")), str(row["currency_a"]),
                                                 _safe_amt(row.get("amount_b")), str(row["currency_b"]), fx_rates=fx_rates)
                        pass_exceptions.append({
                            "id": f"exc_{uuid.uuid4().hex[:10]}",
                            "record_id": id_a,
                            "canonical_transaction_id": str(row.get("canonical_transaction_id_a") or id_a),
                            "source": str(row["_source_label_a"]),
                            "reason_code": "CURRENCY_MISMATCH",
                            "discrepancy_level": "MATERIAL",
                            "amount_discrepancy": 0.0,
                            "explanation": (
                                f"Currency mismatch on entity/date candidate {id_a} ↔ {id_b}: "
                                f"{row['currency_a']} vs {row['currency_b']}. Currency conversion required."
                            ),
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
                                "record_id_a": id_a, "record_id_b": id_b,
                                "matching_strategy": "FALLBACK_ENTITY_AMOUNT_DATE",
                                "currency_a": str(row["currency_a"]), "currency_b": str(row["currency_b"]),
                                "amount_a": _safe_amt(row.get("amount_a")), "amount_b": _safe_amt(row.get("amount_b")),
                                "original_amount": _safe_amt(row.get("amount_a")),
                                "original_currency": str(row["currency_a"]),
                                "exchange_rate": _fx4.get("exchange_rate"),
                                "converted_amount": _fx4.get("converted_amount"),
                                "conversion_source": _fx4.get("conversion_source"),
                                "fx_status": _fx4.get("fx_status"),
                            },
                        })
                        matched_a.add(id_a)
                        matched_b.add(id_b)
                # Exclude cross-currency rows from further Pass 4 matching.
                merged_4 = merged_4[~_fx_mask]

                if len(merged_4) > 0:
                    dt_a = merged_4["dt_date_a"]
                    dt_b = merged_4["dt_date_b"]
                    days_diff_4 = np.abs((dt_a - dt_b).dt.days)
                    pass4_mask = (merged_4["_best_diff"] <= self.fee_tolerance) & (days_diff_4 <= self.date_window_days)
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
                            _g = float(row["_gross_diff"]) if pd.notna(row["_gross_diff"]) else 0.0
                            _n = float(row["_net_diff"]) if pd.notna(row["_net_diff"]) else _g
                            _best = float(row["_best_diff"]) if pd.notna(row["_best_diff"]) else _g
                            _basis = "GROSS" if _g <= self.amount_tolerance else "NET"
                            diff_val = round(_best, 2)
                            rule = "Pass 4: Fallback Entity + Date Window Cluster Match"
                            match_entry = _build_match(row, "FALLBACK_ENTITY_AMOUNT_DATE", "FUZZY_MATCH", 78.0, diff_val, d_diff, rule,
                                                       gross_diff=round(_g, 2), net_diff=round(_n, 2), match_basis=_basis)
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
    # TWO-WAY SPLIT DETECTION (1:2 / 2:1)
    # ─────────────────────────────────────────────────────────────
    # Adopted from agent-for-accounting's `findPossibleSplits`: order-independent,
    # exactly-two groupings only, and a single shared consumed-pool across BOTH
    # directions so a row can never be claimed by two contradictory splits.

    def _detect_two_way_splits(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        matched_a: Set[str],
        matched_b: Set[str],
    ) -> Tuple[List[Dict[str, Any]], Set[str], Set[str]]:
        """
        Detect a single row on one side whose amount equals the SUM of exactly
        two rows on the other side (within amount tolerance and the date window).

        Returns (splits, split_used_a, split_used_b).
        """
        splits: List[Dict[str, Any]] = []
        used_a: Set[str] = set(matched_a)
        used_b: Set[str] = set(matched_b)

        def _available(df, used):
            sub = df[~df["transaction_id"].isin(used)]
            if "amount" in sub.columns:
                sub = sub[~sub["amount"].isna()]
            return sub

        rows_a = [r for _, r in _available(df_a, used_a).iterrows()]
        rows_b = [r for _, r in _available(df_b, used_b).iterrows()]

        def _amt(r) -> Optional[float]:
            try:
                v = float(r["amount"])
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    return None
                return v
            except Exception:
                return None

        def _date_ok(x, y) -> bool:
            dx, dy = x.get("dt_date"), y.get("dt_date")
            if pd.isna(dx) or pd.isna(dy):
                return True  # undated rows cannot be rejected on date
            try:
                return abs((dx - dy).days) <= self.date_window_days
            except Exception:
                return True

        # candidate tuples: (diff, single_side, single_row, g1_row, g2_row)
        candidates = []

        def _consider(single_side, single_rows, group_rows):
            for s in single_rows:
                s_amt = _amt(s)
                if s_amt is None:
                    continue
                for i in range(len(group_rows)):
                    for j in range(i + 1, len(group_rows)):
                        g1, g2 = group_rows[i], group_rows[j]
                        if not (_date_ok(s, g1) and _date_ok(s, g2)):
                            continue
                        a1, a2 = _amt(g1), _amt(g2)
                        if a1 is None or a2 is None:
                            continue
                        diff = round(abs((a1 + a2) - s_amt), 2)
                        if diff <= self.amount_tolerance:
                            candidates.append((diff, single_side, s, g1, g2))

        _consider("a", rows_a, rows_b)  # 1 primary : 2 counterpart
        _consider("b", rows_b, rows_a)  # 2 primary : 1 counterpart

        # Order-independent sort: by diff, then by sorted content key so swapping
        # bank/ledger yields identical selections.
        def _sort_key(c):
            diff, single_side, s, g1, g2 = c
            ids = sorted([str(s["transaction_id"]), str(g1["transaction_id"]), str(g2["transaction_id"])])
            return (diff, "~".join(ids))

        candidates.sort(key=_sort_key)

        for diff, single_side, s, g1, g2 in candidates:
            s_id = str(s["transaction_id"])
            g1_id = str(g1["transaction_id"])
            g2_id = str(g2["transaction_id"])
            single_set = used_a if single_side == "a" else used_b
            group_set = used_b if single_side == "a" else used_a
            if s_id in single_set or g1_id in group_set or g2_id in group_set:
                continue
            single_set.add(s_id)
            group_set.add(g1_id)
            group_set.add(g2_id)

            def _meta(r):
                return {
                    "record_id": str(r["transaction_id"]),
                    "amount": _amt(r),
                    "date": str(r.get("iso_date")),
                    "source": str(r.get("_source_label", "")),
                    "document_id": str(r.get("_doc_id", "")),
                    "row_index": int(r.get("_row_idx", -1)),
                }

            sum_amt = round((_amt(g1) or 0.0) + (_amt(g2) or 0.0), 2)
            strategy = "ONE_TO_TWO_SPLIT" if single_side == "a" else "TWO_TO_ONE_SPLIT"
            splits.append({
                "id": f"split_{uuid.uuid4().hex[:10]}",
                "record_id": s_id,
                "match_category": "SPLIT_MATCH",
                "matching_strategy": strategy,
                "confidence_score": 80.0,
                "discrepancy_level": "NORMAL" if diff <= 1.0 else "MATERIAL",
                "side": single_side,
                "single": _meta(s),
                "group": [_meta(g1), _meta(g2)],
                "sum_amount": sum_amt,
                "amount_diff": diff,
                "explanation": (
                    f"Single {strategy.split('_')[0].lower()}-side record {s_id} "
                    f"(${(_amt(s) or 0.0):,.2f}) equals the sum of two counterpart "
                    f"records ({g1_id} ${(_amt(g1) or 0.0):,.2f} + {g2_id} ${(_amt(g2) or 0.0):,.2f} = ${sum_amt:,.2f}); "
                    f"difference ${diff:,.2f} within tolerance ${self.amount_tolerance:.2f}. Manual confirmation recommended."
                ),
                "evidence": {
                    "single": _meta(s),
                    "group": [_meta(g1), _meta(g2)],
                    "sum_amount": sum_amt,
                    "amount_diff": diff,
                },
            })

        return splits, used_a - set(matched_a), used_b - set(matched_b)

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

        def _exc_amt(v: Any) -> Optional[float]:
            try:
                f = float(v)
                if math.isnan(f) or math.isinf(f):
                    return None
                return f
            except Exception:
                return None

        def _exc_amt_str(v: Any) -> str:
            f = _exc_amt(v)
            return f"${f:,.2f}" if f is not None else "N/A (missing amount)"

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
            _amt_missing_a = bool(pd.isna(row.get("amount")))

            if _amt_missing_a:
                _raw = row.get("_raw_data") if isinstance(row.get("_raw_data"), dict) else {}
                exceptions.append({
                    "id": f"exc_{uuid.uuid4().hex[:10]}",
                    "record_id": rec_id,
                    "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                    "source": row["_source_label"],
                    "reason_code": "MISSING_AMOUNT",
                    "discrepancy_level": "MATERIAL",
                    "amount_discrepancy": 0.0,
                    "explanation": (
                        f"Invalid record {rec_id}: missing financial amount. "
                        f"Amount-less records are excluded from amount-based matching."
                    ),
                    "recommended_action": "Supply a valid numeric amount for the record and re-run reconciliation.",
                    "provenance": {
                        "document_id": row["_doc_id"],
                        "filename": row["_doc_name"],
                        "document_role": str(row.get("_doc_role", "TRANSACTIONS")),
                        "row_index": int(row["_row_idx"]),
                        "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                        "member_id": row.get("member_id"),
                        "raw_data": row["_raw_data"],
                    },
                    "evidence": {
                        "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                        "member_id": row.get("member_id"),
                        "document_role": str(row.get("_doc_role", "TRANSACTIONS")),
                        "row_index": int(row["_row_idx"]),
                        "reference": row["raw_reference_id"],
                        "date": row["iso_date"],
                        "entity": row["raw_entity"],
                        "amount": None,
                        "amount_missing": True,
                        "record_id_a": rec_id,
                        "amount_a": None,
                    },
                })
                continue

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
            if bool(pd.isna(row.get("amount"))):
                exceptions.append({
                    "id": f"exc_{uuid.uuid4().hex[:10]}",
                    "record_id": rec_id,
                    "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                    "source": row["_source_label"],
                    "reason_code": "MISSING_AMOUNT",
                    "discrepancy_level": "MATERIAL",
                    "amount_discrepancy": 0.0,
                    "explanation": (
                        f"Invalid record {rec_id}: missing financial amount. "
                        f"Amount-less records are excluded from amount-based matching."
                    ),
                    "recommended_action": "Supply a valid numeric amount for the record and re-run reconciliation.",
                    "provenance": {
                        "document_id": row["_doc_id"],
                        "filename": row["_doc_name"],
                        "document_role": str(row.get("_doc_role", "SETTLEMENTS")),
                        "row_index": int(row["_row_idx"]),
                        "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                        "member_id": row.get("member_id"),
                        "raw_data": row["_raw_data"],
                    },
                    "evidence": {
                        "canonical_transaction_id": str(row.get("canonical_transaction_id") or rec_id),
                        "member_id": row.get("member_id"),
                        "document_role": str(row.get("_doc_role", "SETTLEMENTS")),
                        "row_index": int(row["_row_idx"]),
                        "reference": row["raw_reference_id"],
                        "date": row["iso_date"],
                        "entity": row["raw_entity"],
                        "amount": None,
                        "amount_missing": True,
                        "record_id_b": rec_id,
                        "amount_b": None,
                    },
                })
                continue

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
