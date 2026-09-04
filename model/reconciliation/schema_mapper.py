"""
Deterministic Schema Inspector and Semantic Column Mapper.
Inspects table schemas of all uploaded financial documents and automatically maps
equivalent columns even when naming conventions differ across sources:
    - transaction_id / txn_id / record_id / payout_id
    - amount / transaction_amount / debit_amount / net_amount / gross_amount
    - date / transaction_date / value_date / posting_date / settlement_date
    - description / narration / memo / particulars
    - reference_id / reference / ref_no / order_ref / invoice / utr
    - entity / vendor / merchant / counterparty / payee
    - currency / curr / ccy
    - tax_amount / tax_rate / taxable_amount
"""

import re
import math
from typing import Dict, List, Any, Optional, Tuple, Set
import pandas as pd
from pydantic import BaseModel, Field


def normalize_canonical_transaction_id(val: Any) -> str:
    """
    Normalizes a transaction ID into a canonical business identifier:
    - String conversion
    - Trim whitespace
    - Normalize uppercase
    - Strip surrounding quotes or brackets
    - Preserve meaningful internal separators ('-', '_', ':') without destroying identifiers
    """
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if s.lower() in ["nan", "none", "null", "n/a", ""]:
        return ""
    # Strip enclosing quotes or brackets
    s = s.strip("'\"`()[]{}")
    # Normalize whitespace
    s = re.sub(r'\s+', ' ', s)
    return s.upper()


# ─────────────────────────────────────────────────────────────
# SYNONYM DICTIONARIES FOR SEMANTIC FINANCIAL COLUMNS
# ─────────────────────────────────────────────────────────────

SEMANTIC_COLUMN_CANDIDATES: Dict[str, List[str]] = {
    "transaction_id": [
        "transaction_id", "txn_id", "payment_id", "record_id",
        "payout_id", "settlement_id", "order_id", "entry_id", "invoice_id",
        "payment_reference", "txn_number", "transaction_number", "trans_id",
        "unique_id", "item_id", "bill_id", "voucher_no", "id",
        "external_ref", "external_reference", "order_num", "order_no",
    ],
    "member_id": [
        "member_id", "member", "customer_id", "user_id", "client_id",
        "account_id", "subscriber_id", "sub_id", "account_no", "account_number",
        "wallet_id", "payer_id", "payee_id",
    ],
    "reference_id": [
        "reference_id", "reference", "ref_no", "ref_num", "order_ref",
        "invoice", "inv_no", "invoice_no", "invoice_number", "utr",
        "utr_number", "cheque_no", "check_no", "ext_ref", "external_id",
        "external_ref", "external_reference", "ext_reference", "txn_ref",
        "client_reference", "common_ref", "order_number", "bill_ref",
    ],
    "amount": [
        "amount", "transaction_amount", "net_amount", "gross_amount",
        "total_amount", "net_payout", "settled_amount", "payout_amount",
        "gross_payout", "bill_amount", "debit_amount", "credit_amount",
        "paid_amount", "amount_paid", "total", "value", "payment_amount",
        "trans_amount", "line_amount", "sum", "amt", "debit", "credit",
    ],
    "date": [
        "date", "transaction_date", "txn_date", "value_date", "posting_date",
        "settlement_date", "invoice_date", "payout_date", "created_at",
        "timestamp", "effective_date", "trans_date", "payment_date",
        "settled_at", "paid_at", "transacted_at", "booking_date",
    ],
    "entity": [
        "entity", "vendor", "merchant", "merchant_entity", "counterparty",
        "payee", "payer", "company", "name", "client", "customer",
        "vendor_name", "merchant_name", "client_name", "account_name",
        "beneficiary", "party_name",
    ],
    "description": [
        "description", "narration", "memo", "particulars", "details",
        "remarks", "note", "purpose", "line_item", "desc", "comments",
    ],
    "currency": [
        "currency", "curr", "ccy", "currency_code", "iso_currency",
    ],
    "tax_amount": [
        "tax_amount", "tax", "gst", "vat", "tds", "tax_deducted",
        "sales_tax", "withholding_tax", "gst_amount", "vat_amount",
    ],
    "tax_rate": [
        "tax_rate", "rate", "gst_rate", "vat_rate", "tax_pct", "rate_pct",
    ],
    "taxable_amount": [
        "taxable_amount", "taxable_base", "subtotal", "base_amount",
        "pre_tax_amount", "net_taxable",
    ],
    "fee_amount": [
        "fee", "fees", "fee_amount", "processing_fee", "interchange",
        "platform_fee", "commission", "service_charge",
        "gateway_fee", "mdr", "mdr_fee", "fees_deducted",
        "transaction_fee", "gateway_charge", "gateway_charges",
        "processing_charge", "processing_charges", "service_fee",
        "convenience_fee", "payment_fee", "settlement_fee",
        "deduction", "deductions", "fee_deducted",
    ],
    "refund_amount": [
        "refund", "refund_amount", "return_amount", "reversal",
        "refund_fee", "refunded_amount", "return", "returns",
        "credit_note_amount", "reversal_amount",
    ],
    "chargeback_amount": [
        "chargeback", "chargeback_amount", "dispute_amount",
        "dispute", "dispute_fee", "chargeback_fee", "representment_amount",
    ],
}


