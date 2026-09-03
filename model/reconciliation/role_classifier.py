"""
Deterministic Document Role Classifier.
Classifies arbitrary financial documents into domain roles:
    - TRANSACTION: internal orders, sales, user transactions
    - SETTLEMENT: payment gateway settlements, processing batches
    - FEE: gateway MDR, processing fee schedules, interchange
    - REFUND: return orders, reversal transactions
    - CHARGEBACK: payment disputes, chargeback notices
    - TAX: statutory GST, VAT, TDS, withholding reports
    - BANK_STATEMENT: bank account debits/credits, wire statements
    - LEDGER: accounting general ledger, journal accruals
    - INVOICE: vendor bills, billing invoices
    - PAYOUT: merchant disbursements, vendor payouts
    - UNKNOWN: when confidence is insufficient (never force an incorrect role)

Uses multi-signal analysis:
1. Column names and semantic financial tokens
2. Value distributions (signed amounts, debit/credit split)
3. Status column values (settled, disputed, refunded)
4. Document metadata and source labels
"""

import re
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set
import pandas as pd
from pydantic import BaseModel, Field


class DocumentRole(str, Enum):
    TRANSACTION = "TRANSACTION"
    SETTLEMENT = "SETTLEMENT"
    FEE = "FEE"
    REFUND = "REFUND"
    CHARGEBACK = "CHARGEBACK"
    TAX = "TAX"
    BANK_STATEMENT = "BANK_STATEMENT"
    LEDGER = "LEDGER"
    INVOICE = "INVOICE"
    PAYOUT = "PAYOUT"
    UNKNOWN = "UNKNOWN"


class DocumentRoleClassification(BaseModel):
    """Detailed role classification result for an uploaded financial document."""
    document_id: str
    filename: str
    document_role: DocumentRole
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    detected_columns: Dict[str, str] = Field(default_factory=dict)
    key_signals: List[str] = Field(default_factory=list)


# Vocabulary profiles for deterministic role scoring
ROLE_VOCABULARIES: Dict[DocumentRole, Dict[str, Any]] = {
    DocumentRole.TAX: {
        "required_any": ["tax_amount", "gst", "vat", "tds", "taxable_amount", "tax_rate", "withholding_tax", "sales_tax"],
        "supporting": ["hsn", "sac", "cgst", "sgst", "igst", "taxable_base", "pre_tax"],
        "weight": 35.0,
    },
    DocumentRole.FEE: {
        "required_any": ["fee", "fee_amount", "mdr", "interchange", "commission", "processing_fee", "gateway_fee", "convenience_fee"],
        "supporting": ["rate_pct", "percentage", "tier", "fixed_fee", "variable_fee"],
        "weight": 30.0,
    },
    DocumentRole.REFUND: {
        "required_any": ["refund_id", "refund_amount", "refund_date", "return_id", "reversal_id", "credit_note"],
        "supporting": ["original_txn_id", "refund_reason", "restocking_fee"],
        "weight": 30.0,
    },
    DocumentRole.CHARGEBACK: {
        "required_any": ["chargeback_id", "dispute_id", "case_id", "chargeback_amount", "dispute_amount"],
        "supporting": ["dispute_reason", "evidence_due", "representment", "arbitration", "card_brand"],
        "weight": 30.0,
    },
    DocumentRole.SETTLEMENT: {
        "required_any": ["settlement_id", "settled_amount", "payout_id", "batch_id", "settlement_date", "settled_at"],
        "supporting": ["gross_settlement", "net_settlement", "fees_deducted", "transfer_id", "gateway_ref", "payout"],
        "weight": 25.0,
    },
    DocumentRole.BANK_STATEMENT: {
        "required_any": ["bank_ref", "utr", "cheque_no", "chq_no", "value_date", "statement_id", "closing_balance", "balance"],
        "supporting": ["deposit", "withdrawal", "debit", "credit", "narration", "particulars", "bank"],
        "weight": 25.0,
    },
    DocumentRole.LEDGER: {
        "required_any": ["account_code", "gl_code", "journal_entry", "voucher_no", "voucher_id", "ledger_id", "general_ledger"],
        "supporting": ["posting_date", "debit_amount", "credit_amount", "accrual", "cost_center", "department"],
        "weight": 25.0,
    },
    DocumentRole.INVOICE: {
        "required_any": ["invoice_number", "invoice_id", "inv_no", "bill_id", "bill_number", "po_number"],
        "supporting": ["due_date", "bill_to", "ship_to", "item_description", "subtotal", "terms"],
        "weight": 20.0,
    },
    DocumentRole.PAYOUT: {
        "required_any": ["payout_id", "disbursement_id", "payout_amount", "recipient_id", "beneficiary"],
        "supporting": ["payout_status", "routing_number", "account_number", "payout_method"],
        "weight": 25.0,
    },
    DocumentRole.TRANSACTION: {
        "required_any": ["transaction_id", "txn_id", "order_id", "sale_id", "checkout_id", "payment_id"],
        "supporting": ["customer_id", "member_id", "user_id", "item_id", "product", "sku", "qty", "quantity"],
        "weight": 20.0,
    },
}


