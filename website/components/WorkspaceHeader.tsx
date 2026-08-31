"use client";

import React from "react";
import { Search, Play, Sparkles } from "lucide-react";

interface WorkspaceHeaderProps {
  prompt: string;
  setPrompt: (p: string) => void;
  onExecute: () => void;
  isRunning: boolean;
  recentRuns?: Array<{ id: string; user_prompt?: string; match_rate: number; created_at?: string }>;
  onSelectRecentRun?: (runId: string) => void;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  prompt,
  setPrompt,
  onExecute,
  isRunning
}) => {
  const suggestions = [
    { label: "Full 200+ Benchmark Batch", text: "Reconcile these financial records and identify anything that doesn't match." },
    { label: "Payment Gateway Fee Deductions", text: "Investigate payment gateway fees and amount discrepancies across sources." },
    { label: "Bank Settlement Lags & Missing Records", text: "Isolate duplicate entries and missing bank counterpart transactions." }
  ];

  return (
    <div className="space-y-4">
      {/* Title & Description */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
          Multi-Source Financial Reconciliation
        </h1>
        <p className="text-sm text-slate-500 max-w-2xl">
          Deterministic candidate matching across internal ledgers, bank feeds, and gateway settlements.
        </p>
      </div>

      {/* Command Input Bar */}
      <div className="card !rounded-xl overflow-hidden">
        <div className="flex flex-col sm:flex-row items-stretch">
          {/* Search Input */}
          <div className="relative flex-1 flex items-center border-b sm:border-b-0 sm:border-r border-slate-100">
            <Sparkles className="w-4 h-4 text-blue-500 absolute left-4 pointer-events-none" />
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isRunning) {
                  onExecute();
                }
              }}
              placeholder="Type a natural language instruction (e.g. 'Reconcile these files and isolate fee deltas')..."
              className="w-full bg-transparent pl-11 pr-4 py-3.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none"
            />
          </div>

          {/* Execute Button */}
          <button
            type="button"
            onClick={onExecute}
            disabled={isRunning || !prompt.trim()}
            className="flex items-center justify-center gap-2 bg-gradient-to-b from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-6 py-3.5 transition-all cursor-pointer active:scale-[0.98] m-1.5 rounded-lg shadow-sm"
          >
            {isRunning ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                <span>Reconciling...</span>
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Reconcile</span>
                <kbd className="hidden sm:inline-flex items-center text-[10px] font-mono text-blue-200 bg-blue-700/30 px-1.5 py-0.5 rounded">↵</kbd>
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Preset Quick-Select Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-0.5">
        <span className="text-xs text-slate-400 font-medium shrink-0">Quick presets:</span>
        {suggestions.map((s, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => setPrompt(s.text)}
            className="whitespace-nowrap text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer shadow-xs"
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
};
