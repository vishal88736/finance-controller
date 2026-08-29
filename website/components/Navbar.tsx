"use client";

import React from "react";
import { ShieldCheck, Cpu, RefreshCw, Layers } from "lucide-react";

interface NavbarProps {
  onTriggerDemo: () => void;
  isRunning: boolean;
  totalProcessed?: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  onTriggerDemo,
  isRunning,
  totalProcessed
}) => {
  return (
    <header className="sticky top-0 z-30 bg-[#0C2340] text-white border-b border-[#1E3A5F] shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center shadow-inner">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-lg tracking-tight text-white">
                AI Finance Controller
              </span>
              <span className="text-[10px] font-semibold tracking-wider uppercase bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded border border-blue-400/30">
                Agentic Ops
              </span>
            </div>
            <p className="text-xs text-slate-300">
              Autonomous Multi-Source Reconciliation & Exception Intelligence
            </p>
          </div>
        </div>

        {/* Right side controls */}
        <div className="flex items-center space-x-3">
          <div className="hidden md:flex items-center space-x-2 text-xs text-slate-300 bg-[#08182B] px-3 py-1.5 rounded-md border border-[#1E3A5F]">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="font-medium text-slate-200">LangGraph Pipeline Active</span>
            {totalProcessed ? (
              <span className="text-slate-400">({totalProcessed} recs)</span>
            ) : null}
          </div>

          <button
            onClick={onTriggerDemo}
            disabled={isRunning}
            className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold px-3.5 py-2 rounded-md transition-colors shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRunning ? "animate-spin" : ""}`} />
            <span>{isRunning ? "Reconciling..." : "Run 200+ Batch"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