def _normalize_col_name(name: str) -> str:
    """Normalize a column header: lowercase, alphanumeric and underscores only."""
    clean = re.sub(r'[\s\-\.\/\\]+', '_', str(name).strip().lower())
    clean = re.sub(r'[^a-z0-9_]', '', clean)
    return clean.strip('_')


class DocumentSchema(BaseModel):
    """Detected schema profile for a single document."""
    document_id: str
    filename: str
    source_label: str
    row_count: int
    raw_columns: List[str]
    normalized_columns: List[str]
    mapped_columns: Dict[str, str] = Field(default_factory=dict)
    unmapped_columns: List[str] = Field(default_factory=list)
    is_valid: bool = True
    missing_required_fields: List[str] = Field(default_factory=list)
    sample_values: Dict[str, Any] = Field(default_factory=dict)


class SchemaMappingResult(BaseModel):
    """Aggregate result of schema detection and column mapping across all documents."""
    documents_inspected: int
    schemas: Dict[str, DocumentSchema]
    all_valid: bool
    summary: Dict[str, Any]
    diagnostics: List[str] = Field(default_factory=list)


class SchemaMapper:
    """
    Deterministic schema inspector and semantic column mapper.
    Operates on pandas DataFrames with strict provenance tracking.
    """

    def __init__(self, candidates: Optional[Dict[str, List[str]]] = None):
        self.candidates = candidates or SEMANTIC_COLUMN_CANDIDATES

    def _select_best_transaction_id(
        self, df: pd.DataFrame, raw_cols: List[str], used_raw_cols: Set[str], norm_to_raw: Dict[str, str]
    ) -> Optional[str]:
        """
        Identify the optimal canonical transaction identifier using:
        1. Column naming priority (transaction_id > txn_id > payment_id > record_id > id)
        2. High uniqueness ratio (transaction IDs are unique, unlike member IDs)
        3. High non-null ratio
        4. Strict exclusion of member/account/customer grouping columns
        """
        n_rows = len(df)
        best_col = None
        best_score = -1.0

        for raw_c in raw_cols:
            if raw_c in used_raw_cols:
                continue
            norm_c = _normalize_col_name(raw_c)
            # Never pick member/grouping columns as transaction_id
            if any(k in norm_c for k in ["member", "customer", "client_id", "user_id", "account_id", "account_no", "subscriber"]):
                continue

            # Never pick financial amount, balance, fee, tax, or date columns as transaction_id
            if any(k in norm_c for k in ["amount", "net_", "_net", "gross", "total", "fee", "tax", "balance", "debit", "credit", "rate", "sum", "date", "time"]):
                continue

            # If strictly floating point numeric, it's financial currency/amount, not a transaction identifier
            if pd.api.types.is_float_dtype(df[raw_c]):
                continue

            # Base name score
            name_score = 0.0
            if norm_c in ["transaction_id", "txn_id", "payment_id", "payout_id", "settlement_id", "record_id"]:
                name_score = 100.0
            elif norm_c in ["reference_id", "order_id", "payment_reference", "txn_number", "trans_id", "unique_id", "entry_id", "invoice_id"]:
                name_score = 80.0
            elif norm_c == "id":
                name_score = 60.0
            elif any(k in norm_c for k in ["txn", "trans", "payment", "payout", "order"]):
                name_score = 40.0
            elif "id" in norm_c or "ref" in norm_c:
                name_score = 20.0
            else:
                continue

            # Uniqueness and non-null metrics
            if n_rows > 0:
                non_null_count = int(df[raw_c].notnull().sum())
                non_null_ratio = non_null_count / n_rows
                unique_count = int(df[raw_c].nunique(dropna=True))
                uniqueness_ratio = unique_count / max(non_null_count, 1)
            else:
                non_null_ratio = 1.0
                uniqueness_ratio = 1.0

            total_score = name_score + (uniqueness_ratio * 30.0) + (non_null_ratio * 10.0)
            if total_score > best_score:
                best_score = total_score
                best_col = raw_c

        return best_col

    def inspect_and_map_dataframe(
        self,
        df: pd.DataFrame,
        document_id: str,
        filename: str,
        source_label: Optional[str] = None,
    ) -> DocumentSchema:
        """
        Inspect the schema of a single document's DataFrame and map semantically equivalent columns.
        """
        source_label = source_label or filename
        raw_cols = [str(c) for c in df.columns]
        norm_to_raw = {_normalize_col_name(c): c for c in raw_cols}
        norm_cols = list(norm_to_raw.keys())

        mapped_fields: Dict[str, str] = {}
        used_raw_cols: Set[str] = set()

        # Step 0: Identify canonical transaction identifier with high uniqueness & member exclusion
        best_txn_col = self._select_best_transaction_id(df, raw_cols, used_raw_cols, norm_to_raw)
        if best_txn_col:
            mapped_fields["transaction_id"] = best_txn_col
            used_raw_cols.add(best_txn_col)

        # Step 1: Exact matches against candidate lists
        for semantic_field, candidate_names in self.candidates.items():
            if semantic_field in mapped_fields:
                continue

            # Check normalized names
            for cand in candidate_names:
                cand_norm = _normalize_col_name(cand)
                if cand_norm in norm_to_raw:
                    raw_col = norm_to_raw[cand_norm]
                    if raw_col not in used_raw_cols:
                        # Extra guard: do not assign member/customer columns to transaction_id
                        if semantic_field == "transaction_id" and any(k in cand_norm for k in ["member", "customer", "user", "account"]):
                            continue
                        mapped_fields[semantic_field] = raw_col
                        used_raw_cols.add(raw_col)
                        break

        # Step 2: Substring token matching for remaining unmapped fields
        for semantic_field, candidate_names in self.candidates.items():
            if semantic_field in mapped_fields:
                continue

            for norm_c in norm_cols:
                raw_col = norm_to_raw[norm_c]
                if raw_col in used_raw_cols:
                    continue

                for cand in candidate_names:
                    cand_norm = _normalize_col_name(cand)
                    # Match if candidate is an exact token or prefix/suffix in column name
                    if f"_{cand_norm}" in f"_{norm_c}_" or f"_{norm_c}" in f"_{cand_norm}_":
                        mapped_fields[semantic_field] = raw_col
                        used_raw_cols.add(raw_col)
                        break
                if semantic_field in mapped_fields:
                    break

        # Step 3: Content-based heuristic fallbacks for required fields
        # If 'amount' is still unmapped, check if any column is numeric with monetary values
        if "amount" not in mapped_fields:
            for c in raw_cols:
                if c in used_raw_cols:
                    continue
                if pd.api.types.is_numeric_dtype(df[c]):
                    # Check if variance is non-zero
                    if df[c].abs().mean() > 0:
                        mapped_fields["amount"] = c
                        used_raw_cols.add(c)
                        break

        # If 'date' is still unmapped, check if any column parses as dates
        if "date" not in mapped_fields:
            for c in raw_cols:
                if c in used_raw_cols:
                    continue
                try:
                    # Test parsing 5 non-null rows
                    sample_dates = df[c].dropna().head(5)
                    if len(sample_dates) > 0:
                        pd.to_datetime(sample_dates, errors="raise")
                        mapped_fields["date"] = c
                        used_raw_cols.add(c)
                        break
                except Exception:
                    continue

        unmapped = [c for c in raw_cols if c not in used_raw_cols]

        # Validation: Required fields are amount and at least one identifier or date
        missing_required = []
        if "amount" not in mapped_fields:
            missing_required.append("amount")
        if "transaction_id" not in mapped_fields and "reference_id" not in mapped_fields and "date" not in mapped_fields:
            missing_required.append("transaction_id_or_reference_or_date")

        is_valid = len(missing_required) == 0

        # Extract sample values (first valid row) for transparency
        sample_vals: Dict[str, Any] = {}
        if len(df) > 0:
            first_row = df.iloc[0].to_dict()
            for k, v in first_row.items():
                if pd.isna(v):
                    sample_vals[str(k)] = None
                else:
                    sample_vals[str(k)] = str(v)[:64]

        return DocumentSchema(
            document_id=document_id,
            filename=filename,
            source_label=source_label,
            row_count=len(df),
            raw_columns=raw_cols,
            normalized_columns=norm_cols,
            mapped_columns=mapped_fields,
            unmapped_columns=unmapped,
            is_valid=is_valid,
            missing_required_fields=missing_required,
            sample_values=sample_vals,
        )

    def inspect_and_map_all(
        self,
        documents: List[Tuple[pd.DataFrame, str, str, str]],  # (df, doc_id, filename, source_label)
    ) -> SchemaMappingResult:
        """
        Inspect all uploaded documents in the thread and return aggregate schema profiles.
        """
        schemas: Dict[str, DocumentSchema] = {}
        diagnostics: List[str] = []
        all_valid = True

        for df, doc_id, filename, source_label in documents:
            schema = self.inspect_and_map_dataframe(
                df=df,
                document_id=doc_id,
                filename=filename,
                source_label=source_label,
            )
            schemas[doc_id] = schema
            if not schema.is_valid:
                all_valid = False
                diag_msg = (
                    f"Document '{filename}' ({doc_id}) failed semantic mapping: "
                    f"missing required fields {schema.missing_required_fields}."
                )
                diagnostics.append(diag_msg)

        summary = {
            "total_documents": len(documents),
            "valid_documents": sum(1 for s in schemas.values() if s.is_valid),
            "invalid_documents": sum(1 for s in schemas.values() if not s.is_valid),
            "mappings_per_document": {
                doc_id: s.mapped_columns for doc_id, s in schemas.items()
            },
        }

        return SchemaMappingResult(
            documents_inspected=len(documents),
            schemas=schemas,
            all_valid=all_valid,
            summary=summary,
            diagnostics=diagnostics,
        )


schema_mapper = SchemaMapper()