def _norm_col(c: Any) -> str:
    s = re.sub(r'[\s\-\.\/\\]+', '_', str(c).strip().lower())
    return re.sub(r'[^a-z0-9_]', '', s).strip('_')


class DocumentRoleClassifier:
    """Deterministic classifier for arbitrary uploaded financial files."""

    def classify_document(
        self,
        df: pd.DataFrame,
        document_id: str,
        filename: str,
        source_label: Optional[str] = None,
    ) -> DocumentRoleClassification:
        """
        Classify a single document's DataFrame into its domain role.
        """
        raw_cols = [str(c) for c in df.columns]
        norm_cols = [_norm_col(c) for c in raw_cols]

        # Signal tracking
        scores: Dict[DocumentRole, float] = {r: 0.0 for r in DocumentRole if r != DocumentRole.UNKNOWN}
        detected_col_map: Dict[DocumentRole, Dict[str, str]] = {r: {} for r in DocumentRole if r != DocumentRole.UNKNOWN}
        signals: Dict[DocumentRole, List[str]] = {r: [] for r in DocumentRole if r != DocumentRole.UNKNOWN}

        # 1. Column Semantic Vocabulary Matching
        for role, vocab in ROLE_VOCABULARIES.items():
            req_tokens = vocab["required_any"]
            sup_tokens = vocab["supporting"]

            # Required tokens
            for token in req_tokens:
                norm_token = _norm_col(token)
                for raw_c, nc in zip(raw_cols, norm_cols):
                    if norm_token == nc or f"_{norm_token}" in f"_{nc}_":
                        scores[role] += vocab["weight"]
                        detected_col_map[role][norm_token] = raw_c
                        signals[role].append(f"Header match: '{raw_c}' matches {role.value} vocabulary '{token}'")
                        break

            # Supporting tokens
            for token in sup_tokens:
                norm_token = _norm_col(token)
                for raw_c, nc in zip(raw_cols, norm_cols):
                    if norm_token == nc or f"_{norm_token}" in f"_{nc}_":
                        scores[role] += 10.0
                        detected_col_map[role][norm_token] = raw_c
                        signals[role].append(f"Supporting header: '{raw_c}' matches token '{token}'")
                        break

        # 2. Data Patterns & Value Distribution Signals
        n_rows = len(df)
        if n_rows > 0:
            # Check for negative amounts (strong signal for REFUND or CHARGEBACK)
            for c in raw_cols:
                if pd.api.types.is_numeric_dtype(df[c]):
                    neg_count = int((df[c] < 0).sum())
                    if neg_count > 0 and (neg_count / n_rows) > 0.15:
                        scores[DocumentRole.REFUND] += 15.0
                        signals[DocumentRole.REFUND].append(f"Numeric column '{c}' contains {neg_count} negative amounts")

            # Check status columns for categorical indicators
            for c in raw_cols:
                if df[c].dtype == object:
                    sample_vals = set(df[c].dropna().astype(str).str.lower().head(50))
                    if any("dispute" in v or "chargeback" in v for v in sample_vals):
                        scores[DocumentRole.CHARGEBACK] += 30.0
                        signals[DocumentRole.CHARGEBACK].append(f"Status column '{c}' contains dispute/chargeback states")
                    if any("refund" in v or "reversed" in v for v in sample_vals):
                        scores[DocumentRole.REFUND] += 25.0
                        signals[DocumentRole.REFUND].append(f"Status column '{c}' contains refund/reversed states")
                    if any("settled" in v or "paid_out" in v for v in sample_vals):
                        scores[DocumentRole.SETTLEMENT] += 20.0
                        signals[DocumentRole.SETTLEMENT].append(f"Status column '{c}' contains settlement states")

        # 3. Document Filename / Label Context (secondary signal, not authoritative alone)
        meta_str = f"{filename} {source_label or ''}".lower()
        if any(k in meta_str for k in ["settle", "payout", "batch"]):
            scores[DocumentRole.SETTLEMENT] += 25.0
            signals[DocumentRole.SETTLEMENT].append(f"Metadata match: '{filename}' mentions settlement/payout")
        elif any(k in meta_str for k in ["bank", "stmt", "statement"]):
            scores[DocumentRole.BANK_STATEMENT] += 25.0
            signals[DocumentRole.BANK_STATEMENT].append(f"Metadata match: '{filename}' mentions bank/statement")
        elif any(k in meta_str for k in ["tax", "gst", "vat", "tds"]):
            scores[DocumentRole.TAX] += 30.0
            signals[DocumentRole.TAX].append(f"Metadata match: '{filename}' mentions tax/gst/vat")
        elif any(k in meta_str for k in ["fee", "mdr", "interchange"]):
            scores[DocumentRole.FEE] += 25.0
            signals[DocumentRole.FEE].append(f"Metadata match: '{filename}' mentions fee/mdr")
        elif any(k in meta_str for k in ["refund", "reversal"]):
            scores[DocumentRole.REFUND] += 25.0
            signals[DocumentRole.REFUND].append(f"Metadata match: '{filename}' mentions refund/reversal")
        elif any(k in meta_str for k in ["dispute", "chargeback"]):
            scores[DocumentRole.CHARGEBACK] += 30.0
            signals[DocumentRole.CHARGEBACK].append(f"Metadata match: '{filename}' mentions dispute/chargeback")
        elif any(k in meta_str for k in ["ledger", "journal", "gl_"]):
            scores[DocumentRole.LEDGER] += 25.0
            signals[DocumentRole.LEDGER].append(f"Metadata match: '{filename}' mentions ledger/journal")
        elif any(k in meta_str for k in ["invoice", "bill", "inv_"]):
            scores[DocumentRole.INVOICE] += 25.0
            signals[DocumentRole.INVOICE].append(f"Metadata match: '{filename}' mentions invoice/bill")
        elif any(k in meta_str for k in ["trans", "sale", "order", "txn"]):
            scores[DocumentRole.TRANSACTION] += 25.0
            signals[DocumentRole.TRANSACTION].append(f"Metadata match: '{filename}' mentions transaction/sale")

        # 4. Determine Top Role and Confidence
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_role, top_score = sorted_scores[0]

        # Classification threshold
        if top_score < 20.0:
            return DocumentRoleClassification(
                document_id=document_id,
                filename=filename,
                document_role=DocumentRole.UNKNOWN,
                confidence=0.0,
                reason="Insufficient distinct financial vocabulary to confidently classify document role.",
                detected_columns={},
                key_signals=[],
            )

        # Normalize confidence to [0.5, 0.99]
        conf = min(0.99, max(0.50, top_score / 100.0))
        reason = f"Classified as {top_role.value} based on: {'; '.join(signals[top_role][:3])}."

        return DocumentRoleClassification(
            document_id=document_id,
            filename=filename,
            document_role=top_role,
            confidence=round(conf, 2),
            reason=reason,
            detected_columns=detected_col_map[top_role],
            key_signals=signals[top_role],
        )

    def classify_all(
        self,
        documents: List[Tuple[pd.DataFrame, str, str, str]],  # (df, doc_id, filename, source_label)
    ) -> Dict[str, DocumentRoleClassification]:
        """Classify a batch of uploaded documents."""
        results = {}
        for df, doc_id, filename, source_label in documents:
            results[doc_id] = self.classify_document(df, doc_id, filename, source_label)
        return results


role_classifier = DocumentRoleClassifier()
