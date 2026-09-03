"use client";

import React, { useState } from "react";
import { Search, Download, CheckCircle2 } from "lucide-react";
import { MatchItem } from "@/lib/api";

interface ResultsViewProps {
  matches: MatchItem[];
  totalMatches: number;
  onSearchChange: (query: string) => void;
  onCategoryChange: (cat: string) => void;
  selectedCategory: string;
  isLoading?: boolean;
}

const categories = [
  { id: "ALL", label: "All" },
  { id: "EXACT_MATCH", label: "Exact" },
  { id: "TOLERANCE_MATCH", label: "Tolerance" },
  { id: "FUZZY_MATCH", label: "Fuzzy" },
];

export const ResultsView: React.FC<ResultsViewProps> = ({
  matches,
  totalMatches,
  onSearchChange,
  onCategoryChange,
  selectedCategory,
  isLoading = false,
}) => {
  const [searchInput, setSearchInput] = useState("");

  const handleExportCSV = () => {
    if (matches.length === 0) return;
    const headers =
      "Match ID,Record A,Record B,Source A,Source B,Amount A,Amount B,Entity,Date A,Date B,Confidence,Category\n";
    const rows = matches
      .map(
        (m) =>
          `"${m.match_id}","${m.record_id_a}","${m.record_id_b}","${m.source_a}","${m.source_b}",${m.amount_a},${m.amount_b},"${m.entity_a || m.entity_b || ""}","${m.date_a || ""}","${m.date_b || ""}",${m.confidence_score},"${m.match_category}"`
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
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900">
          Reconciled Pairs
          <span className="text-slate-400 font-normal ml-1.5">({totalMatches.toLocaleString()})</span>
        </h3>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="segment-group" role="tablist" aria-label="Match category filter">
            {categories.map((c) => (
              <button
                key={c.id}
                role="tab"
                aria-selected={selectedCategory === c.id}
                onClick={() => onCategoryChange(c.id)}
                className={`segment-item cursor-pointer ${selectedCategory === c.id ? "segment-item-active" : ""}`}
              >
                {c.label}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value);
                onSearchChange(e.target.value);
              }}
              placeholder="Search reference, vendor…"
              className="bg-white border border-slate-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none w-52 transition-all"
              aria-label="Search matched pairs"
            />
          </div>

          <button
            onClick={handleExportCSV}
            disabled={matches.length === 0}
            className="flex items-center gap-1.5 bg-white hover:bg-slate-50 disabled:opacity-40 text-slate-600 border border-slate-200 hover:border-slate-300 text-sm font-medium px-3 py-2 rounded-lg transition-all cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-slate-400" />
            <span>CSV</span>
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left fintech-table">
          <thead className="bg-slate-50/80 border-b border-slate-100">
            <tr>
              <th>Record A</th>
              <th>Record B</th>
              <th>Counterparty</th>
              <th>Amount</th>
              <th>Date</th>
              <th>Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                  Loading matched pairs…
                </td>
              </tr>
            ) : matches.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                  <div className="flex flex-col items-center gap-2">
                    <CheckCircle2 className="w-8 h-8 text-slate-200" />
                    <span>No matched pairs match your filters.</span>
                  </div>
                </td>
              </tr>
            ) : (
              matches.map((m) => (
                <tr key={m.match_id}>
                  <td className="font-[family-name:var(--font-geist-mono)] text-xs font-medium text-slate-900">
                    {m.record_id_a}
                  </td>
                  <td className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-500">
                    {m.record_id_b}
                  </td>
                  <td className="text-slate-800 text-sm font-medium truncate max-w-[200px]">
                    {m.entity_a || m.entity_b || "—"}
                  </td>
                  <td className="font-[family-name:var(--font-geist-mono)] text-sm font-bold text-slate-900">
                    ${m.amount_a.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="text-slate-500 font-[family-name:var(--font-geist-mono)] text-xs">
                    {m.date_a || "N/A"}
                  </td>
                  <td className="font-[family-name:var(--font-geist-mono)] text-xs">
                    <div className="flex items-center gap-1.5">
                      <div className="w-10 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${m.confidence_score}%` }} />
                      </div>
                      <span className="font-semibold text-slate-700">{m.confidence_score.toFixed(0)}%</span>
                    </div>
                  </td>
                  <td>
                    <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200">
                      {m.status === "VERIFIED" ? "Verified" : "Matched"}
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
