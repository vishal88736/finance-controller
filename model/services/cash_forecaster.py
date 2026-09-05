"""
Deterministic Forward Cash Forecaster Service.
Calculates reproducible forward-looking cash projections from thread-scoped
financial records (transactions, settlements, and reconciliation pipeline).

Invariants:
- 100% deterministic calculations using Python Decimal.
- Zero LLM calculations — the LLM is only an explanation layer.
- Clear separation between ACTUAL historical data and FORECAST projections.
- Strictly isolated to thread_id.
- Persists results to SQLite and emits append-only audit events.
"""

import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models import (
    DocumentRecord,
    ReconciliationResult,
    ExceptionItemResult,
    CashForecastResult,
)
from ..database.repositories import log_audit


def _round_dec(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# Optional statistical (exponential-smoothing) run-rate. Remains 100% deterministic
# (pure Decimal), with the day-of-week weighted moving average as the default and
# the fallback when there is insufficient history.
_FORECAST_METHODS = frozenset({
    "deterministic_dow_weighted_moving_average",
    "exponential_smoothing",
})
_EWMA_ALPHA = Decimal("0.3")


def _ewma_level(values: List[Decimal]) -> Optional[Decimal]:
    """Final smoothed level of a date-ordered series (alpha=0.3)."""
    if not values:
        return None
    level = values[0]
    for v in values[1:]:
        level = _EWMA_ALPHA * v + (Decimal("1") - _EWMA_ALPHA) * level
    return _round_dec(level)


def forecast_data_context(daily_projections: List[Dict[str, Any]], analysis_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Derive demonstration-facing context from persisted daily projections:
    - analysis_date: today (server date), or an explicit override
    - historical_window_end: the date one day before the first projection row
    - dataset_is_stale: True when the historical window ends before analysis_date
      (i.e. the projections are anchored to a past / test-data vintage)
    - stale_note: a human-readable label when the dataset is stale
    """
    today = analysis_date or datetime.now().date().isoformat()
    if not daily_projections:
        return {
            "analysis_date": today,
            "historical_window_end": None,
            "dataset_is_stale": False,
            "stale_note": None,
        }
    first_date_str = daily_projections[0].get("date")
    if not first_date_str:
        return {
            "analysis_date": today,
            "historical_window_end": None,
            "dataset_is_stale": False,
            "stale_note": None,
        }
    try:
        hist_end_dt = datetime.fromisoformat(first_date_str).date() - timedelta(days=1)
    except Exception:
        return {
            "analysis_date": today,
            "historical_window_end": None,
            "dataset_is_stale": False,
            "stale_note": None,
        }
    hist_end = hist_end_dt.isoformat()
    dataset_is_stale = hist_end < today
    stale_note = (
        f"Based on uploaded test dataset dated {hist_end}; the projection window "
        f"starts before today's analysis date ({today})."
        if dataset_is_stale else None
    )
    return {
        "analysis_date": today,
        "historical_window_end": hist_end,
        "dataset_is_stale": dataset_is_stale,
        "stale_note": stale_note,
    }


class CashForecastingError(Exception):
    """Raised when cash forecasting cannot be performed."""
    pass


class CashForecasterService:
    """Production deterministic forward cash forecasting engine."""

    def __init__(self):
        pass

    def run_forecast(
        self,
        db: Session,
        thread_id: str,
        horizon_days: int = 7,
        current_cash_balance: Optional[float] = None,
        run_id: Optional[str] = None,
        method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute deterministic cash forecasting for the given thread.

        Contract (consistent):
        - Supported horizons are exactly 7, 14, and 30 days for named presets,
          with a validated range of 1..90 days for custom horizons.
        - Returns both requested_horizon and applied_horizon (applied is the
          validated/clamped value actually used).
        - Invalid horizons (<1 or >90 or non-integer) raise CashForecastingError
          with a clear message; callers map to 422.
        - `method` selects the run-rate model. Default is the deterministic
          day-of-week weighted moving average; `exponential_smoothing` is an
          optional statistical tier. Unsupported values raise CashForecastingError.
        """
        method = method or "deterministic_dow_weighted_moving_average"
        if method not in _FORECAST_METHODS:
            raise CashForecastingError(
                f"Unsupported forecast method '{method}'. Supported: "
                + ", ".join(sorted(_FORECAST_METHODS))
            )

        requested_horizon = horizon_days
        try:
            requested_int = int(horizon_days)
        except Exception:
            raise CashForecastingError(f"Invalid forecast horizon '{horizon_days}': must be an integer 1..90.")
        if requested_int < 1 or requested_int > 90:
            raise CashForecastingError(
                f"Invalid forecast horizon {requested_int}: must be between 1 and 90 days. "
                f"Supported presets are 7, 14, and 30 days."
            )
        # Validated range 1..90; presets 7/14/30 pass through unchanged.
        horizon_days = requested_int
        applied_horizon = horizon_days

        log_audit(
            db=db,
            thread_id=thread_id,
            action="CASH_FORECAST_STARTED",
            agent="Cash_Forecaster_Agent",
            parameters={"horizon_days": horizon_days, "starting_cash": current_cash_balance},
            result_summary=f"Initiated {horizon_days}-day cash forecast",
        )

        # ── 1. Retrieve thread records ──
        doc_records = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.thread_id == thread_id)
            .all()
        )

        matches = (
            db.query(ReconciliationResult)
            .filter(ReconciliationResult.thread_id == thread_id)
            .all()
        )

        exceptions = (
            db.query(ExceptionItemResult)
            .filter(ExceptionItemResult.thread_id == thread_id)
            .all()
        )

        total_source_records = len(doc_records)

        # ── 2. Handle empty / insufficient data ──
        if total_source_records == 0 and len(matches) == 0 and len(exceptions) == 0:
            result = {
                "status": "INSUFFICIENT_DATA",
                "thread_id": thread_id,
                "horizon_days": horizon_days,
                "requested_horizon": requested_horizon,
                "applied_horizon": applied_horizon,
                "message": "No transaction or settlement records are available in this thread. Upload documents before forecasting.",
                "historical_summary": {
                    "total_records": 0,
                    "date_range_days": 0,
                    "historical_inflows": 0.0,
                    "historical_outflows": 0.0,
                },
                "forecast": None,
                "daily_projections": [],
                "confidence_level": "LOW",
                "forecast_method": method,
                "methodology": "Deterministic historical moving average",
                "input_period": {"start": None, "end": None, "date_span_days": 0},
                "horizon": {"requested": requested_horizon, "applied": applied_horizon},
                "data_sufficiency": {"sufficient": False, "reason": "No historical records."},
                "assumptions": ["Requires historical financial records to project future cash flows."],
                "limitations": ["Insufficient data points to build a baseline velocity."],
            }
            log_audit(
                db=db,
                thread_id=thread_id,
                action="CASH_FORECAST_COMPLETED",
                agent="Cash_Forecaster_Agent",
                parameters={"status": "INSUFFICIENT_DATA"},
                result_summary="Completed with INSUFFICIENT_DATA (0 records)",
            )
            return result

        # ── 3. Parse historical inflows & outflows by date ──
        daily_inflows: Dict[str, Decimal] = defaultdict(Decimal)
        daily_outflows: Dict[str, Decimal] = defaultdict(Decimal)
        valid_dates: List[datetime] = []
        pending_pipeline_amount = Decimal("0.00")

        # Ingest document records
        for r in doc_records:
            amt = Decimal(str(r.amount if r.amount is not None else 0.0))
            is_outflow = amt < 0 or (r.source and "fee" in r.source.lower()) or (r.description and "refund" in r.description.lower())
            abs_amt = abs(amt)

            if r.iso_date:
                try:
                    dt = datetime.fromisoformat(r.iso_date.replace("Z", "+00:00")).date()
                    valid_dates.append(datetime(dt.year, dt.month, dt.day))
                    d_str = dt.isoformat()
                    if is_outflow:
                        daily_outflows[d_str] += abs_amt
                    else:
                        daily_inflows[d_str] += abs_amt
                except Exception:
                    pending_pipeline_amount += abs_amt
            else:
                # Undated record belongs to pending queue
                pending_pipeline_amount += abs_amt

        # Ingest matches and exceptions if doc records were sparse
        if len(daily_inflows) == 0 and len(matches) > 0:
            for m in matches:
                amt = Decimal(str(m.amount_a if m.amount_a is not None else 0.0))
                abs_amt = abs(amt)
                d_str = m.date_a or m.date_b
                if d_str:
                    try:
                        dt = datetime.fromisoformat(d_str.replace("Z", "+00:00")).date()
                        valid_dates.append(datetime(dt.year, dt.month, dt.day))
                        daily_inflows[dt.isoformat()] += abs_amt
                    except Exception:
                        pending_pipeline_amount += abs_amt
                else:
                    pending_pipeline_amount += abs_amt

        # Sum historical metrics
        total_hist_inflow = sum(daily_inflows.values(), Decimal("0.00"))
        total_hist_outflow = sum(daily_outflows.values(), Decimal("0.00"))

        if len(valid_dates) > 0:
            min_date = min(valid_dates)
            max_date = max(valid_dates)
            date_span_days = max(1, (max_date - min_date).days + 1)
        else:
            min_date = datetime.now()
            max_date = datetime.now()
            date_span_days = 1

        # ── 4. Baseline daily run-rate & day-of-week multipliers ──
        # Daily averages
        effective_days = Decimal(str(max(1, len(daily_inflows) or date_span_days)))

        if method == "exponential_smoothing":
            in_vals = [daily_inflows[d] for d in sorted(daily_inflows)]
            out_vals = [daily_outflows[d] for d in sorted(daily_outflows)]
            base_daily_inflow = _ewma_level(in_vals) or Decimal("0.00")
            base_daily_outflow = _ewma_level(out_vals) or Decimal("0.00")
        else:
            base_daily_inflow = total_hist_inflow / effective_days if effective_days > 0 else Decimal("0.00")
            base_daily_outflow = total_hist_outflow / effective_days if effective_days > 0 else Decimal("0.00")

        # If no outflow data is observed, do NOT invent a fee/refund run-rate.
        # The forecast projects observed outflows only and records this honestly.
        outflows_unobserved = base_daily_outflow == Decimal("0.00") and base_daily_inflow > Decimal("0.00")

        # Day-of-week volume weighting (Monday=0 ... Sunday=6)
        dow_weights = {
            0: Decimal("1.10"),  # Monday catchup
            1: Decimal("1.05"),  # Tuesday
            2: Decimal("1.00"),  # Wednesday
            3: Decimal("1.00"),  # Thursday
            4: Decimal("1.15"),  # Friday high volume
            5: Decimal("0.40"),  # Saturday low volume
            6: Decimal("0.30"),  # Sunday low volume
        }

        # ── 5. Starting Cash Position ──
        # Baseline must have an explicit source. We never invent a monetary
        # default such as $10,000.
        if current_cash_balance is not None:
            starting_balance = Decimal(str(current_cash_balance))
            baseline_source = "USER_PROVIDED"
        else:
            # No opening balance provided: derive the baseline from observed net
            # historical cash flows. This is a documented, actual derived figure,
            # not a fabricated constant. It may legitimately be <= 0.
            net_hist = total_hist_inflow - total_hist_outflow
            starting_balance = net_hist
            baseline_source = "HISTORY_DERIVED"

        starting_balance = _round_dec(starting_balance)

        # ── 6. Generate Forward Day-by-Day Forecast ──
        daily_projections = []
        running_balance = starting_balance
        proj_start_date = (max_date + timedelta(days=1)).date()

        total_proj_inflow = Decimal("0.00")
        total_proj_outflow = Decimal("0.00")

        # Pending settlement realization window (first 2 days)
        pending_pipeline_per_day = _round_dec(pending_pipeline_amount / Decimal("2")) if pending_pipeline_amount > 0 else Decimal("0.00")

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for i in range(horizon_days):
            curr_date = proj_start_date + timedelta(days=i)
            dow = curr_date.weekday()
            weight = dow_weights.get(dow, Decimal("1.00"))

            # Calculate day inflow
            day_inflow = _round_dec(base_daily_inflow * weight)
            # Add pending pipeline realization in first 2 business days
            if i < 2 and pending_pipeline_amount > 0 and dow < 5:
                day_inflow += pending_pipeline_per_day

            # Calculate day outflow
            day_outflow = _round_dec(base_daily_outflow * weight)

            net_day = day_inflow - day_outflow
            running_balance += net_day

            total_proj_inflow += day_inflow
            total_proj_outflow += day_outflow

            daily_projections.append({
                "day_number": i + 1,
                "date": curr_date.isoformat(),
                "day_of_week": day_names[dow],
                "projection_type": "FORECAST",
                "projected_inflow": float(day_inflow),
                "projected_outflow": float(day_outflow),
                "net_change": float(net_day),
                "projected_closing_cash": float(_round_dec(running_balance)),
                "is_weekend": dow >= 5,
            })

        net_projected_change = total_proj_inflow - total_proj_outflow
        ending_balance = running_balance

        context = forecast_data_context(daily_projections)

        # Determine confidence level
        if date_span_days >= 14 and total_source_records >= 20:
            confidence = "HIGH"
        elif date_span_days >= 5 or total_source_records >= 6:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        methodology_desc = (
            f"Deterministic {method.replace('_', ' ')} with "
            "settlement pipeline realization. Outflow run-rate is derived "
            "strictly from observed historical outflows (no synthetic fee calibration)."
        )

        assumptions_list = [
            f"Baseline daily velocity derived from {len(doc_records)} recorded source documents.",
            f"Baseline cash source: {baseline_source.lower()}.",
            "Day-of-week seasonal multiplier applied (elevated Friday settlements, reduced weekend banking).",
            "Pending settlement pipeline assumed to clear within 2 business days.",
            "Excludes unrecorded extraordinary capital financing or manual wire draws.",
        ]
        if outflows_unobserved:
            assumptions_list.append(
                "No outflow records observed in the historical window; projected outflows are zero."
            )
        elif baseline_source == "HISTORY_DERIVED":
            assumptions_list.append(
                "No opening cash balance provided; baseline derived from net historical cash flows."
            )

        limitations_list = [
            "Forecast represents statistical cash flow expectation and does not account for unexpected banking halts.",
            "Accuracy depends on the completeness of uploaded ledger and settlement records.",
        ]

        # ── 7. Persist to Database ──
        forecast_id = f"fct_{uuid.uuid4().hex[:12]}"
        forecast_record = CashForecastResult(
            id=forecast_id,
            thread_id=thread_id,
            run_id=run_id,
            horizon_days=horizon_days,
            current_cash_balance=float(starting_balance),
            baseline_source=baseline_source,
            projected_inflows=float(_round_dec(total_proj_inflow)),
            projected_outflows=float(_round_dec(total_proj_outflow)),
            net_projected_change=float(_round_dec(net_projected_change)),
            projected_ending_cash=float(_round_dec(ending_balance)),
            confidence_level=confidence,
            methodology=methodology_desc,
            assumptions_json=json.dumps(assumptions_list),
            daily_forecast_json=json.dumps(daily_projections),
        )
        db.add(forecast_record)
        db.commit()

        log_audit(
            db=db,
            thread_id=thread_id,
            action="CASH_FORECAST_COMPLETED",
            agent="Cash_Forecaster_Agent",
            parameters={
                "forecast_id": forecast_id,
                "horizon_days": horizon_days,
                "current_cash": float(starting_balance),
                "ending_cash": float(_round_dec(ending_balance)),
                "confidence": confidence,
            },
            result_summary=(
                f"Generated {horizon_days}-day forecast: "
                f"Start ${starting_balance:,.2f} -> End ${ending_balance:,.2f} "
                f"(Net Δ ${net_projected_change:,.2f})"
            ),
        )

        return {
            "status": "COMPLETED",
            "forecast_id": forecast_id,
            "thread_id": thread_id,
            "horizon_days": horizon_days,
            "requested_horizon": requested_horizon,
            "applied_horizon": applied_horizon,
            "horizon": {"requested": requested_horizon, "applied": applied_horizon},
            "current_cash_balance": float(starting_balance),
            "baseline_source": baseline_source,
            "projected_inflows": float(_round_dec(total_proj_inflow)),
            "projected_outflows": float(_round_dec(total_proj_outflow)),
            "net_projected_change": float(_round_dec(net_projected_change)),
            "projected_ending_cash": float(_round_dec(ending_balance)),
            "confidence_level": confidence,
            "forecast_method": method,
            "methodology": methodology_desc,
            "input_period": {
                "start": min_date.date().isoformat() if hasattr(min_date, "date") else str(min_date),
                "end": max_date.date().isoformat() if hasattr(max_date, "date") else str(max_date),
                "date_span_days": date_span_days,
            },
            "data_sufficiency": {
                "sufficient": True,
                "total_source_records": total_source_records,
                "date_span_days": date_span_days,
                "confidence": confidence,
            },
            "assumptions": assumptions_list,
            "limitations": limitations_list,
            "analysis_date": context["analysis_date"],
            "historical_window_end": context["historical_window_end"],
            "dataset_is_stale": context["dataset_is_stale"],
            "stale_note": context["stale_note"],
            "outflows_observed": bool(base_daily_outflow > Decimal("0.00")),
            "historical_baseline": {
                "total_source_records": total_source_records,
                "date_span_days": date_span_days,
                "daily_inflow_runrate": float(_round_dec(base_daily_inflow)),
                "daily_outflow_runrate": float(_round_dec(base_daily_outflow)),
            },
            "daily_projections": daily_projections,
        }


cash_forecaster = CashForecasterService()
