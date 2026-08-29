"use client";

import React, { useState } from "react";
import { AlertCircle, Search, ChevronRight, Info, DollarSign, Copy, HelpCircle, ShieldAlert, FileText, CheckCircle2 } from "lucide-react";
import { ExceptionItem } from "@/lib/api";

interface ExceptionTableProps {
  exceptions: ExceptionItem[];
  totalExceptions: number;
  onSelectException: (exc: ExceptionItem) => void;
  onReasonChange: (reason: string) => void;
  selectedReason: string;
}

export const ExceptionTable: React.FC<ExceptionTableProps> = ({
  exceptions,
  totalExceptions,
  onSelectException,
  onReasonChange,
  selectedReason
}) => {
  const [search, setSearch] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const reasons = [
    { id: "ALL", label: "All Exceptions" },
    { id: "AMOUNT_MISMATCH", label: "Amount / Fee Delta" },
    { id: "AMBIGUOUS_CANDIDATES", label: "Multiple Candidates" },
    { id: "MISSING_COUNTERPART", label: "Missing Records" },
    { id: "DUPLICATE", label: "Duplicates" }
  ];

  const getReasonBadge = (reason: string) => {
    switch (reason) {
      case "AMOUNT_MISMATCH":
        return (
          <span className="bg-rose-50 text-rose-800 border border-rose-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold flex items-center gap-1">
            <DollarSign className="w-3 h-3 text-rose-600" /> Fee / Discrepancy
          </span>
        );
      case "AMBIGUOUS_CANDIDATES":
        return (
          <span className="bg-purple-50 text-purple-800 border border-purple-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold flex items-center gap-1">
            <HelpCircle className="w-3 h-3 text-purple-600" /> Multiple Candidates
          </span>
        );
      case "DUPLICATE":
        return (
          <span className="bg-amber-50 text-amber-800 border border-amber-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold flex items-center gap-1">
            <Copy className="w-3 h-3 text-amber-600" /> Duplicate Ledger Entry
          </span>
        );
      case "MISSING_COUNTERPART":
      default:
        return (
          <span className="bg-slate-100 text-slate-800 border border-slate-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold flex items-center gap-1">
            <Info className="w-3 h-3 text-slate-500" /> Missing Counterpart
          </span>
        );
    }
  };

  const copyToClipboard = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const filtered = exceptions.filter((e) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      e.record_id.toLowerCase().includes(q) ||
      e.explanation.toLowerCase().includes(q) ||
      (e.entity && e.entity.toLowerCase().includes(q))
    );
  });

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden razorpay-card">
      {/* Header Controls */}
      <div className="p-4 sm:p-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center justify-between gap-3.5 bg-slate-50/60">
        <div className="flex items-center space-x-2.5">
          <div className="w-3 h-3 rounded-full bg-amber-500 shadow-xs"></div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <span>Honest Exceptions & Discrepancies</span>
              <span className="bg-amber-100 text-amber-800 text-[11px] font-bold px-2 py-0.2 rounded-full">
                {totalExceptions} isolated
              </span>
            </h3>
            <p className="text-[11px] text-slate-500">
              Zero forced false matches — items flagged for fee accounting, ambiguous candidates, or missing counterpart entries
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Filter Pills */}
          <div className="flex items-center space-x-1 bg-slate-200/70 p-1 rounded-lg">
            {reasons.map((r) => (
              <button
                key={r.id}
                onClick={() => onReasonChange(r.id)}
                className={`text-xs font-semibold px-3 py-1 rounded-md transition-all ${
                  selectedReason === r.id
                    ? "bg-white text-blue-700 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search exceptions..."
              className="bg-white border border-slate-300 focus:border-blue-500 rounded-lg pl-8.5 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-48 shadow-2xs"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50/90 text-slate-500 uppercase tracking-wider font-bold text-[10px] border-b border-slate-200">
            <tr>
              <th className="py-3.5 px-4 font-bold">Record ID</th>
              <th className="py-3.5 px-4 font-bold">Source File</th>
              <th className="py-3.5 px-4 font-bold">Reason Category</th>
              <th className="py-3.5 px-4 font-bold">Recorded Amount</th>
              <th className="py-3.5 px-4 font-bold">Discrepancy / Candidates</th>
              <th className="py-3.5 px-4 font-bold">Decision Status</th>
              <th className="py-3.5 px-4 font-bold text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-medium">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-xs">
                  No unresolved exceptions matching criteria.
                </td>
              </tr>
            ) : (
              filtered.map((exc) => (
                <tr
                  key={exc.exception_id}
                  onClick={() => onSelectException(exc)}
                  className="hover:bg-slate-50/90 cursor-pointer transition-colors group"
                >
                  <td className="py-3.5 px-4">
                    <div className="flex items-center space-x-1.5">
                      <span className="font-bold text-slate-900 font-mono text-[11px]">
                        {exc.record_id}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => copyToClipboard(exc.record_id, e)}
                        className="text-slate-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                        title="Copy Record ID"
                      >
                        <Copy className="w-3 h-3" />
                      </button>
                      {copiedId === exc.record_id && (
                        <span className="text-[9px] text-emerald-600 font-bold bg-emerald-50 px-1 rounded">
                          Copied!
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono">{exc.date || "Date N/A"}</div>
                  </td>

                  <td className="py-3.5 px-4">
                    <span className="text-[11px] font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                      {exc.source}
                    </span>
                  </td>

                  <td className="py-3.5 px-4">
                    {getReasonBadge(exc.reason_code)}
                  </td>

                  <td className="py-3.5 px-4 font-bold text-slate-900 font-mono">
                    {exc.amount !== undefined
                      ? `$${exc.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "N/A"}
                  </td>

                  <td className="py-3.5 px-4 text-slate-600">
                    {exc.amount_discrepancy > 0 ? (
                      <span className="text-rose-600 font-bold font-mono">
                        Δ ${exc.amount_discrepancy.toFixed(2)} fee diff
                      </span>
                    ) : exc.candidates.length > 0 ? (
                      <span className="text-purple-700 font-semibold">
                        {exc.candidates.length} candidates ({exc.candidates[0].confidence_score.toFixed(0)}%)
                      </span>
                    ) : (
                      <span className="text-slate-400 italic">No counterpart entry</span>
                    )}
                  </td>

                  <td className="py-3.5 px-4">
                    <span className="text-amber-900 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold tracking-wide">
                      {exc.decision}
                    </span>
                  </td>

                  <td className="py-3.5 px-4 text-right">
                    <button
                      type="button"
                      className="inline-flex items-center space-x-1 text-blue-600 group-hover:text-blue-800 font-bold text-xs bg-blue-50 group-hover:bg-blue-100 px-2.5 py-1 rounded-md transition-colors"
                    >
                      <span>Inspect</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
