"use client";

import React from "react";
import { CheckCircle2, Circle, Loader2, Cpu, ArrowRight } from "lucide-react";

interface RunProgressProps {
  currentStepIndex: number;
  steps?: Array<{ title: string; desc: string }>;
}

const DEFAULT_NODES = [
  { title: "Analyze Request", desc: "Extract intent & constraints" },
  { title: "Load Documents", desc: "Multi-source file ingestion" },
  { title: "Normalize Records", desc: "ISO dates, amounts & tokens" },
  { title: "Generate Candidates", desc: "Pairwise candidate vectors" },
  { title: "Match Records", desc: "Deterministic multi-factor score" },
  { title: "Verify Consistency", desc: "1-to-1 pairwise validation" },
  { title: "Classify Exceptions", desc: "Honest exception rationale" },
  { title: "Evaluate Benchmark", desc: "Ground-truth precision & metrics" }
];

export const RunProgress: React.FC<RunProgressProps> = ({
  currentStepIndex,
  steps = DEFAULT_NODES
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3.5 razorpay-card">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Cpu className="w-4 h-4 text-blue-600" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            LangGraph StateGraph Execution Pipeline
          </h4>
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-[11px] font-mono text-slate-500">
            Node {Math.min(currentStepIndex + 1, steps.length)} of {steps.length}
          </span>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
            currentStepIndex >= steps.length - 1
              ? "bg-emerald-100 text-emerald-800"
              : "bg-blue-100 text-blue-800 animate-pulse"
          }`}>
            {currentStepIndex >= steps.length - 1 ? "Graph Completed" : "Active Flow"}
          </span>
        </div>
      </div>

      {/* Grid of 8 Nodes */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {steps.map((node, idx) => {
          const isDone = idx < currentStepIndex || currentStepIndex >= steps.length - 1;
          const isCurrent = idx === currentStepIndex && currentStepIndex < steps.length - 1;

          return (
            <div
              key={idx}
              className={`p-3 rounded-xl border text-xs transition-all flex flex-col justify-between ${
                isDone
                  ? "bg-emerald-50/60 border-emerald-200 text-emerald-950 shadow-2xs"
                  : isCurrent
                  ? "bg-blue-50 border-blue-400 text-blue-950 ring-2 ring-blue-500/20 shadow-xs"
                  : "bg-slate-50 border-slate-200 text-slate-400"
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono font-bold text-[10px] opacity-75">N{idx + 1}</span>
                  {isDone ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  ) : isCurrent ? (
                    <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />
                  ) : (
                    <Circle className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                  )}
                </div>
                <p className="text-[11px] leading-snug font-bold line-clamp-1">
                  {node.title}
                </p>
              </div>
              <p className="text-[10px] opacity-70 mt-1 line-clamp-1">
                {node.desc}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
