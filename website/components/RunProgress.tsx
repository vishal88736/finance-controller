"use client";

import React from "react";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";

interface RunProgressProps {
  currentStepIndex: number;
  steps?: string[];
}

const DEFAULT_STEPS = [
  "Analyze request & constraints",
  "Ingest multi-source documents",
  "Normalize dates & currencies",
  "Generate candidate pairs",
  "Deterministic match scoring",
  "Verify pairwise consistency",
  "Classify honest exceptions",
  "Calculate ground-truth metrics"
];

export const RunProgress: React.FC<RunProgressProps> = ({
  currentStepIndex,
  steps = DEFAULT_STEPS
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          LangGraph Agent Execution Pipeline
        </h4>
        <span className="text-xs font-semibold text-blue-600">
          Step {Math.min(currentStepIndex + 1, steps.length)} of {steps.length}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {steps.map((step, idx) => {
          const isDone = idx < currentStepIndex;
          const isCurrent = idx === currentStepIndex;

          return (
            <div
              key={idx}
              className={`p-2.5 rounded-lg border text-xs transition-all ${
                isDone
                  ? "bg-emerald-50/70 border-emerald-200 text-emerald-900"
                  : isCurrent
                  ? "bg-blue-50 border-blue-300 text-blue-900 ring-2 ring-blue-500/20"
                  : "bg-slate-50 border-slate-200 text-slate-400"
              }`}
            >
              <div className="flex items-center space-x-1.5 mb-1">
                {isDone ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                ) : isCurrent ? (
                  <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />
                ) : (
                  <Circle className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                )}
                <span className="font-bold text-[11px]">0{idx + 1}</span>
              </div>
              <p className="text-[11px] leading-tight font-medium line-clamp-2">
                {step}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
