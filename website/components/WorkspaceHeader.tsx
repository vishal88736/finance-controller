"use client";

import React from "react";
import { Search, Play, CornerDownLeft } from "lucide-react";

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
    <div className="space-y-3">
      {/* Title & Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">
            Multi-Source Financial Reconciliation
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Deterministic candidate matching across internal ledgers, bank feeds, and gateway settlements.
          </p>
        </div>
      </div>

      {/* Clean Natural Search / Prompt Input */}
      <div className="bg-white border border-gray-200 rounded-lg p-2.5 shadow-xs flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <div className="relative flex-1 flex items-center">
          <Search className="w-4 h-4 text-gray-400 absolute left-3" />
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
            className="w-full bg-transparent pl-9 pr-3 py-2 text-xs text-gray-900 placeholder-gray-400 focus:outline-none"
          />
        </div>

        <div className="flex items-center space-x-1.5 shrink-0">
          <button
            type="button"
            onClick={onExecute}
            disabled={isRunning || !prompt.trim()}
            className="w-full sm:w-auto flex items-center justify-center space-x-1.5 bg-[#0C6CF2] hover:bg-blue-600 active:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2 rounded-md transition-colors shadow-xs"
          >
            {isRunning ? (
              <span className="flex items-center space-x-1.5">
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                <span>Reconciling...</span>
              </span>
            ) : (
              <span className="flex items-center space-x-1.5">
                <Play className="w-3 h-3 fill-current" />
                <span>Reconcile</span>
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Preset pills */}
      <div className="flex items-center space-x-1.5 overflow-x-auto text-[11px] pt-0.5">
        <span className="text-gray-400 font-medium text-[11px] shrink-0">Quick presets:</span>
        {suggestions.map((s, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => setPrompt(s.text)}
            className="whitespace-nowrap text-gray-600 hover:text-gray-900 bg-gray-100/80 hover:bg-gray-200/80 px-2.5 py-1 rounded text-[11px] font-medium transition-colors"
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
};
