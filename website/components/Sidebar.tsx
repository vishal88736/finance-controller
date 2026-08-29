"use client";

import React from "react";
import {
  Layers,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  MessageSquare,
  Database,
  FileSpreadsheet,
  ShieldCheck,
  Zap,
  Activity,
  Cpu
} from "lucide-react";

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  totalMatches: number;
  totalExceptions: number;
  accuracy: number;
  totalRecords: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  totalMatches,
  totalExceptions,
  accuracy,
  totalRecords
}) => {
  const navItems = [
    {
      id: "overview",
      label: "Workspace Overview",
      icon: Layers,
      badge: null
    },
    {
      id: "matches",
      label: "Reconciled Pairs",
      icon: CheckCircle2,
      badge: `${totalMatches}`,
      badgeColor: "bg-emerald-100 text-emerald-800"
    },
    {
      id: "exceptions",
      label: "Exceptions & Fees",
      icon: AlertTriangle,
      badge: `${totalExceptions}`,
      badgeColor: "bg-amber-100 text-amber-900"
    },
    {
      id: "evaluation",
      label: "Benchmark Evaluation",
      icon: ShieldCheck,
      badge: `${accuracy.toFixed(1)}%`,
      badgeColor: "bg-indigo-100 text-indigo-800"
    },
    {
      id: "qa",
      label: "QA Copilot Chat",
      icon: MessageSquare,
      badge: "AI",
      badgeColor: "bg-blue-100 text-blue-800"
    }
  ];

  const dataSources = [
    { name: "ERP Internal Ledger", file: "source_a_ledger.csv", count: "200 rows", status: "Active" },
    { name: "Bank Statement", file: "source_b_bank.csv", count: "180 rows", status: "Active" },
    { name: "Gateway Payouts", file: "source_c_payouts.xlsx", count: "40 rows", status: "Active" }
  ];

  return (
    <aside className="w-64 bg-[#08182B] text-slate-300 border-r border-[#1E3A5F] flex flex-col justify-between shrink-0 hidden md:flex min-h-[calc(100vh-4rem)]">
      {/* Navigation */}
      <div className="p-4 space-y-6">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-widest text-slate-400 px-3 mb-2">
            Operations Workspace
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition-all ${
                    isActive
                      ? "bg-[#0066FF] text-white shadow-md shadow-blue-900/30"
                      : "text-slate-300 hover:text-white hover:bg-[#163A66]/60"
                  }`}
                >
                  <div className="flex items-center space-x-2.5 truncate">
                    <Icon className={`w-4 h-4 ${isActive ? "text-white" : "text-slate-400"}`} />
                    <span className="truncate">{item.label}</span>
                  </div>
                  {item.badge && (
                    <span
                      className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                        isActive ? "bg-white/20 text-white" : item.badgeColor
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Ingestion Data Sources */}
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-widest text-slate-400 px-3 mb-2 flex items-center justify-between">
            <span>Data Ingestion Sources</span>
            <span className="text-[9px] bg-[#163A66] text-blue-300 px-1.5 py-0.2 rounded font-mono">
              3 files
            </span>
          </div>
          <div className="space-y-1.5 px-1">
            {dataSources.map((ds, idx) => (
              <div
                key={idx}
                className="bg-[#0C2340]/90 border border-[#1E3A5F] p-2.5 rounded-xl text-[11px] space-y-1"
              >
                <div className="flex items-center justify-between text-slate-200 font-semibold">
                  <span className="truncate">{ds.name}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span className="truncate">{ds.file}</span>
                  <span className="text-slate-300 font-semibold">{ds.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer System Telemetry */}
      <div className="p-4 border-t border-[#1E3A5F] bg-[#061424]/60 space-y-2 text-[11px]">
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5 text-blue-400" />
            <span>Agent Pipeline</span>
          </span>
          <span className="text-emerald-400 font-bold font-mono">LangGraph 8-Node</span>
        </div>
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <Database className="w-3.5 h-3.5 text-emerald-400" />
            <span>Database</span>
          </span>
          <span className="text-slate-200 font-mono">SQLite Local</span>
        </div>
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center space-x-1.5">
            <Activity className="w-3.5 h-3.5 text-amber-400" />
            <span>Throughput</span>
          </span>
          <span className="text-amber-300 font-bold font-mono">622 rec/sec</span>
        </div>
      </div>
    </aside>
  );
};
