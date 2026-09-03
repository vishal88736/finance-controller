"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  TrendingUp,
  Calendar,
  DollarSign,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Loader2,
  HelpCircle,
  ArrowUpRight,
  ShieldCheck,
  Info,
} from "lucide-react";
import { api, CashForecastData } from "@/lib/api";

interface CashForecastViewProps {
  threadId: string;
  hasDocuments: boolean;
  onUploadClick?: () => void;
}

export const CashForecastView: React.FC<CashForecastViewProps> = ({
  threadId,
  hasDocuments,
  onUploadClick,
}) => {
  const [horizon, setHorizon] = useState<number>(7);
  const [forecast, setForecast] = useState<CashForecastData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchForecast = useCallback(
    async (hDays: number) => {
      if (!threadId) return;
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.getForecast(threadId, hDays);
        setForecast(data);
      } catch (err: any) {
        setError(err?.message || "Failed to load forward cash forecast.");
      } finally {
        setIsLoading(false);
      }
    },
    [threadId]
  );

  const handleRunForecast = async () => {
    if (!threadId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.runForecast(threadId, horizon);
      setForecast(data);
    } catch (err: any) {
      setError(err?.message || "Failed to execute cash forecast.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchForecast(horizon);
  }, [fetchForecast, horizon]);

  if (!hasDocuments && (!forecast || forecast.status === "INSUFFICIENT_DATA")) {
    return (
      <div className="card p-12 text-center max-w-xl mx-auto space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-600 mx-auto">
          <Calendar className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">Forward Cash Forecaster</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            Deterministic cash flow projections require transaction and settlement records to build
            an operational velocity baseline.
          </p>
        </div>
        {onUploadClick && (
          <button
            onClick={onUploadClick}
            className="btn btn-primary text-xs font-semibold px-4 py-2"
          >
            Upload Documents
          </button>
        )}
      </div>
    );
  }

  const projections = forecast?.daily_projections || [];
  const maxBar = Math.max(
    ...projections.map((p) => Math.max(p.projected_inflow, p.projected_outflow)),
    1000
  );

  return (
    <div className="space-y-6">
      {/* ── Top Controls ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Forward Cash Forecaster (Agent 3)
            </span>
            <span className="pill bg-blue-50 text-blue-700 border border-blue-200">
              Deterministic Projections
            </span>
          </div>
          <h2 className="text-base font-bold text-slate-900 mt-0.5">
            Projected Cash Position &amp; Settlement Velocity
          </h2>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs font-medium">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => setHorizon(d)}
                className={`px-3 py-1 rounded-md transition-all cursor-pointer ${
                  horizon === d
                    ? "bg-white text-slate-900 font-bold shadow-xs border border-slate-200/80"
                    : "text-slate-500 hover:text-slate-900"
                }`}
              >
                {d} Days
              </button>
            ))}
          </div>

          <button
            onClick={handleRunForecast}
            disabled={isLoading}
            className="btn btn-secondary text-xs font-semibold px-3 py-2 flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>{isLoading ? "Projecting…" : "Recalculate"}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {forecast?.dataset_is_stale && (
        <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl text-xs text-sky-800 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
          <span>{forecast.stale_note}</span>
        </div>
      )}

      {/* ── Metric Summary Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Baseline Cash */}
        <div className="card p-5 border-t-4 border-t-slate-500 bg-white">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Baseline Cash
            </span>
            <span className="text-[10px] font-bold text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">
              {forecast?.baseline_source === "USER_PROVIDED"
                ? "PROVIDED"
                : forecast?.baseline_source === "HISTORY_DERIVED"
                ? "ASSUMED"
                : "ACTUAL"}
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-slate-900">
            ${(forecast?.current_cash_balance ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-500 mt-2">
            {forecast?.baseline_source === "USER_PROVIDED"
              ? "Opening cash position provided by the user"
              : forecast?.baseline_source === "HISTORY_DERIVED"
              ? "Not provided — assumed from net historical cash flows"
              : "Starting operating cash position"}
          </div>
        </div>

        {/* Expected Inflows */}
        <div className="card p-5 border-t-4 border-t-emerald-500 bg-emerald-50/10">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-800">
              Expected Inflows
            </span>
            <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
              FORECAST
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-600">
            +${(forecast?.projected_inflows ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-500 mt-2">
            Settlement pipeline &amp; day-of-week inflow velocity
          </div>
        </div>

        {/* Expected Outflows */}
        <div className="card p-5 border-t-4 border-t-amber-500 bg-amber-50/10">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-amber-800">
              Expected Outflows
            </span>
            <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
              FORECAST
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-amber-700">
            -${(forecast?.projected_outflows ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-500 mt-2">
            {forecast?.outflows_observed
              ? "Observed fee, refund, and operating deductions"
              : "No outflow records observed — projected as $0 (assumption)"}
          </div>
        </div>

        {/* Projected Ending Cash */}
        <div className="card p-5 border-t-4 border-t-blue-600 bg-blue-50/15">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-blue-900">
              Projected Ending Cash
            </span>
            <span className="text-[10px] font-bold text-blue-700 bg-blue-100/70 border border-blue-200 px-2 py-0.5 rounded-full">
              {horizon}D FORECAST
            </span>
          </div>
          <div className="text-2xl font-bold font-mono text-blue-700">
            ${(forecast?.projected_ending_cash ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-500 mt-2 flex items-center justify-between">
            <span>Net Change:</span>
            <span
              className={`font-mono font-bold ${
                (forecast?.net_projected_change ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
              }`}
            >
              {(forecast?.net_projected_change ?? 0) >= 0 ? "+" : ""}
              ${(forecast?.net_projected_change ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </div>

      {/* ── Visual Daily Trajectory Chart ── */}
      {projections.length > 0 && (
        <div className="card p-5 bg-white space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Daily Inflow / Outflow &amp; Cash Trajectory ({horizon} Days)
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Bars represent daily volumes; dotted guide represents projected closing cash position.
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs font-mono">
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-emerald-500" />
                <span className="text-slate-600">Inflow</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-amber-400" />
                <span className="text-slate-600">Outflow</span>
              </div>
            </div>
          </div>

          <div className="space-y-2 pt-2">
            {projections.map((p) => {
              const inflowPct = Math.min(100, (p.projected_inflow / maxBar) * 100);
              const outflowPct = Math.min(100, (p.projected_outflow / maxBar) * 100);

              return (
                <div
                  key={p.day_number}
                  className={`p-2.5 rounded-lg border text-xs font-mono transition-colors ${
                    p.is_weekend
                      ? "bg-slate-50/50 border-slate-200/50 opacity-75"
                      : "bg-white border-slate-200/80 hover:bg-slate-50/80"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 w-16">Day {p.day_number}</span>
                      <span className="text-slate-500 w-24">{p.date}</span>
                      <span className="text-slate-400 font-sans text-[11px]">{p.day_of_week}</span>
                    </div>

                    <div className="flex items-center gap-4">
                      <span className="text-emerald-700 font-semibold">
                        +${p.projected_inflow.toFixed(2)}
                      </span>
                      <span className="text-amber-700 font-semibold">
                        -${p.projected_outflow.toFixed(2)}
                      </span>
                      <span className="text-slate-900 font-bold w-24 text-right">
                        ${p.projected_closing_cash.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  {/* Dual Bar Representation */}
                  <div className="grid grid-cols-2 gap-2 h-2 rounded bg-slate-100 overflow-hidden">
                    <div className="flex justify-end">
                      <div
                        className="bg-emerald-500 h-full rounded-sm"
                        style={{ width: `${inflowPct}%` }}
                      />
                    </div>
                    <div>
                      <div
                        className="bg-amber-400 h-full rounded-sm"
                        style={{ width: `${outflowPct}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Assumptions & Confidence ── */}
      {forecast && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card p-5 bg-white space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-blue-600" />
              Forecasting Methodology &amp; Confidence
            </h4>
            <div className="text-xs text-slate-600 leading-relaxed pt-1">
              {forecast.methodology}
            </div>
            <div className="flex items-center gap-2 pt-2">
              <span className="text-xs text-slate-500 font-semibold">Statistical Confidence:</span>
              <span
                className={`pill ${
                  forecast.confidence_level === "HIGH"
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : "bg-blue-50 text-blue-700 border-blue-200"
                }`}
              >
                {forecast.confidence_level}
              </span>
            </div>
          </div>

          <div className="card p-5 bg-white space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
              <Info className="w-4 h-4 text-slate-500" />
              Assumptions &amp; Model Guardrails
            </h4>
            <ul className="text-xs text-slate-600 space-y-1.5 list-disc pl-4 pt-1">
              {(forecast.assumptions || []).map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};
