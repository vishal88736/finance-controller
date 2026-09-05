"""
Deterministic working-capital analysis service.

Adopts the working-capital-optimizer reference's key idea — the cash conversion
cycle (CCC = DSO + DIO - DPO) and the AR/AP/aging breakdown — but computes every
number deterministically in Python. No LLM performs or influences the math; a
separate explanation layer may describe the result, never calculate it.

Invariants:
- Decimal arithmetic, division guarded against zero.
- Honest missing-data handling: metrics with no supporting data are None (never 0).
- Thread-scoped: only reads records for the given thread_id.
- No fabrication of inventory/COGS when absent: DIO/CCC are omitted or explicitly
  marked unavailable if the inputs cannot be derived.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models import DocumentRecord, ExceptionItemResult, ReconciliationResult
from ..database.repositories import log_audit


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _dec(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def compute_dso(receivables: Optional[Any], credit_sales: Optional[Any], days: int = 365) -> Optional[float]:
    """Days Sales Outstanding = receivables / credit_sales * days."""
    r, s = _dec(receivables), _dec(credit_sales)
    if r is None or s is None or s <= 0 or days <= 0:
        return None
    return float(_round(r / s * Decimal(days)))


def compute_dio(average_inventory: Optional[Any], cogs: Optional[Any], days: int = 365) -> Optional[float]:
    """Days Inventory Outstanding = average_inventory / COGS * days."""
    inv, c = _dec(average_inventory), _dec(cogs)
    if inv is None or c is None or c <= 0 or days <= 0:
        return None
    return float(_round(inv / c * Decimal(days)))


def compute_dpo(accounts_payable: Optional[Any], cogs: Optional[Any], days: int = 365) -> Optional[float]:
    """Days Payables Outstanding = accounts_payable / COGS * days."""
    ap, c = _dec(accounts_payable), _dec(cogs)
    if ap is None or c is None or c <= 0 or days <= 0:
        return None
    return float(_round(ap / c * Decimal(days)))


def compute_ccc(dso: Optional[float], dio: Optional[float], dpo: Optional[float]) -> Optional[float]:
    """Cash Conversion Cycle = DSO + DIO - DPO. Returns None if any operand is unknown."""
    if dso is None or dio is None or dpo is None:
        return None
    return float(_round(Decimal(str(dso)) + Decimal(str(dio)) - Decimal(str(dpo))))


class WorkingCapitalService:
    """Deterministic working-capital analysis over a thread's records."""

    def run_analysis(self, db: Session, thread_id: str, days: int = 365) -> Dict[str, Any]:
        log_audit(
            db=db, thread_id=thread_id, action="WORKING_CAPITAL_STARTED",
            agent="Working_Capital_Agent", parameters={"period_days": days},
            result_summary="Initiated deterministic working-capital analysis",
        )

        records = db.query(DocumentRecord).filter(DocumentRecord.thread_id == thread_id).all()
        matches = db.query(ReconciliationResult).filter(ReconciliationResult.thread_id == thread_id).all()
        exceptions = db.query(ExceptionItemResult).filter(ExceptionItemResult.thread_id == thread_id).all()

        if not records:
            return {
                "status": "INSUFFICIENT_DATA",
                "thread_id": thread_id,
                "message": "No financial records in this thread; upload documents and reconcile first.",
                "dso_days": None,
                "dio_days": None,
                "dpo_days": None,
                "cash_conversion_cycle_days": None,
            }

        total_inflows = Decimal("0.00")
        total_outflows = Decimal("0.00")
        inflow_docs = 0
        outflow_docs = 0

        for r in records:
            amt = _dec(r.amount)
            if amt is None:
                continue
            if amt >= 0:
                total_inflows += amt
                inflow_docs += 1
            else:
                total_outflows += abs(amt)
                outflow_docs += 1

        # Unreconciled receivables/payables = unmatched net of fee-delta misestimates.
        # Reconcile on the same signed basis: receivable = unpaid inflow, payable = unpaid outflow.
        matched_ids = {m.record_id_a for m in matches} | {m.record_id_b for m in matches}
        receivables_outstanding = Decimal("0.00")
        payables_outstanding = Decimal("0.00")
        for r in records:
            if r.record_id in matched_ids:
                continue
            amt = _dec(r.amount)
            if amt is None:
                continue
            if amt >= 0:
                receivables_outstanding += amt
            else:
                payables_outstanding += abs(amt)

        # Average settlement lag from matched pairs (date window).
        settlement_lags: List[int] = []
        for m in matches:
            try:
                da = datetime.fromisoformat(str(m.date_a).replace("Z", "+00:00"))
                dbdate = datetime.fromisoformat(str(m.date_b).replace("Z", "+00:00"))
                settlement_lags.append(abs((da - dbdate).days))
            except Exception:
                continue
        average_settlement_lag = sum(settlement_lags) / len(settlement_lags) if settlement_lags else None

        # Sales and COGS proxies are the observable inflow/outflow volumes.
        dso = compute_dso(receivables_outstanding, total_inflows, days) if total_inflows > 0 else None
        dpo = compute_dpo(payables_outstanding, total_outflows, days) if total_outflows > 0 else None
        # Inventory is not represented in the ledger; DIO stays unknown (never fabricated).
        dio = None

        # A partial CCC (DSO - DPO) is computed only when both are known; a full
        # CCC including DIO is reported unavailable without inventory/COGS data.
        ccc_full = compute_ccc(dso, 0.0 if dio is None else dio, dpo) if (dso is not None and dpo is not None and dio is not None) else None
        ccc_partial = float(_round(Decimal(str(dso)) - Decimal(str(dpo)))) if (dso is not None and dpo is not None) else None

        result = {
            "status": "COMPLETED",
            "thread_id": thread_id,
            "period_days": days,
            "total_inflows": float(_round(total_inflows)),
            "total_outflows": float(_round(total_outflows)),
            "receivables_outstanding": float(_round(receivables_outstanding)),
            "payables_outstanding": float(_round(payables_outstanding)),
            "average_settlement_lag_days": (float(round(average_settlement_lag, 2)) if average_settlement_lag is not None else None),
            "dso_days": dso,
            "dio_days": dio,
            "dpo_days": dpo,
            "cash_conversion_cycle_days": ccc_full,
            "cash_conversion_cycle_partial_days": ccc_partial,
            "methodology": (
                "DSO = unpaid receivables / total inflows * period; DPO = unpaid payables / "
                "total outflows * period; DIO omitted (no inventory representation in ledger); "
                "CCC = DSO + DIO - DPO."
            ),
            "assumptions": [
                "Unreconciled inflows are treated as receivables; unreconciled outflows as payables.",
                "Total document inflow/outflow volume is used as the sales/COGS proxy.",
                "Inventory is not represented in the uploaded ledger, so DIO is unavailable.",
            ],
            "limitations": [
                "This is a proxy computed from uploaded documents, not a full accounts-receivable/",
                "payable/inventory ledger. Treat as directional, not authoritative.",
            ],
        }

        log_audit(
            db=db, thread_id=thread_id, action="WORKING_CAPITAL_COMPLETED",
            agent="Working_Capital_Agent", parameters={"status": result["status"]},
            result_summary=(
                f"DSO {dso} days, DPO {dpo} days, DIO {dio}, partial CCC {ccc_partial} days"
            ),
        )
        return result


working_capital = WorkingCapitalService()