"use client";

import React from "react";
import { Layers, CheckCircle2, AlertTriangle, FileWarning, FlaskConical } from "lucide-react";
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

  const cards = [
    {
      id: "documents" as const,
      label: "Documents",
      value: hasDocuments ? documentCount.toLocaleString() : "0",
      sub: hasDocuments ? "Uploaded in this thread" : "Upload documents to begin",
      badge: null as string | null,
      accent: "border-l-blue-500",
      iconBg: "bg-blue-50",
      icon: <Layers className="w-4 h-4 text-blue-500" />,
      clickable: true,
      filter: undefined,
    },
    {
      id: "matches" as const,
      label: "Matched Pairs",
      value: run ? run.matched_count.toLocaleString() : "—",
      sub: run ? `${run.match_rate.toFixed(1)}% match rate` : "No reconciliation run yet",
      badge: run ? `${run.match_rate.toFixed(1)}%` : null,
      accent: "border-l-emerald-500",
      iconBg: "bg-emerald-50",
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-500" />,
      clickable: !!run,
      filter: undefined,
    },
    {
      id: "exceptions" as const,
      label: "Exceptions",
      value: run ? run.exceptions_count.toLocaleString() : "—",
      sub: run && run.exceptions_count > 0 ? "Click to investigate" : run ? "No exceptions raised" : "No reconciliation run yet",
      badge: run && run.exceptions_count > 0 ? "Review" : null,
      accent: "border-l-amber-500",
      iconBg: "bg-amber-50",
      icon: <AlertTriangle className="w-4 h-4 text-amber-500" />,
      clickable: !!run,
      filter: undefined,
    },
    {
      id: "records" as const,
      label: "Total Records",
      value: run ? run.total_records.toLocaleString() : "—",
      sub: run ? `${run.throughput_records_sec.toFixed(0)} rec/s in ${run.processing_time_sec.toFixed(2)}s` : "—",
      badge: null,
      accent: "border-l-indigo-500",
      iconBg: "bg-indigo-50",
      icon: <FileWarning className="w-4 h-4 text-indigo-500" />,
      clickable: false,
      filter: undefined,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        {cards.map((c, idx) => {
          const inner = (
            <div className={`card ${c.clickable ? "card-interactive cursor-pointer" : "cursor-default"} border-l-[3px] ${c.accent} p-5 h-full animate-slide-up`}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-slate-500">{c.label}</span>
                <div className={`w-8 h-8 ${c.iconBg} rounded-lg flex items-center justify-center`}>
                  {c.icon}
                </div>
              </div>
              <div className="flex items-baseline gap-2.5 flex-wrap">
                <span className="text-2xl font-bold text-slate-900 font-[family-name:var(--font-geist-mono)] tracking-tight">
                  {c.value}
                </span>
                {c.badge && (
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                    {c.badge}
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-2">{c.sub}</div>
            </div>
          );
          return c.clickable ? (
            <button
              key={idx}
              onClick={() => onSelect(c.id as any, c.filter)}
              className="text-left w-full focus-visible:outline-none"
              aria-label={`Show ${c.label}`}
            >
              {inner}
            </button>
          ) : (
            <div key={idx}>{inner}</div>
          );
        })}
      </div>

      {/* Evaluation status line — truthful */}
      <div className="card px-4 py-3 flex items-center gap-2.5 text-xs">
        <FlaskConical className="w-4 h-4 text-slate-400 shrink-0" />
        <span className="text-slate-500">
          Evaluation:{" "}
          {run ? (
            run.evaluated ? (
              <span className="text-emerald-700 font-semibold">
                evaluated against authorized benchmark ground truth
              </span>
            ) : (
              <span className="font-medium">
                not evaluated — no authorized ground truth is associated with user-document runs
              </span>
            )
          ) : (
            <span className="font-medium">no run yet</span>
          )}
        </span>
      </div>
    </div>
  );
};
