"use client";

import React from "react";
import { RefreshCw, Download, Activity } from "lucide-react";

interface NavbarProps {
  onTriggerDemo: () => void;
  isRunning: boolean;
  totalProcessed?: number;
  onExportReport?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  onTriggerDemo,
  isRunning,
  totalProcessed = 380,
  onExportReport
}) => {
  return (
    <header className="bg-white/80 backdrop-blur-xl border-b border-slate-200/80 sticky top-0 z-30">
      <div className="max-w-[1400px] mx-auto px-5 sm:px-8 h-16 flex items-center justify-between">
        {/* Brand & Navigation */}
        <div className="flex items-center gap-3.5">
          <div className="w-9 h-9 bg-gradient-to-br from-blue-600 to-blue-700 rounded-xl flex items-center justify-center text-white font-bold text-sm shadow-md shadow-blue-600/20 transition-transform hover:scale-105 cursor-pointer">
            FC
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="font-semibold text-slate-900">Finance Controller</span>
            <span className="text-slate-300 font-light">/</span>
            <span className="text-slate-500 font-medium hidden sm:inline">Reconciliation Batch #8492</span>
          </div>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-3">
          {/* Status Indicator */}
          <div className="hidden md:flex items-center gap-2 text-xs text-slate-500 bg-slate-50 px-3 py-1.5 rounded-full border border-slate-200/80">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="font-medium">Deterministic Engine Active</span>
          </div>

          {/* Export Button */}
          {onExportReport && (
            <button
              onClick={onExportReport}
              className="flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium px-4 py-2 rounded-lg border border-slate-200 hover:border-slate-300 transition-all cursor-pointer shadow-xs"
            >
              <Download className="w-4 h-4 text-slate-500" />
              <span className="hidden sm:inline">Export</span>
            </button>
          )}

          {/* Run Button */}
          <button
            onClick={onTriggerDemo}
            disabled={isRunning}
            className="flex items-center gap-2 bg-gradient-to-b from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2 rounded-lg transition-all shadow-md shadow-blue-600/20 hover:shadow-lg hover:shadow-blue-600/25 cursor-pointer active:scale-[0.98]"
          >
            <RefreshCw className={`w-4 h-4 ${isRunning ? "animate-spin" : ""}`} />
            <span>{isRunning ? "Processing..." : "Run Reconciliation"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
