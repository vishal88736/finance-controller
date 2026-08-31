"use client";

import React, { useState } from "react";
import { Search, ChevronRight, AlertCircle } from "lucide-react";
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
    { id: "AMOUNT_MISMATCH", label: "Fee / Amount" },
    { id: "AMBIGUOUS_CANDIDATES", label: "Multi-Candidate" },
    { id: "MISSING_COUNTERPART", label: "Missing" },
    { id: "DUPLICATE", label: "Duplicates" }
  ];

  const getReasonTag = (reason: string) => {
    switch (reason) {
      case "AMOUNT_MISMATCH":
        return <span className="pill bg-red-50 text-red-700 border border-red-200">Fee / Amount Diff</span>;
      case "AMBIGUOUS_CANDIDATES":
        return <span className="pill bg-purple-50 text-purple-700 border border-purple-200">Multiple Candidates</span>;
      case "DUPLICATE":
        return <span className="pill bg-amber-50 text-amber-700 border border-amber-200">Duplicate Entry</span>;
      case "MISSING_COUNTERPART":
      default:
        return <span className="pill bg-slate-100 text-slate-600 border border-slate-200">Missing Counterpart</span>;
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
    <div className="card overflow-hidden">
      {/* Table Header Controls */}
      <div className="px-5 py-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900">
          Unresolved Exceptions
          <span className="text-slate-400 font-normal ml-1.5">({totalExceptions})</span>
        </h3>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Segment Pills */}
          <div className="segment-group">
            {reasons.map((r) => (
              <button
                key={r.id}
                onClick={() => onReasonChange(r.id)}
                className={`segment-item cursor-pointer ${
                  selectedReason === r.id ? "segment-item-active" : ""
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search exceptions..."
              className="bg-white border border-slate-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none w-48 transition-all"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left fintech-table">
          <thead className="bg-slate-50/80 border-b border-slate-100">
            <tr>
              <th>Record ID</th>
              <th>Source</th>
              <th>Reason Category</th>
              <th>Recorded Amount</th>
              <th>Discrepancy / Candidates</th>
              <th>Decision</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                  <div className="flex flex-col items-center gap-2">
                    <AlertCircle className="w-8 h-8 text-slate-200" />
                    <span>No exceptions matching criteria.</span>
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((exc) => (
                <tr
                  key={exc.exception_id}
                  onClick={() => onSelectException(exc)}
                  className="cursor-pointer group"
                >
                  <td className="font-[family-name:var(--font-geist-mono)] text-xs font-medium text-slate-900">
                    {exc.record_id}
                  </td>

                  <td className="text-xs text-slate-500 font-[family-name:var(--font-geist-mono)]">
                    {exc.source}
                  </td>

                  <td>
                    {getReasonTag(exc.reason_code)}
                  </td>

                  <td className="font-[family-name:var(--font-geist-mono)] text-sm font-bold text-slate-900">
                    {exc.amount !== undefined
                      ? `$${exc.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "N/A"}
                  </td>

                  <td className="font-[family-name:var(--font-geist-mono)] text-xs">
                    {exc.amount_discrepancy > 0 ? (
                      <span className="text-red-600 font-semibold">
                        Δ ${exc.amount_discrepancy.toFixed(2)} fee delta
                      </span>
                    ) : exc.candidates.length > 0 ? (
                      <span className="text-purple-700 font-medium">
                        {exc.candidates.length} candidate pairs
                      </span>
                    ) : (
                      <span className="text-slate-400 italic">No counterpart record</span>
                    )}
                  </td>

                  <td>
                    <span className="pill bg-amber-50 text-amber-700 border border-amber-200">
                      {exc.decision}
                    </span>
                  </td>

                  <td className="text-right">
                    <button
                      type="button"
                      className="text-blue-600 hover:text-blue-700 text-sm font-semibold inline-flex items-center gap-0.5 group-hover:gap-1.5 transition-all cursor-pointer"
                    >
                      <span>Inspect</span>
                      <ChevronRight className="w-4 h-4" />
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
