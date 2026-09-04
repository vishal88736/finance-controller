"""
Deterministic Tax-Line Matcher Service.
Compares financial transaction and invoice amounts against reported tax lines
using strict mathematical calculations (e.g., GST, VAT, TDS, sales tax).

Invariants:
- 100% deterministic arithmetic using Python Decimal.
- Zero LLM calculations — the LLM is only an explanation layer.
- Thread-scoped isolation: never reads cross-thread data.
- Enforces expected_tax = round(taxable_amount * tax_rate, 2).
- Only tax-bearing records are eligible (never treats bank/chargeback rows as tax lines).
- Explicit statuses: MATCH, MISMATCH, MISSING, AMBIGUOUS, NOT_TAX_APPLICABLE,
  TAX_DATA_UNAVAILABLE, DUPLICATE.
- Distinguishes signed net variance from absolute cumulative discrepancy.
- Persists to SQLite and emits append-only audit events.
"""

import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models import DocumentRecord, TaxMatchResult
from ..database.repositories import log_audit


import math

def _safe_dec(val, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if val is None:
        return default
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return default
    val_str = str(val).strip().lower()
    if val_str in ("", "nan", "none", "null", "inf", "-inf"):
        return default
    try:
        d = Decimal(str(val))
        if d.is_nan() or d.is_infinite():
            return default
        return d
    except Exception:
        return default


def _sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _round_dec(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# Fields that mark a record as a *tax-bearing* line. Records without any of
# these are NOT tax lines and must never be forced into a MATCH/MISMATCH.
_TAX_EVIDENCE_FIELDS = (
    "tax_amount", "tax", "gst", "vat", "tds", "cgst", "sgst", "igst",
    "tax_rate", "gst_rate", "vat_rate", "taxable_amount", "taxable_base",
    "tax_deducted", "withholding_tax", "sales_tax",
)


def _is_tax_eligible(raw_data: Dict[str, Any]) -> bool:
    if not raw_data:
        return False
    return any(k in raw_data for k in _TAX_EVIDENCE_FIELDS)


class TaxMatcherService:
    """Production deterministic tax-line matcher engine."""

    def __init__(self, default_tax_rate: float = 0.18, default_tolerance: float = 0.05):
        self.default_tax_rate = Decimal(str(default_tax_rate))
        self.default_tolerance = Decimal(str(default_tolerance))

    def run_tax_matching(
        self,
        db: Session,
        thread_id: str,
        tax_rate: Optional[float] = None,
        tolerance: Optional[float] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify tax-bearing lines in the given thread against deterministic tax
        expectations. Non-tax-bearing records (bank statements, chargebacks,
        plain transactions) are classified NOT_TAX_APPLICABLE and excluded from
        the tax-eligible denominator.
        """
        user_supplied_rate = tax_rate is not None
        rate = Decimal(str(tax_rate)) if tax_rate is not None else self.default_tax_rate
        tol = Decimal(str(tolerance)) if tolerance is not None else self.default_tolerance
        default_rate_source = "USER_CONFIGURED" if user_supplied_rate else "ASSUMED"

        log_audit(
            db=db,
            thread_id=thread_id,
            action="TAX_MATCH_STARTED",
            agent="Tax_Matcher_Agent",
            parameters={"tax_rate": float(rate), "tolerance": float(tol)},
            result_summary=f"Initiated tax-line matching at {float(rate)*100:.1f}% rate",
        )

        doc_records = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.thread_id == thread_id)
            .all()
        )

        if not doc_records:
            result = {
                "status": "NO_DATA",
                "thread_id": thread_id,
                "message": "No financial records found in this thread to perform tax matching.",
                "total_records": 0,
                "tax_eligible_count": 0,
                "matched_count": 0,
                "mismatched_count": 0,
                "missing_count": 0,
                "ambiguous_count": 0,
                "not_applicable_count": 0,
                "unavailable_count": 0,
                "tax_match_rate": 0.0,
                "total_tax_expected": 0.0,
                "total_tax_reported": 0.0,
                "total_tax_discrepancy": 0.0,
                "net_tax_variance": 0.0,
                "tax_lines": [],
            }
            log_audit(
                db=db,
                thread_id=thread_id,
                action="TAX_MATCH_COMPLETED",
                agent="Tax_Matcher_Agent",
                parameters={"status": "NO_DATA"},
                result_summary="Completed with NO_DATA (0 records)",
            )
            return result

        tax_lines = []
        matched_count = 0
        mismatched_count = 0
        missing_count = 0
        ambiguous_count = 0
        not_applicable_count = 0
        unavailable_count = 0

        total_expected_tax = Decimal("0.00")
        total_reported_tax = Decimal("0.00")
        total_tax_discrepancy = Decimal("0.00")  # absolute cumulative variance
        net_tax_variance = Decimal("0.00")        # signed net variance

        # Clear prior tax results for fresh analysis in this run
        db.query(TaxMatchResult).filter(TaxMatchResult.thread_id == thread_id).delete()

        for rec in doc_records:
            raw_data = json.loads(rec.raw_data_json) if rec.raw_data_json else {}

            # ── Eligibility gate: only tax-bearing records are tax lines ──
            if not _is_tax_eligible(raw_data):
                not_applicable_count += 1
                line_entry = {
                    "id": f"tax_{uuid.uuid4().hex[:10]}",
                    "record_id": rec.record_id,
                    "source": rec.source,
                    "taxable_amount": 0.0,
                    "tax_rate": None,
                    "tax_rate_source": "NONE",
                    "expected_tax": 0.0,
                    "reported_tax": 0.0,
                    "tax_difference": 0.0,
                    "status": "NOT_TAX_APPLICABLE",
                    "explanation": (
                        f"Record '{rec.record_id}' ({rec.source}) carries no tax evidence "
                        "(no tax/gst/vat/taxable/tax_rate fields); it is not a tax line."
                    ),
                    "evidence": {
                        "record_id": rec.record_id,
                        "source": rec.source,
                        "date": rec.iso_date,
                    },
                }
                tax_lines.append(line_entry)

                db_record = TaxMatchResult(
                    id=line_entry["id"],
                    thread_id=thread_id,
                    run_id=run_id,
                    record_id=rec.record_id,
                    source=rec.source,
                    taxable_amount=0.0,
                    tax_rate=0.0,
                    expected_tax=0.0,
                    reported_tax=0.0,
                    tax_difference=0.0,
                    status=line_entry["status"],
                    evidence_json=json.dumps(line_entry["evidence"]),
                    explanation=line_entry["explanation"],
                )
                db.add(db_record)
                continue

            # Identify taxable amount (or gross / subtotal)
            taxable_val = None
            for key in ["taxable_amount", "taxable_base", "subtotal", "base_amount", "net_amount", "gross_amount", "amount"]:
                if key in raw_data:
                    parsed = _safe_dec(raw_data[key])
                    if parsed is not None:
                        taxable_val = parsed
                        break
            if taxable_val is None:
                taxable_val = _safe_dec(rec.amount, Decimal("0.00"))

            # Identify reported tax amount
            reported_tax_val = None
            for key in ["tax_amount", "tax", "gst", "vat", "tds", "withholding_tax", "tax_deducted", "cgst", "sgst", "igst"]:
                if key in raw_data:
                    parsed = _safe_dec(raw_data[key])
                    if parsed is not None:
                        reported_tax_val = parsed
                        break

            # Identify specific line tax rate if specified, else use global rate
            item_rate = rate
            rate_source = default_rate_source
            for key in ["tax_rate", "rate", "gst_rate", "vat_rate"]:
                if key in raw_data:
                    parsed_rate = _safe_dec(raw_data[key])
                    if parsed_rate is not None:
                        if parsed_rate > Decimal("1.00"):
                            parsed_rate = parsed_rate / Decimal("100.00")
                        item_rate = parsed_rate
                        rate_source = "SOURCE_DATA"
                        break

            # ── Zero taxable base: never auto-MATCH without exemption evidence ──
            if taxable_val == Decimal("0.00") or taxable_val < Decimal("0.005"):
                raw_str = str(raw_data).lower()
                if reported_tax_val in (None, Decimal("0.00")) and any(
                    t in raw_str for t in ("exempt", "zero_rated", "zero rated", "exemption")
                ):
                    status = "MATCH"
                    explanation = "Verified zero-tax line: taxable base is zero and an exemption/zero-rated flag is present."
                    matched_count += 1
                else:
                    status = "TAX_DATA_UNAVAILABLE"
                    explanation = (
                        "Zero taxable base with no exemption/zero-rated evidence; "
                        "tax applicability cannot be verified."
                    )
                    unavailable_count += 1
                expected_tax_val = Decimal("0.00")
                reported = reported_tax_val if reported_tax_val is not None else Decimal("0.00")
                diff = abs(reported - expected_tax_val)
            else:
                # Calculate deterministic expected tax
                expected_tax_val = _round_dec(taxable_val * item_rate)

                if reported_tax_val is None:
                    reported_tax_val = Decimal("0.00")

                diff = abs(reported_tax_val - expected_tax_val)
                try:
                    effective_rate = (reported_tax_val / taxable_val) if taxable_val > Decimal("0.00") else Decimal("0.00")
                except Exception:
                    effective_rate = Decimal("0.00")

                # Classify line status
                if reported_tax_val == Decimal("0.00") and expected_tax_val > Decimal("0.00"):
                    status = "MISSING"
                    explanation = (
                        f"Taxable base of ${taxable_val:,.2f} at {float(item_rate)*100:.1f}% tax rate "
                        f"expects ${expected_tax_val:,.2f} tax, but no tax line was reported."
                    )
                    missing_count += 1
                else:
                    # Check ambiguity: e.g. conflicting rates or subtotal + tax != total
                    total_val = None
                    for key in ["total", "total_amount", "invoice_total"]:
                        if key in raw_data:
                            parsed_total = _safe_dec(raw_data[key])
                            if parsed_total is not None:
                                total_val = parsed_total
                                break

                    if total_val is not None and abs(total_val - (taxable_val + reported_tax_val)) > tol:
                        status = "AMBIGUOUS"
                        explanation = (
                            f"Invoice total (${total_val:,.2f}) does not equal subtotal (${taxable_val:,.2f}) "
                            f"+ tax (${reported_tax_val:,.2f}). Possible additional fee or discounting."
                        )
                        ambiguous_count += 1
                    elif diff <= tol:
                        status = "MATCH"
                        explanation = (
                            f"Tax matches expected calculation: ${taxable_val:,.2f} × {float(item_rate)*100:.1f}% "
                            f"= ${expected_tax_val:,.2f} (reported: ${reported_tax_val:,.2f}, diff: ${diff:,.2f})."
                        )
                        matched_count += 1
                    else:
                        status = "MISMATCH"
                        explanation = (
                            f"Tax mismatch detected: ${taxable_val:,.2f} at {float(item_rate)*100:.1f}% expects "
                            f"${expected_tax_val:,.2f}, but reported ${reported_tax_val:,.2f} "
                            f"(effective rate {float(effective_rate)*100:.2f}%, variance: Δ ${diff:,.2f})."
                        )
                        mismatched_count += 1

            signed_diff = reported_tax_val - expected_tax_val
            total_expected_tax += expected_tax_val
            total_reported_tax += reported_tax_val
            total_tax_discrepancy += diff
            net_tax_variance += signed_diff

            line_entry = {
                "id": f"tax_{uuid.uuid4().hex[:10]}",
                "record_id": rec.record_id,
                "source": rec.source,
                "taxable_amount": float(_round_dec(taxable_val)),
                "tax_rate": float(item_rate) if item_rate is not None else None,
                "tax_rate_source": rate_source,
                "expected_tax": float(_round_dec(expected_tax_val)),
                "reported_tax": float(_round_dec(reported_tax_val)),
                "tax_difference": float(_round_dec(diff)),
                "status": status,
                "explanation": explanation,
                "evidence": {
                    "record_id": rec.record_id,
                    "source": rec.source,
                    "date": rec.iso_date,
                    "tax_rate_source": rate_source,
                    "calculation": f"${taxable_val:,.2f} × {float(item_rate)*100:.1f}% = ${expected_tax_val:,.2f}" if item_rate is not None else None,
                    "difference": f"${diff:,.2f}",
                    "signed_variance": f"${signed_diff:,.2f}",
                    "raw_data": _sanitize_for_json(raw_data),
                },
            }
            tax_lines.append(line_entry)

            # Persist row
            db_record = TaxMatchResult(
                id=line_entry["id"],
                thread_id=thread_id,
                run_id=run_id,
                record_id=rec.record_id,
                source=rec.source,
                taxable_amount=line_entry["taxable_amount"] if line_entry["taxable_amount"] is not None else 0.0,
                tax_rate=line_entry["tax_rate"] if line_entry["tax_rate"] is not None else 0.0,
                expected_tax=line_entry["expected_tax"],
                reported_tax=line_entry["reported_tax"],
                tax_difference=line_entry["tax_difference"],
                status=line_entry["status"],
                evidence_json=json.dumps(line_entry["evidence"]),
                explanation=line_entry["explanation"],
            )
            db.add(db_record)

        db.commit()

        tax_eligible_count = matched_count + mismatched_count + missing_count + ambiguous_count + unavailable_count
        total_lines = len(tax_lines)
        match_rate = (matched_count / tax_eligible_count * 100.0) if tax_eligible_count > 0 else 0.0

        log_audit(
            db=db,
            thread_id=thread_id,
            action="TAX_MATCH_COMPLETED",
            agent="Tax_Matcher_Agent",
            parameters={
                "total_records": total_lines,
                "tax_eligible": tax_eligible_count,
                "matched": matched_count,
                "mismatched": mismatched_count,
                "missing": missing_count,
                "ambiguous": ambiguous_count,
                "not_applicable": not_applicable_count,
                "unavailable": unavailable_count,
                "match_rate": round(match_rate, 2),
            },
            result_summary=(
                f"Tax matching complete: {matched_count}/{tax_eligible_count} eligible matched "
                f"({match_rate:.1f}%), {mismatched_count} mismatches, {missing_count} missing, "
                f"{not_applicable_count} not applicable. "
                f"Net variance: ${net_tax_variance:,.2f}, absolute variance: ${total_tax_discrepancy:,.2f}"
            ),
        )

        return {
            "status": "COMPLETED",
            "thread_id": thread_id,
            "total_records": total_lines,
            "tax_eligible_count": tax_eligible_count,
            "matched_count": matched_count,
            "mismatched_count": mismatched_count,
            "missing_count": missing_count,
            "ambiguous_count": ambiguous_count,
            "not_applicable_count": not_applicable_count,
            "unavailable_count": unavailable_count,
            "tax_match_rate": round(match_rate, 2),
            "total_tax_expected": float(_round_dec(total_expected_tax)) if tax_eligible_count > 0 else None,
            "total_tax_reported": float(_round_dec(total_reported_tax)) if tax_eligible_count > 0 else None,
            "total_tax_discrepancy": float(_round_dec(total_tax_discrepancy)) if tax_eligible_count > 0 else None,
            "net_tax_variance": float(_round_dec(net_tax_variance)) if tax_eligible_count > 0 else None,
            "tax_lines": tax_lines,
        }


tax_matcher = TaxMatcherService()