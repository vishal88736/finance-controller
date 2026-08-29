"use client";

import React, { useState } from "react";
import { Search, ChevronRight, DollarSign } from "lucide-react";
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
    { id: "AMOUNT_MISMATCH", label: "Fee / Amount Discrepancy" },
    { id: "AMBIGUOUS_CANDIDATES", label: "Multiple Candidates" },
    { id: "MISSING_COUNTERPART", label: "Missing Records" },
    { id: "DUPLICATE", label: "Duplicate Bookings" }
  ];

  const getReasonTag = (reason: string) => {
    switch (reason) {
      case "AMOUNT_MISMATCH":
        return <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded text-[11px] font-medium">Fee / Amount Diff</span>;
      case "AMBIGUOUS_CANDIDATES":
        return <span className="text-purple-700 bg-purple-50 px-2 py-0.5 rounded text-[11px] font-medium">Multiple Candidates</span>;
      case "DUPLICATE":
        return <span className="text-amber-700 bg-amber-50 px-2 py-0.5 rounded text-[11px] font-medium">Duplicate Entry</span>;
      case "MISSING_COUNTERPART":
      default:
        return <span className="text-gray-700 bg-gray-100 px-2 py-0.5 rounded text-[11px] font-medium">Missing Counterpart</span>;
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
    <div className="bg-white border border-gray-200 rounded-lg shadow-xs overflow-hidden">
      {/* Table Header Controls */}
      <div className="p-3.5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-50/50">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold text-gray-900">
            Unresolved Exceptions & Discrepancies ({totalExceptions})
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Segment Pills */}
          <div className="flex items-center space-x-1 bg-gray-200/70 p-0.5 rounded-md">
            {reasons.map((r) => (
              <button
                key={r.id}
                onClick={() => onReasonChange(r.id)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded transition-all ${
                  selectedReason === r.id
                    ? "bg-white text-gray-900 font-semibold shadow-2xs"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search exceptions..."
              className="bg-white border border-gray-300 focus:border-blue-500 rounded-md pl-8 pr-2.5 py-1 text-xs text-gray-900 placeholder-gray-400 focus:outline-none w-44"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left fintech-table">
          <thead className="bg-gray-50 text-gray-500 uppercase tracking-wider text-[10px] border-b border-gray-200">
            <tr>
              <th className="py-2.5 px-3.5 font-semibold">Record ID</th>
              <th className="py-2.5 px-3.5 font-semibold">Source</th>
              <th className="py-2.5 px-3.5 font-semibold">Reason Category</th>
              <th className="py-2.5 px-3.5 font-semibold">Recorded Amount</th>
              <th className="py-2.5 px-3.5 font-semibold">Discrepancy / Candidates</th>
              <th className="py-2.5 px-3.5 font-semibold">Decision</th>
              <th className="py-2.5 px-3.5 font-semibold text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 font-normal">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-gray-400 text-xs">
                  No exceptions matching criteria.
                </td>
              </tr>
            ) : (
              filtered.map((exc) => (
                <tr
                  key={exc.exception_id}
                  onClick={() => onSelectException(exc)}
                  className="hover:bg-gray-50/80 cursor-pointer transition-colors"
                >
                  <td className="py-2.5 px-3.5 font-mono text-[11px] font-medium text-gray-900">
                    {exc.record_id}
                  </td>

                  <td className="py-2.5 px-3.5 text-[11px] text-gray-500 font-mono">
                    {exc.source}
                  </td>

                  <td className="py-2.5 px-3.5">
                    {getReasonTag(exc.reason_code)}
                  </td>

                  <td className="py-2.5 px-3.5 font-mono text-xs font-bold text-gray-900">
                    {exc.amount !== undefined
                      ? `$${exc.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "N/A"}
                  </td>

                  <td className="py-2.5 px-3.5 font-mono text-xs">
                    {exc.amount_discrepancy > 0 ? (
                      <span className="text-rose-600 font-semibold">
                        Δ ${exc.amount_discrepancy.toFixed(2)} fee delta
                      </span>
                    ) : exc.candidates.length > 0 ? (
                      <span className="text-purple-700 font-medium">
                        {exc.candidates.length} candidate pairs
                      </span>
                    ) : (
                      <span className="text-gray-400 italic">No counterpart record</span>
                    )}
                  </td>

                  <td className="py-2.5 px-3.5">
                    <span className="text-amber-800 bg-amber-50 px-2 py-0.5 rounded text-[10px] font-semibold">
                      {exc.decision}
                    </span>
                  </td>

                  <td className="py-2.5 px-3.5 text-right">
                    <button
                      type="button"
                      className="text-[#0C6CF2] hover:text-blue-700 text-xs font-semibold inline-flex items-center"
                    >
                      <span>Inspect</span>
                      <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
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
