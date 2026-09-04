"use client";

import React from "react";
import {
  Layers,
  AlertTriangle,
  Activity,
  ArrowUpRight,
  TrendingUp,
} from "lucide-react";
import { LatestRun } from "@/lib/api";

interface OverviewCardsProps {
  latestRun: LatestRun | null;
  hasDocuments: boolean;
  documentCount: number;
  onSelect: (tab: "documents" | "matches" | "exceptions", filter?: { category?: string }) => void;
}

export const OverviewCards: React.FC<OverviewCardsProps> = ({
  latestRun,
  hasDocuments,
  documentCount,
  onSelect,
}) => {
  const run = latestRun;
  const matchRate = run ? run.match_rate : 0;
  const sourcePop = run ? (run.source_population ?? run.matched_count + run.exceptions_count) : 0;

  return (
    <div className="space-y-4">
      {/* ── Financial Health / Reconciliation Status Banner ── */}
      <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className={`w-3 h-3 rounded-full shrink-0 ${
              run
                ? "bg-emerald-500 ring-4 ring-emerald-500/20"
                : hasDocuments
                ? "bg-amber-500 ring-4 ring-amber-500/20 animate-pulse"
                : "bg-slate-300"
            }`}
          />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Reconciliation Status
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                  run
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : hasDocuments
                    ? "bg-amber-50 text-amber-700 border border-amber-200"
                    : "bg-slate-100 text-slate-600 border border-slate-200"
                }`}
              >
                {run ? "Completed" : hasDocuments ? "Ready to Reconcile" : "Awaiting Ingestion"}
              </span>
            </div>
            <p className="text-sm font-semibold text-slate-900 mt-0.5">
              {run ? (
                <>
                  <span className="text-emerald-600 font-bold">{run.matched_count}</span> of{" "}
                  <span className="font-bold">{sourcePop || run.matched_count + run.exceptions_count}</span> source records matched{" "}
                  <span className="text-slate-400 font-normal">({matchRate.toFixed(1)}%)</span>
                  {run.exceptions_count > 0 && (
                    <span className="text-amber-700 font-medium ml-2">
                      · {run.exceptions_count} exceptions require review
                    </span>
                  )}
                </>
              ) : hasDocuments ? (
                "Documents ingested and normalized. Ready to execute 4-pass deterministic matching."
              ) : (
                "Upload transaction ledger and counterpart settlement records to run the reconciliation loop."
              )}
            </p>
          </div>
        </div>

        {run && (
          <div className="flex items-center gap-3 text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200/80 px-3 py-1.5 rounded-lg shrink-0">
            <span>Throughput:</span>
            <span className="font-bold text-slate-900">
              {run.throughput_records_sec.toFixed(0)} rec/s
            </span>
            <span className="text-slate-300">•</span>
            <span>Time:</span>
            <span className="font-bold text-slate-900">
              {run.processing_time_sec.toFixed(2)}s
            </span>
          </div>
        )}
      </div>

      {/* ── Metric Cards Grid with Hero Match Rate ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* HERO CARD: MATCH RATE */}
        <div
          onClick={() => run && onSelect("matches")}
          className={`card relative overflow-hidden p-5 ${
            run ? "cursor-pointer hover:border-emerald-300 transition-all hover:shadow-md" : ""
          } border-t-4 border-t-emerald-500 bg-gradient-to-b from-emerald-50/20 to-white`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Match Rate (Track Metric)
            </span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200/60 flex items-center justify-center text-emerald-600">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900 font-[family-name:var(--font-geist-mono)] tracking-tight">
              {run ? `${matchRate.toFixed(1)}%` : "—"}
            </span>
            {run && (
              <span className="text-xs text-emerald-700 font-semibold bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                {run.matched_count} matched
              </span>
            )}
          </div>

          {/* Progress bar */}
          <div className="w-full bg-slate-100 rounded-full h-2 mt-3 overflow-hidden border border-slate-200/50">
            <div
              className="bg-emerald-500 h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(matchRate, 100)}%` }}
            />
          </div>

          <div className="text-xs text-slate-500 mt-2.5 flex items-center justify-between font-medium">
            <span>{run ? `${run.matched_count} / ${sourcePop} source records reconciled` : "No reconciliation run"}</span>
            {run && <span className="text-emerald-600 flex items-center gap-0.5">View <ArrowUpRight className="w-3 h-3" /></span>}
          </div>
        </div>

        {/* EXCEPTIONS */}
        <div
          onClick={() => run && onSelect("exceptions")}
          className={`card p-5 ${
            run ? "cursor-pointer hover:border-amber-300 transition-all hover:shadow-md" : ""
          } border-t-4 border-t-amber-500 bg-gradient-to-b from-amber-50/15 to-white`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Exceptions &amp; Fees
            </span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 border border-amber-200/60 flex items-center justify-center text-amber-600">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900 font-[family-name:var(--font-geist-mono)] tracking-tight">
              {run ? run.exceptions_count : "—"}
            </span>
            {run && run.exceptions_count > 0 && (
              <span className="text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                Needs review
              </span>
            )}
          </div>

          <div className="text-xs text-slate-500 mt-3 font-medium">
            {run
              ? run.exceptions_count > 0
                ? "Discrepancies, fees, & counterpart gaps"
                : "Clean reconciliation, 0 exceptions"
              : "Awaiting matching run"}
          </div>

          <div className="text-xs text-amber-700 mt-2 font-semibold flex items-center justify-between">
            <span>{run && run.exceptions_count > 0 ? "Click to investigate drawer" : "—"}</span>
            {run && <ArrowUpRight className="w-3 h-3 text-amber-600" />}
          </div>
        </div>

        {/* RECORDS PROCESSED */}
        <div className="card p-5 border-t-4 border-t-indigo-500 bg-gradient-to-b from-indigo-50/15 to-white">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Records Ingested
            </span>
            <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-200/60 flex items-center justify-center text-indigo-600">
              <Activity className="w-4 h-4" />
            </div>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900 font-[family-name:var(--font-geist-mono)] tracking-tight">
              {run ? run.total_records.toLocaleString() : "—"}
            </span>
            <span className="text-xs text-slate-400 font-mono">rows</span>
          </div>

          <div className="text-xs text-slate-500 mt-3 font-medium">
            {run ? "Ingested across all uploaded documents" : "Ready for ingestion"}
          </div>

          <div className="text-xs font-mono text-slate-400 mt-2">
            {run ? `Processed in ${run.processing_time_sec.toFixed(2)}s` : "Awaiting files"}
          </div>
        </div>

        {/* DOCUMENTS */}
        <div
          onClick={() => onSelect("documents")}
          className="card p-5 border-t-4 border-t-blue-500 bg-gradient-to-b from-blue-50/15 to-white cursor-pointer hover:border-blue-300 transition-all hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Documents
            </span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-200/60 flex items-center justify-center text-blue-600">
              <Layers className="w-4 h-4" />
            </div>
          </div>

          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900 font-[family-name:var(--font-geist-mono)] tracking-tight">
              {hasDocuments ? documentCount : "0"}
            </span>
            <span className="text-xs text-blue-700 font-semibold bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
              Registered
            </span>
          </div>

          <div className="text-xs text-slate-500 mt-3 font-medium">
            {hasDocuments ? "Ledger + Bank / Settlement files" : "Upload documents to begin"}
          </div>

          <div className="text-xs text-blue-600 font-semibold mt-2 flex items-center justify-between">
            <span>Manage Registry</span>
            <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>
      </div>
    </div>
  );
};
