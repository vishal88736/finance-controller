"use client";

import React from "react";
import { ShieldCheck, RefreshCw, Database, Activity, Download, Zap, Sparkles } from "lucide-react";

interface NavbarProps {
  onTriggerDemo: () => void;
  isRunning: boolean;
  totalProcessed?: number;
  throughput?: number;
  onExportReport?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  onTriggerDemo,
  isRunning,
  totalProcessed = 380,
  throughput = 622.5,
  onExportReport
}) => {
  return (
    <header className="sticky top-0 z-40 bg-[#0C2340] text-white border-b border-[#1E3A5F] shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand & Logo */}
        <div className="flex items-center space-x-3.5">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-blue-500 rounded-xl flex items-center justify-center shadow-md shadow-blue-900/40 border border-blue-400/30">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2.5">
              <span className="font-bold text-base sm:text-lg tracking-tight text-white">
                AI Finance Controller
              </span>
              <span className="text-[10px] font-bold tracking-wider uppercase bg-blue-500/25 text-blue-300 px-2 py-0.5 rounded-full border border-blue-400/30">
                LangGraph 8-Node Ops
              </span>
            </div>
            <p className="text-[11px] text-slate-300 hidden sm:block">
              Multi-Source Financial Reconciliation, Exception Intelligence & Ground-Truth Benchmarking
            </p>
          </div>
        </div>

        {/* Live System Status & Action Controls */}
        <div className="flex items-center space-x-2.5 sm:space-x-3">
          {/* Telemetry pill */}
          <div className="hidden lg:flex items-center space-x-2.5 text-xs text-slate-300 bg-[#08182B] px-3 py-1.5 rounded-lg border border-[#1E3A5F]">
            <div className="flex items-center space-x-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span className="font-medium text-slate-200">SQLite In-Sync</span>
            </div>
            <span className="text-slate-600">|</span>
            <div className="flex items-center space-x-1 text-slate-300 font-mono text-[11px]">
              <Zap className="w-3 h-3 text-amber-400" />
              <span>{throughput > 0 ? `${throughput.toFixed(0)} rec/s` : "Idle"}</span>
            </div>
          </div>

          {/* Export Report button */}
          {onExportReport && (
            <button
              onClick={onExportReport}
              className="hidden sm:flex items-center space-x-1.5 bg-[#163A66] hover:bg-[#1E4E8C] text-slate-200 text-xs font-semibold px-3 py-2 rounded-lg border border-[#23528A] transition-colors shadow-xs"
              title="Export Reconciliation Summary as CSV"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Audit CSV</span>
            </button>
          )}

          {/* Run Reconciliation Trigger */}
          <button
            onClick={onTriggerDemo}
            disabled={isRunning}
            className="flex items-center space-x-2 bg-[#0066FF] hover:bg-blue-500 active:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-lg transition-all shadow-sm shadow-blue-900/50 hover:shadow-md"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRunning ? "animate-spin" : ""}`} />
            <span>{isRunning ? "Reconciling..." : "Run 200+ Batch"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
