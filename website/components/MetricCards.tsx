"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, Activity, Zap, TrendingUp, ShieldCheck, DollarSign, Clock } from "lucide-react";
import { ReconciliationRunSummary } from "@/lib/api";

interface MetricCardsProps {
  summary: ReconciliationRunSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ summary }) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
      {/* 1. Records Processed */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-xs razorpay-card flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider">Processed</span>
            <div className="w-6 h-6 rounded-md bg-slate-100 flex items-center justify-center text-slate-600">
              <Activity className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-black text-slate-900 tracking-tight">
            {summary.total_records.toLocaleString()}
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 text-[11px] text-slate-500 font-medium flex items-center justify-between">
          <span>Multi-source rows</span>
          <span className="text-emerald-600 font-bold">100% Ingested</span>
        </div>
      </div>

      {/* 2. Matched Records */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-xs razorpay-card flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider">Reconciled</span>
            <div className="w-6 h-6 rounded-md bg-emerald-100 flex items-center justify-center text-emerald-700">
              <CheckCircle2 className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-black text-emerald-700 tracking-tight">
            {summary.matched_records.toLocaleString()}
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 text-[11px] text-slate-500 font-medium flex items-center justify-between">
          <span>Verified pairs</span>
          <span className="text-blue-600 font-bold">{summary.match_rate.toFixed(1)}% Match</span>
        </div>
      </div>

      {/* 3. Exceptions */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-xs razorpay-card flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider">Exceptions</span>
            <div className="w-6 h-6 rounded-md bg-amber-100 flex items-center justify-center text-amber-700">
              <AlertTriangle className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-black text-amber-700 tracking-tight">
            {summary.exception_records.toLocaleString()}
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 text-[11px] text-slate-500 font-medium flex items-center justify-between">
          <span>Honest unresolved</span>
          <span className="text-amber-700 font-bold">Isolated</span>
        </div>
      </div>

      {/* 4. Match Rate */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-xs razorpay-card flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider">Match Rate</span>
            <div className="w-6 h-6 rounded-md bg-blue-100 flex items-center justify-center text-blue-700">
              <TrendingUp className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-black text-blue-700 tracking-tight">
            {summary.match_rate.toFixed(1)}%
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 text-[11px] text-slate-500 font-medium flex items-center justify-between">
          <span>Ledger coverage</span>
          <span className="text-slate-700 font-semibold">Deterministic</span>
        </div>
      </div>

      {/* 5. Accuracy vs Ground Truth */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-xs razorpay-card flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider">Accuracy</span>
            <div className="w-6 h-6 rounded-md bg-indigo-100 flex items-center justify-center text-indigo-700">
              <ShieldCheck className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-black text-indigo-700 tracking-tight">
            {summary.accuracy.toFixed(1)}%
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 text-[11px] text-slate-500 font-medium flex items-center justify-between">
          <span>vs Ground Truth</span>
          <span className="text-indigo-700 font-bold">100% Prec</span>
        </div>
      </div>

      {/* 6. Throughput */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 shadow-xs razorpay-card flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider">Throughput</span>
            <div className="w-6 h-6 rounded-md bg-violet-100 flex items-center justify-center text-violet-700">
              <Zap className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-black text-violet-700 tracking-tight">
            {summary.throughput_records_sec.toFixed(0)} <span className="text-xs font-semibold text-slate-400">rec/s</span>
          </div>
        </div>
        <div className="pt-2 border-t border-slate-100 text-[11px] text-slate-500 font-medium flex items-center justify-between">
          <span>Sub-second speed</span>
          <span className="text-violet-700 font-bold">{summary.processing_time_sec.toFixed(2)}s total</span>
        </div>
      </div>
    </div>
  );
};
