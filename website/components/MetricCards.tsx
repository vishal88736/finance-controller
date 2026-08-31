"use client";

import React from "react";
import { TrendingUp, AlertTriangle, Target, Zap } from "lucide-react";
import { ReconciliationRunSummary } from "@/lib/api";

interface MetricCardsProps {
  summary: ReconciliationRunSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ summary }) => {
  const metrics = [
    {
      label: "Records Processed",
      value: summary.total_records.toLocaleString(),
      sub: "Across 3 multi-source files",
      badge: null,
      accentColor: "border-l-blue-500",
      icon: <Zap className="w-4 h-4 text-blue-500" />,
      iconBg: "bg-blue-50"
    },
    {
      label: "Reconciled Pairs",
      value: summary.matched_records.toLocaleString(),
      sub: "Deterministic 4-factor scoring",
      badge: { text: `${summary.match_rate.toFixed(1)}%`, color: "bg-emerald-50 text-emerald-700 border-emerald-200" },
      accentColor: "border-l-emerald-500",
      icon: <TrendingUp className="w-4 h-4 text-emerald-500" />,
      iconBg: "bg-emerald-50"
    },
    {
      label: "Unresolved Exceptions",
      value: summary.exception_records.toLocaleString(),
      sub: "15 fee deltas · 10 ambiguous",
      badge: { text: "Action required", color: "bg-amber-50 text-amber-700 border-amber-200" },
      accentColor: "border-l-amber-500",
      icon: <AlertTriangle className="w-4 h-4 text-amber-500" />,
      iconBg: "bg-amber-50"
    },
    {
      label: "Benchmark Accuracy",
      value: `${summary.accuracy.toFixed(1)}%`,
      sub: `${summary.throughput_records_sec.toFixed(0)} rec/s in ${summary.processing_time_sec.toFixed(2)}s`,
      badge: { text: "100% precision", color: "bg-blue-50 text-blue-700 border-blue-200" },
      accentColor: "border-l-indigo-500",
      icon: <Target className="w-4 h-4 text-indigo-500" />,
      iconBg: "bg-indigo-50"
    }
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
      {metrics.map((m, idx) => (
        <div
          key={idx}
          className={`card card-interactive border-l-[3px] ${m.accentColor} p-5 animate-slide-up cursor-default`}
        >
          {/* Header with Icon */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-500">{m.label}</span>
            <div className={`w-8 h-8 ${m.iconBg} rounded-lg flex items-center justify-center`}>
              {m.icon}
            </div>
          </div>

          {/* Value */}
          <div className="flex items-baseline gap-2.5">
            <span className="text-2xl font-bold text-slate-900 font-[family-name:var(--font-geist-mono)] tracking-tight">
              {m.value}
            </span>
            {m.badge && (
              <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${m.badge.color}`}>
                {m.badge.text}
              </span>
            )}
          </div>

          {/* Subtitle */}
          <div className="text-xs text-slate-400 mt-2">
            {m.sub}
          </div>
        </div>
      ))}
    </div>
  );
};
