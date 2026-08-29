"use client";

import React, { useState } from "react";
import { Search, Sparkles, ArrowRight, Play, Clock, CheckCircle2 } from "lucide-react";

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
  isRunning,
  recentRuns = [],
  onSelectRecentRun
}) => {
  const suggestions = [
    "Reconcile these financial records and identify anything that doesn't match.",
    "Investigate payment gateway fees and amount discrepancies across sources.",
    "Isolate duplicate entries and missing bank counterpart transactions."
  ];

  return (
    <div className="space-y-4">
      {/* Title section */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-[#0C2340] tracking-tight">
          AI Finance Controller
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Understand, match, and reconcile multi-source financial operations with honest exception intelligence.
        </p>
      </div>

      {/* Main Natural Language Command Bar */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
        <label className="block text-xs font-semibold text-slate-700">
          Reconciliation Instruction
        </label>
        <div className="relative flex items-center">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !isRunning) {
                onExecute();
              }
            }}
            placeholder="Ask anything about your financial data or enter a reconciliation prompt..."
            className="w-full bg-slate-50/70 border border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none rounded-lg px-4 py-3 text-sm text-slate-800 placeholder-slate-400 transition-all pr-32"
          />
          <button
            type="button"
            onClick={onExecute}
            disabled={isRunning || !prompt.trim()}
            className="absolute right-2 top-1.5 bottom-1.5 flex items-center space-x-1.5 bg-[#0066FF] hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold px-4 rounded-md shadow-sm transition-all"
          >
            {isRunning ? (
              <span className="flex items-center space-x-1.5">
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                <span>Processing</span>
              </span>
            ) : (
              <span className="flex items-center space-x-1.5">
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Reconcile</span>
              </span>
            )}
          </button>
        </div>

        {/* Quick prompt suggestion chips */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="text-[11px] font-medium text-slate-400 flex items-center mr-1">
            <Sparkles className="w-3 h-3 text-blue-500 mr-1" /> Quick suggestions:
          </span>
          {suggestions.map((s, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setPrompt(s)}
              className="text-[11px] text-slate-600 bg-slate-100 hover:bg-blue-50 hover:text-blue-700 border border-slate-200 px-2.5 py-1 rounded-full transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Recent runs quick selector */}
      {recentRuns.length > 0 && (
        <div className="flex items-center space-x-2 text-xs text-slate-500 overflow-x-auto py-1">
          <div className="flex items-center space-x-1 font-semibold text-slate-600 shrink-0">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Recent Runs:</span>
          </div>
          {recentRuns.slice(0, 4).map((r) => (
            <button
              key={r.id}
              onClick={() => onSelectRecentRun && onSelectRecentRun(r.id)}
              className="inline-flex items-center space-x-1.5 bg-white border border-slate-200 hover:border-blue-400 px-2.5 py-1 rounded-md text-slate-700 shrink-0 transition-colors"
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              <span className="font-medium truncate max-w-[150px]">{r.user_prompt || r.id}</span>
              <span className="text-emerald-700 font-semibold bg-emerald-50 px-1.5 py-0.2 rounded text-[10px]">
                {r.match_rate}%
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
