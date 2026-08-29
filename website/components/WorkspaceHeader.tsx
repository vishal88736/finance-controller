"use client";

import React from "react";
import { Search, Sparkles, Play, Clock, CheckCircle2, CornerDownLeft, Filter } from "lucide-react";

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
    { label: "Full 200+ Multi-Source Batch", text: "Reconcile these financial records and identify anything that doesn't match." },
    { label: "Payment Gateway Fee Deductions", text: "Investigate payment gateway fees and amount discrepancies across sources." },
    { label: "Bank Settlement Lags & Missing Records", text: "Isolate duplicate entries and missing bank counterpart transactions." }
  ];

  return (
    <div className="space-y-4">
      {/* Title & Subtitle */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-2">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-[#0C2340] tracking-tight">
              Conversational Finance Workspace
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Prompt the autonomous agent to match transactions, detect processing fee deductions, and isolate unresolved exceptions.
          </p>
        </div>
      </div>

      {/* Main Natural Language Command Bar */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 sm:p-5 space-y-3.5 razorpay-card">
        <div className="flex items-center justify-between">
          <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">
            Reconciliation & Analysis Prompt
          </label>
          <span className="hidden sm:flex items-center space-x-1 text-[10px] text-slate-400 font-mono bg-slate-100 px-2 py-0.5 rounded">
            <span>Press</span>
            <span className="font-bold text-slate-700">Enter ↵</span>
            <span>to execute</span>
          </span>
        </div>

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
            placeholder="Ask anything about your financial data or enter a reconciliation instruction..."
            className="w-full bg-slate-50 border border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none rounded-xl px-4 py-3.5 text-sm text-slate-900 placeholder-slate-400 transition-all pr-36 shadow-inner"
          />
          <button
            type="button"
            onClick={onExecute}
            disabled={isRunning || !prompt.trim()}
            className="absolute right-2 top-2 bottom-2 flex items-center space-x-2 bg-[#0066FF] hover:bg-blue-700 active:bg-blue-800 disabled:opacity-40 text-white text-xs font-bold px-4 rounded-lg shadow-sm transition-all"
          >
            {isRunning ? (
              <span className="flex items-center space-x-2">
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                <span>Running...</span>
              </span>
            ) : (
              <span className="flex items-center space-x-1.5">
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Reconcile Batch</span>
              </span>
            )}
          </button>
        </div>

        {/* Quick prompt suggestion chips */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-[11px] font-semibold text-slate-400 flex items-center mr-0.5">
            <Sparkles className="w-3 h-3 text-blue-500 mr-1" /> Presets:
          </span>
          {suggestions.map((s, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setPrompt(s.text)}
              className="text-[11px] font-medium text-slate-700 bg-slate-100/90 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-300 border border-slate-200/80 px-3 py-1.5 rounded-full transition-all"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Recent runs quick selector */}
      {recentRuns.length > 0 && (
        <div className="flex items-center space-x-2 text-xs text-slate-500 overflow-x-auto py-1">
          <div className="flex items-center space-x-1 font-bold text-slate-700 shrink-0">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>Recent Runs:</span>
          </div>
          {recentRuns.slice(0, 5).map((r) => (
            <button
              key={r.id}
              onClick={() => onSelectRecentRun && onSelectRecentRun(r.id)}
              className="inline-flex items-center space-x-2 bg-white border border-slate-200 hover:border-blue-400 hover:shadow-xs px-3 py-1.5 rounded-lg text-slate-700 shrink-0 transition-all"
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
              <span className="font-semibold text-slate-800 truncate max-w-[160px]">
                {r.user_prompt || r.id}
              </span>
              <span className="text-emerald-700 font-bold bg-emerald-50 border border-emerald-200/60 px-1.5 py-0.2 rounded text-[10px]">
                {r.match_rate ? `${r.match_rate.toFixed(1)}%` : "Done"}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
