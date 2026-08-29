"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, Activity, Zap, TrendingUp, ShieldCheck } from "lucide-react";
import { ReconciliationRunSummary } from "@/lib/api";

interface MetricCardsProps {
  summary: ReconciliationRunSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ summary }) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {/* 1. Processed */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Processed</span>
          <Activity className="w-4 h-4 text-slate-400" />
        </div>
        <div className="text-xl font-bold text-slate-900 tracking-tight">
          {summary.total_records.toLocaleString()}
        </div>
        <div className="text-[11px] text-slate-500 mt-1 font-medium">Total Multi-Source Records</div>
      </div>

      {/* 2. Matched */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Matched</span>
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
        </div>
        <div className="text-xl font-bold text-emerald-700 tracking-tight">
          {summary.matched_records.toLocaleString()}
        </div>
        <div className="text-[11px] text-emerald-600 mt-1 font-medium">Reconciled pairs</div>
      </div>

      {/* 3. Exceptions */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Exceptions</span>
          <AlertTriangle className="w-4 h-4 text-amber-600" />
        </div>
        <div className="text-xl font-bold text-amber-700 tracking-tight">
          {summary.exception_records.toLocaleString()}
        </div>
        <div className="text-[11px] text-amber-600 mt-1 font-medium">Honest Unresolved</div>
      </div>

      {/* 4. Match Rate */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Match Rate</span>
          <TrendingUp className="w-4 h-4 text-blue-600" />
        </div>
        <div className="text-xl font-bold text-blue-700 tracking-tight">
          {summary.match_rate.toFixed(1)}%
        </div>
        <div className="text-[11px] text-slate-500 mt-1 font-medium">Ledger coverage</div>
      </div>

      {/* 5. Accuracy vs Ground Truth */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Accuracy</span>
          <ShieldCheck className="w-4 h-4 text-indigo-600" />
        </div>
        <div className="text-xl font-bold text-indigo-700 tracking-tight">
          {summary.accuracy.toFixed(1)}%
        </div>
        <div className="text-[11px] text-slate-500 mt-1 font-medium">vs Ground Truth</div>
      </div>

      {/* 6. Throughput */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Throughput</span>
          <Zap className="w-4 h-4 text-violet-600" />
        </div>
        <div className="text-xl font-bold text-violet-700 tracking-tight">
          {summary.throughput_records_sec.toFixed(0)} <span className="text-xs font-normal text-slate-500">rec/s</span>
        </div>
        <div className="text-[11px] text-slate-500 mt-1 font-medium">in {summary.processing_time_sec.toFixed(2)}s</div>
      </div>
    </div>
  );
};
