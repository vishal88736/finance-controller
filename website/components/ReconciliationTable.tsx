"use client";

import React, { useState } from "react";
import { Search, Filter, CheckCircle2, ArrowRight, Layers } from "lucide-react";
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

  const getConfidenceBadge = (score: number) => {
    if (score >= 95) {
      return <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded text-[11px] font-semibold">{score.toFixed(0)}% Exact</span>;
    }
    if (score >= 85) {
      return <span className="bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded text-[11px] font-semibold">{score.toFixed(0)}% High</span>;
    }
    return <span className="bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded text-[11px] font-semibold">{score.toFixed(0)}% Fuzzy</span>;
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header Controls */}
      <div className="p-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50/50">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500"></div>
          <h3 className="text-sm font-bold text-slate-900">
            Matched Transactions ({totalMatches})
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Category Filter Pills */}
          <div className="flex items-center space-x-1 bg-slate-200/60 p-1 rounded-lg">
            {categories.map((c) => (
              <button
                key={c.id}
                onClick={() => onCategoryChange(c.id)}
                className={`text-xs font-medium px-2.5 py-1 rounded-md transition-all ${
                  selectedCategory === c.id
                    ? "bg-white text-blue-700 shadow-xs font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value);
                onSearchChange(e.target.value);
              }}
              placeholder="Search reference, entity..."
              className="bg-white border border-slate-300 focus:border-blue-500 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none w-48"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold text-[10px] border-b border-slate-200">
            <tr>
              <th className="py-3 px-4">Ledger Record (A)</th>
              <th className="py-3 px-4">Bank Record (B)</th>
              <th className="py-3 px-4">Entity / Counterparty</th>
              <th className="py-3 px-4">Amount</th>
              <th className="py-3 px-4">Date</th>
              <th className="py-3 px-4">Confidence</th>
              <th className="py-3 px-4">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-medium">
            {matches.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-400 text-xs">
                  No matched transactions matching your filters.
                </td>
              </tr>
            ) : (
              matches.map((m) => (
                <tr key={m.match_id} className="hover:bg-slate-50/80 transition-colors">
                  {/* Ledger Record */}
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-900">{m.record_id_a}</div>
                    <div className="text-[10px] text-slate-400">{m.source_a}</div>
                  </td>

                  {/* Bank Record */}
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-900">{m.record_id_b}</div>
                    <div className="text-[10px] text-slate-400">{m.source_b}</div>
                  </td>

                  {/* Entity */}
                  <td className="py-3 px-4">
                    <div className="text-slate-800 font-medium truncate max-w-[180px]">
                      {m.entity_a || m.entity_b || "Direct Transfer"}
                    </div>
                  </td>

                  {/* Amount */}
                  <td className="py-3 px-4 font-semibold text-slate-900">
                    ${m.amount_a.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>

                  {/* Date */}
                  <td className="py-3 px-4 text-slate-500">
                    <div>{m.date_a || "N/A"}</div>
                    {m.date_a !== m.date_b && m.date_b && (
                      <div className="text-[10px] text-amber-600">Bank: {m.date_b}</div>
                    )}
                  </td>

                  {/* Confidence */}
                  <td className="py-3 px-4">
                    {getConfidenceBadge(m.confidence_score)}
                  </td>

                  {/* Status */}
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center space-x-1 text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-2 py-0.5 rounded text-[10px] font-semibold">
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
