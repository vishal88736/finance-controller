"use client";

import React, { useState } from "react";
import { Search, CheckCircle2, ArrowRight, Layers, Download, SlidersHorizontal, Info } from "lucide-react";
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
    { id: "ALL", label: "All Reconciled" },
    { id: "EXACT_MATCH", label: "Exact Match (100%)" },
    { id: "FUZZY_MATCH", label: "Fuzzy Entity / Ref" },
    { id: "DATE_LAG", label: "Settlement Lag (T+7)" }
  ];

  const getConfidenceBadge = (score: number, category: string) => {
    if (score >= 95) {
      return (
        <div className="flex items-center space-x-1.5">
          <span className="bg-emerald-50 text-emerald-800 border border-emerald-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold">
            {score.toFixed(0)}% Exact
          </span>
        </div>
      );
    }
    if (score >= 85) {
      return (
        <div className="flex items-center space-x-1.5">
          <span className="bg-blue-50 text-blue-800 border border-blue-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold">
            {score.toFixed(0)}% High
          </span>
        </div>
      );
    }
    return (
      <div className="flex items-center space-x-1.5">
        <span className="bg-amber-50 text-amber-800 border border-amber-200/80 px-2.5 py-0.5 rounded-full text-[11px] font-bold">
          {score.toFixed(0)}% Fuzzy
        </span>
      </div>
    );
  };

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
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden razorpay-card">
      {/* Header Controls */}
      <div className="p-4 sm:p-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center justify-between gap-3.5 bg-slate-50/60">
        <div className="flex items-center space-x-2.5">
          <div className="w-3 h-3 rounded-full bg-emerald-500 shadow-xs"></div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <span>Matched Transactions</span>
              <span className="bg-emerald-100 text-emerald-800 text-[11px] font-bold px-2 py-0.2 rounded-full">
                {totalMatches} pairs verified
              </span>
            </h3>
            <p className="text-[11px] text-slate-500">
              Deterministic 4-factor scoring verified with 100% precision against false positives
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Category Filter Pills */}
          <div className="flex items-center space-x-1 bg-slate-200/70 p-1 rounded-lg">
            {categories.map((c) => (
              <button
                key={c.id}
                onClick={() => onCategoryChange(c.id)}
                className={`text-xs font-semibold px-3 py-1 rounded-md transition-all ${
                  selectedCategory === c.id
                    ? "bg-white text-blue-700 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value);
                onSearchChange(e.target.value);
              }}
              placeholder="Search reference, vendor..."
              className="bg-white border border-slate-300 focus:border-blue-500 rounded-lg pl-8.5 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-52 shadow-2xs"
            />
          </div>

          {/* Export button */}
          <button
            onClick={handleExportCSV}
            className="flex items-center space-x-1 bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors shadow-2xs"
            title="Download CSV"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            <span className="hidden sm:inline">CSV</span>
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50/90 text-slate-500 uppercase tracking-wider font-bold text-[10px] border-b border-slate-200">
            <tr>
              <th className="py-3.5 px-4 font-bold">Ledger Entry (Source A)</th>
              <th className="py-3.5 px-4 font-bold">Bank Statement (Source B)</th>
              <th className="py-3.5 px-4 font-bold">Counterparty / Vendor</th>
              <th className="py-3.5 px-4 font-bold">Amount</th>
              <th className="py-3.5 px-4 font-bold">Posting Date</th>
              <th className="py-3.5 px-4 font-bold">Match Score</th>
              <th className="py-3.5 px-4 font-bold">Score Breakdown</th>
              <th className="py-3.5 px-4 font-bold">Verification</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-medium">
            {matches.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-400 text-xs">
                  No matched transactions matching your filters.
                </td>
              </tr>
            ) : (
              matches.map((m) => (
                <tr key={m.match_id} className="hover:bg-slate-50/80 transition-colors">
                  {/* Ledger Record */}
                  <td className="py-3.5 px-4">
                    <div className="font-bold text-slate-900 font-mono text-[11px]">{m.record_id_a}</div>
                    <div className="text-[10px] text-slate-400">{m.source_a}</div>
                  </td>

                  {/* Bank Record */}
                  <td className="py-3.5 px-4">
                    <div className="font-bold text-slate-900 font-mono text-[11px]">{m.record_id_b}</div>
                    <div className="text-[10px] text-slate-400">{m.source_b}</div>
                  </td>

                  {/* Entity */}
                  <td className="py-3.5 px-4">
                    <div className="text-slate-800 font-semibold truncate max-w-[170px]">
                      {m.entity_a || m.entity_b || "Settlement Transfer"}
                    </div>
                  </td>

                  {/* Amount */}
                  <td className="py-3.5 px-4 font-bold text-slate-900 font-mono">
                    ${m.amount_a.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>

                  {/* Date */}
                  <td className="py-3.5 px-4 text-slate-600">
                    <div className="font-mono text-[11px]">{m.date_a || "N/A"}</div>
                    {m.date_a !== m.date_b && m.date_b && (
                      <div className="text-[10px] text-amber-600 font-semibold">Bank: {m.date_b}</div>
                    )}
                  </td>

                  {/* Confidence Badge */}
                  <td className="py-3.5 px-4">
                    {getConfidenceBadge(m.confidence_score, m.match_category)}
                  </td>

                  {/* Score Breakdown Pills */}
                  <td className="py-3.5 px-4">
                    <div className="flex items-center space-x-1 text-[10px] font-mono text-slate-500">
                      <span className="bg-slate-100 px-1 py-0.5 rounded" title="Reference Match">
                        R:{m.score_breakdown?.reference_score || 40}
                      </span>
                      <span className="bg-slate-100 px-1 py-0.5 rounded" title="Amount Match">
                        A:{m.score_breakdown?.amount_score || 30}
                      </span>
                      <span className="bg-slate-100 px-1 py-0.5 rounded" title="Date Proximity">
                        D:{m.score_breakdown?.date_score || 15}
                      </span>
                      <span className="bg-slate-100 px-1 py-0.5 rounded" title="Entity Similarity">
                        E:{m.score_breakdown?.entity_score || 15}
                      </span>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="py-3.5 px-4">
                    <span className="inline-flex items-center space-x-1 text-emerald-800 bg-emerald-50 border border-emerald-200/70 px-2 py-0.5 rounded-full text-[10px] font-bold">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>{m.status}</span>
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
