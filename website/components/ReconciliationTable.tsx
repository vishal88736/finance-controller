"use client";

import React, { useState } from "react";
import { Search, Download, CheckCircle2 } from "lucide-react";
import { MatchItem } from "@/lib/api";

interface ReconciliationTableProps {
  matches: MatchItem[];
  totalMatches: number;
  onSearchChange: (query: string) => void;
  onCategoryChange: (cat: string) => void;
  selectedCategory: string;
}

export const ReconciliationTable: React.FC<ReconciliationTableProps> = ({
  matches,
  totalMatches,
  onSearchChange,
  onCategoryChange,
  selectedCategory
}) => {
  const [searchInput, setSearchInput] = useState("");

  const categories = [
    { id: "ALL", label: "All Matches" },
    { id: "EXACT_MATCH", label: "Exact (100%)" },
    { id: "FUZZY_MATCH", label: "Fuzzy Entity" },
    { id: "DATE_LAG", label: "Settlement Lag" }
  ];

  const handleExportCSV = () => {
    if (matches.length === 0) return;
    const headers = "Match ID,Record A,Record B,Source A,Source B,Amount A,Amount B,Entity,Date A,Date B,Confidence,Category\n";
    const rows = matches
      .map(
        (m) =>
          `"${m.match_id}","${m.record_id_a}","${m.record_id_b}","${m.source_a}","${m.source_b}",${m.amount_a},${m.amount_b},"${m.entity_a || m.entity_b || ''}","${m.date_a || ''}","${m.date_b || ''}",${m.confidence_score},"${m.match_category}"`
      )
      .join("\n");
    const blob = new Blob([headers + rows], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `matched_records_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-xs overflow-hidden">
      {/* Table Header Controls */}
      <div className="p-3.5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-gray-50/50">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold text-gray-900">
            Reconciled Transactions ({totalMatches})
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Segment Pills */}
          <div className="flex items-center space-x-1 bg-gray-200/70 p-0.5 rounded-md">
            {categories.map((c) => (
              <button
                key={c.id}
                onClick={() => onCategoryChange(c.id)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded transition-all ${
                  selectedCategory === c.id
                    ? "bg-white text-gray-900 font-semibold shadow-2xs"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value);
                onSearchChange(e.target.value);
              }}
              placeholder="Search reference, vendor..."
              className="bg-white border border-gray-300 focus:border-blue-500 rounded-md pl-8 pr-2.5 py-1 text-xs text-gray-900 placeholder-gray-400 focus:outline-none w-48"
            />
          </div>

          {/* Export CSV */}
          <button
            onClick={handleExportCSV}
            className="flex items-center space-x-1 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 text-xs font-medium px-2.5 py-1 rounded-md transition-colors"
          >
            <Download className="w-3 h-3 text-gray-500" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* Clean Fintech Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left fintech-table">
          <thead className="bg-gray-50 text-gray-500 uppercase tracking-wider text-[10px] border-b border-gray-200">
            <tr>
              <th className="py-2.5 px-3.5 font-semibold">Ledger Entry</th>
              <th className="py-2.5 px-3.5 font-semibold">Bank Statement</th>
              <th className="py-2.5 px-3.5 font-semibold">Counterparty</th>
              <th className="py-2.5 px-3.5 font-semibold">Amount</th>
              <th className="py-2.5 px-3.5 font-semibold">Posting Date</th>
              <th className="py-2.5 px-3.5 font-semibold">Score</th>
              <th className="py-2.5 px-3.5 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 font-normal">
            {matches.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-gray-400 text-xs">
                  No matched transactions matching your filters.
                </td>
              </tr>
            ) : (
              matches.map((m) => (
                <tr key={m.match_id} className="hover:bg-gray-50/80 transition-colors">
                  {/* Ledger Record */}
                  <td className="py-2.5 px-3.5 font-mono text-[11px] text-gray-900 font-medium">
                    {m.record_id_a}
                  </td>

                  {/* Bank Record */}
                  <td className="py-2.5 px-3.5 font-mono text-[11px] text-gray-600">
                    {m.record_id_b}
                  </td>

                  {/* Entity */}
                  <td className="py-2.5 px-3.5 text-gray-800 text-xs font-medium truncate max-w-[180px]">
                    {m.entity_a || m.entity_b || "Settlement Transfer"}
                  </td>

                  {/* Amount */}
                  <td className="py-2.5 px-3.5 font-mono text-xs font-bold text-gray-900">
                    ${m.amount_a.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>

                  {/* Date */}
                  <td className="py-2.5 px-3.5 text-gray-500 font-mono text-[11px]">
                    {m.date_a || "N/A"}
                  </td>

                  {/* Score */}
                  <td className="py-2.5 px-3.5 font-mono text-[11px]">
                    <span className="font-semibold text-gray-800">{m.confidence_score.toFixed(0)}%</span>
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-3.5">
                    <span className="inline-flex items-center text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded text-[10px] font-semibold">
                      Matched
                    </span>
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
