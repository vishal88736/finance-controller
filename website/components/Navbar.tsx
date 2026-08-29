"use client";

import React from "react";
import { Shield, RefreshCw, Download, FileText, CheckCircle2 } from "lucide-react";

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
    <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        {/* Brand & Breadcrumbs */}
        <div className="flex items-center space-x-3">
          <div className="w-7 h-7 bg-[#0C6CF2] rounded-md flex items-center justify-center text-white font-bold text-xs shadow-xs">
            FC
          </div>
          <div className="flex items-center space-x-2 text-xs">
            <span className="font-semibold text-gray-900">Finance Controller</span>
            <span className="text-gray-300">/</span>
            <span className="text-gray-500 font-medium">Reconciliation Batch #8492</span>
          </div>
        </div>

        {/* Right Actions */}
        <div className="flex items-center space-x-2.5">
          <div className="hidden sm:flex items-center space-x-1.5 text-xs text-gray-500 mr-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Deterministic Engine Active</span>
          </div>

          {onExportReport && (
            <button
              onClick={onExportReport}
              className="flex items-center space-x-1.5 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold px-3 py-1.5 rounded-md border border-gray-300 transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-gray-500" />
              <span>Export CSV</span>
            </button>
          )}

          <button
            onClick={onTriggerDemo}
            disabled={isRunning}
            className="flex items-center space-x-1.5 bg-[#0C6CF2] hover:bg-blue-600 disabled:opacity-50 text-white text-xs font-semibold px-3.5 py-1.5 rounded-md transition-colors shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRunning ? "animate-spin" : ""}`} />
            <span>{isRunning ? "Processing Batch..." : "Run Reconciliation"}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
