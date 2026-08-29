"use client";

import React, { useState } from "react";
import { AlertCircle, Search, ChevronRight, Info, DollarSign, Copy, HelpCircle } from "lucide-react";
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

  const reasons = [
    { id: "ALL", label: "All Exceptions" },
    { id: "AMOUNT_MISMATCH", label: "Amount Discrepancy" },
    { id: "AMBIGUOUS_CANDIDATES", label: "Ambiguous Candidates" },
    { id: "MISSING_COUNTERPART", label: "Missing Records" },
    { id: "DUPLICATE", label: "Duplicates" }
  ];

  const getReasonBadge = (reason: string) => {
    switch (reason) {
      case "AMOUNT_MISMATCH":
        return <span className="bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 rounded text-[11px] font-semibold flex items-center gap-1"><DollarSign className="w-3 h-3"/> Fee / Amount Diff</span>;
      case "AMBIGUOUS_CANDIDATES":
        return <span className="bg-purple-50 text-purple-700 border border-purple-200 px-2 py-0.5 rounded text-[11px] font-semibold flex items-center gap-1"><HelpCircle className="w-3 h-3"/> Multiple Candidates</span>;
      case "DUPLICATE":
        return <span className="bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded text-[11px] font-semibold flex items-center gap-1"><Copy className="w-3 h-3"/> Duplicate Entry</span>;
      case "MISSING_COUNTERPART":
      default:
        return <span className="bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded text-[11px] font-semibold flex items-center gap-1"><Info className="w-3 h-3"/> Missing Record</span>;
    }
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
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header Controls */}
      <div className="p-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50/50">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500"></div>
          <h3 className="text-sm font-bold text-slate-900">
            Honest Exceptions & Discrepancies ({totalExceptions})
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Filter Pills */}
          <div className="flex items-center space-x-1 bg-slate-200/60 p-1 rounded-lg">
            {reasons.map((r) => (
              <button
                key={r.id}
                onClick={() => onReasonChange(r.id)}
                className={`text-xs font-medium px-2.5 py-1 rounded-md transition-all ${
                  selectedReason === r.id
                    ? "bg-white text-blue-700 shadow-xs font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search exceptions..."
              className="bg-white border border-slate-300 focus:border-blue-500 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-44"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold text-[10px] border-b border-slate-200">
            <tr>
              <th className="py-3 px-4">Record ID</th>
              <th className="py-3 px-4">Source</th>
              <th className="py-3 px-4">Reason Category</th>
              <th className="py-3 px-4">Recorded Amount</th>
              <th className="py-3 px-4">Discrepancy / Candidates</th>
              <th className="py-3 px-4">Decision</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-medium">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-400 text-xs">
                  No unresolved exceptions matching criteria.
                </td>
              </tr>
            ) : (
              filtered.map((exc) => (
                <tr
                  key={exc.exception_id}
                  onClick={() => onSelectException(exc)}
                  className="hover:bg-slate-50/90 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-900">{exc.record_id}</div>
                    <div className="text-[10px] text-slate-400">{exc.date || "Date N/A"}</div>
                  </td>

                  <td className="py-3 px-4">
                    <span className="text-[11px] font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                      {exc.source}
                    </span>
                  </td>

                  <td className="py-3 px-4">
                    {getReasonBadge(exc.reason_code)}
                  </td>

                  <td className="py-3 px-4 font-semibold text-slate-900">
                    {exc.amount !== undefined ? `$${exc.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "N/A"}
                  </td>

                  <td className="py-3 px-4 text-slate-600">
                    {exc.amount_discrepancy > 0 ? (
                      <span className="text-rose-600 font-semibold">
                        Δ ${exc.amount_discrepancy.toFixed(2)}
                      </span>
                    ) : exc.candidates.length > 0 ? (
                      <span className="text-purple-600 font-medium">
                        {exc.candidates.length} candidates ({exc.candidates[0].confidence_score.toFixed(0)}%)
                      </span>
                    ) : (
                      <span className="text-slate-400 italic">No counterpart entry</span>
                    )}
                  </td>

                  <td className="py-3 px-4">
                    <span className="text-amber-800 bg-amber-50 border border-amber-200/80 px-2 py-0.5 rounded text-[10px] font-bold">
                      {exc.decision}
                    </span>
                  </td>

                  <td className="py-3 px-4 text-right">
                    <button
                      type="button"
                      className="inline-flex items-center space-x-1 text-blue-600 hover:text-blue-800 font-semibold text-xs"
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
