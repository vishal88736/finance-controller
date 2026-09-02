"use client";

import React, { useMemo, useState } from "react";
import { Search, ChevronRight, AlertCircle, ArrowUpDown, X, ShieldAlert } from "lucide-react";
import { ExceptionItem } from "@/lib/api";

interface ExceptionInvestigatorProps {
  exceptions: ExceptionItem[];
  totalExceptions: number;
  onReasonChange: (reason: string) => void;
  selectedReason: string;
  onCategoryChange?: (category: string) => void;
  selectedCategory?: string;
  onSearch?: (search: string) => void;
  onOpenRecord?: (recordId: string) => void;
  isLoading?: boolean;
  presetFilter?: { reason?: string; category?: string } | null;
  onClearPreset?: () => void;
}

const REASONS = [
  { id: "ALL", label: "All" },
  { id: "AMOUNT_MISMATCH", label: "Amount mismatch" },
  { id: "AMBIGUOUS_CANDIDATES", label: "Ambiguous" },
  { id: "MISSING_COUNTERPART", label: "Missing counterpart" },
  { id: "DUPLICATE", label: "Duplicate" },
];

const CATEGORIES = [
  { id: "ALL", label: "All severities" },
  { id: "MATERIAL", label: "Material" },
  { id: "NORMAL", label: "Normal" },
];

type SortKey = "discrepancy" | "amount" | "recent";

export const ExceptionInvestigator: React.FC<ExceptionInvestigatorProps> = ({
  exceptions,
  totalExceptions,
  onReasonChange,
  selectedReason,
  onCategoryChange,
  selectedCategory = "ALL",
  onSearch,
  onOpenRecord,
  isLoading = false,
  presetFilter,
  onClearPreset,
}) => {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("discrepancy");
  const [selected, setSelected] = useState<ExceptionItem | null>(null);

  // Client-side filtering/sorting over the fetched page (server does reason/category/search too)
  const filtered = useMemo(() => {
    let rows = exceptions;
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (e) =>
          e.record_id.toLowerCase().includes(q) ||
          (e.entity || "").toLowerCase().includes(q) ||
          e.explanation.toLowerCase().includes(q)
      );
    }
    const sorted = [...rows];
    if (sortKey === "discrepancy") {
      sorted.sort((a, b) => (b.amount_discrepancy || 0) - (a.amount_discrepancy || 0));
    } else if (sortKey === "amount") {
      sorted.sort((a, b) => (b.amount || 0) - (a.amount || 0));
    }
    return sorted;
  }, [exceptions, search, sortKey]);

  const getReasonTag = (reason: string) => {
    switch (reason) {
      case "AMOUNT_MISMATCH":
        return <span className="pill bg-red-50 text-red-700 border border-red-200">Amount mismatch</span>;
      case "AMBIGUOUS_CANDIDATES":
        return <span className="pill bg-purple-50 text-purple-700 border border-purple-200">Ambiguous</span>;
      case "DUPLICATE":
        return <span className="pill bg-amber-50 text-amber-700 border border-amber-200">Duplicate</span>;
      default:
        return <span className="pill bg-slate-100 text-slate-600 border border-slate-200">Missing counterpart</span>;
    }
  };

  return (
    <div className="card overflow-hidden">
      {/* Controls */}
      <div className="px-5 py-4 border-b border-slate-100 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-900">
            Exceptions &amp; Fees
            <span className="text-slate-400 font-normal ml-1.5">({totalExceptions.toLocaleString()})</span>
          </h3>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Sort */}
            <button
              onClick={() =>
                setSortKey((k) => (k === "discrepancy" ? "amount" : k === "amount" ? "recent" : "discrepancy"))
              }
              className="segment-item !bg-white border border-slate-200 hover:border-slate-300 text-slate-600 flex items-center gap-1.5 cursor-pointer"
              title="Toggle sort"
            >
              <ArrowUpDown className="w-3 h-3" />
              Sort: {sortKey}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Severity */}
          {onCategoryChange && (
            <div className="segment-group" role="tablist" aria-label="Severity filter">
              {CATEGORIES.map((c) => (
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
          )}

          {/* Reason */}
          <div className="segment-group" role="tablist" aria-label="Exception type filter">
            {REASONS.map((r) => (
              <button
                key={r.id}
                role="tab"
                aria-selected={selectedReason === r.id}
                onClick={() => onReasonChange(r.id)}
                className={`segment-item cursor-pointer ${selectedReason === r.id ? "segment-item-active" : ""}`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[180px] max-w-xs">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                onSearch?.(e.target.value);
              }}
              placeholder="Search record, entity…"
              className="bg-white border border-slate-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none w-full transition-all"
              aria-label="Search exceptions"
            />
          </div>
        </div>

        {presetFilter && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2.5 py-1 font-medium">
              Filtered: {presetFilter.category === "MATERIAL" ? "material exceptions" : presetFilter.reason || "custom"}
            </span>
            <button
              onClick={onClearPreset}
              className="text-[11px] text-slate-500 hover:text-slate-800 underline cursor-pointer"
            >
              clear
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left fintech-table">
          <thead className="bg-slate-50/80 border-b border-slate-100">
            <tr>
              <th>Record ID</th>
              <th>Source</th>
              <th>Type</th>
              <th>Amount</th>
              <th>Difference</th>
              <th>Severity</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                  Loading exceptions…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                  <div className="flex flex-col items-center gap-2">
                    <AlertCircle className="w-8 h-8 text-slate-200" />
                    <span>No exceptions match the current filters.</span>
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((exc) => (
                <tr key={exc.exception_id} onClick={() => setSelected(exc)} className="cursor-pointer group">
                  <td className="font-[family-name:var(--font-geist-mono)] text-xs font-medium text-slate-900">
                    {exc.record_id}
                  </td>
                  <td className="text-xs text-slate-500 font-[family-name:var(--font-geist-mono)]">{exc.source}</td>
                  <td>{getReasonTag(exc.reason_code)}</td>
                  <td className="font-[family-name:var(--font-geist-mono)] text-sm font-bold text-slate-900">
                    {exc.amount !== undefined && exc.amount !== null
                      ? `$${exc.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "N/A"}
                  </td>
                  <td className="font-[family-name:var(--font-geist-mono)] text-xs">
                    {exc.amount_discrepancy > 0 ? (
                      <span className="text-red-600 font-semibold">Δ ${exc.amount_discrepancy.toFixed(2)}</span>
                    ) : exc.candidates && exc.candidates.length > 0 ? (
                      <span className="text-purple-700 font-medium">{exc.candidates.length} candidates</span>
                    ) : (
                      <span className="text-slate-400 italic">No counterpart</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`pill ${
                        exc.discrepancy_category === "MATERIAL"
                          ? "bg-red-50 text-red-700 border border-red-200"
                          : "bg-slate-100 text-slate-600 border border-slate-200"
                      }`}
                    >
                      {exc.discrepancy_category || "MATERIAL"}
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

      {/* Detail drawer */}
      {selected && (
        <div
          className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-sm animate-fade-in"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <div className="bg-white w-full max-w-lg h-full shadow-2xl flex flex-col animate-slide-in-right" role="dialog" aria-label={`Exception ${selected.record_id}`}>
            <div className="px-6 py-4 border-b border-slate-100 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2.5">
                  <h3 className="text-base font-bold text-slate-900 font-[family-name:var(--font-geist-mono)]">
                    {selected.record_id}
                  </h3>
                  {onOpenRecord && (
                    <button
                      onClick={() => {
                        onOpenRecord(selected.record_id);
                        setSelected(null);
                      }}
                      className="text-[11px] text-blue-600 hover:text-blue-700 underline font-medium cursor-pointer"
                    >
                      Ask copilot about this
                    </button>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Source: <span className="font-medium text-slate-600">{selected.source}</span>
                  <span className="mx-1.5 text-slate-300">•</span>
                  Reason: <span className="font-medium text-slate-600">{selected.reason_code}</span>
                </p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-slate-400 hover:text-slate-600 p-2 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label="Close exception details"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Stat label="Amount" value={selected.amount !== undefined && selected.amount !== null ? `$${selected.amount.toFixed(2)}` : "N/A"} />
                <Stat
                  label="Difference"
                  value={selected.amount_discrepancy > 0 ? `Δ $${selected.amount_discrepancy.toFixed(2)}` : "—"}
                  danger={selected.amount_discrepancy > 0}
                />
                <Stat label="Date" value={selected.date || "—"} />
                <Stat label="Match score" value={`${selected.confidence.toFixed(1)}%`} />
              </div>

              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-slate-800">Explanation</h4>
                <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl text-sm text-slate-700 leading-relaxed">
                  {selected.explanation}
                </div>
              </div>

              {selected.candidates && selected.candidates.length > 0 && (
                <div className="space-y-2.5">
                  <h4 className="text-sm font-semibold text-slate-800">Candidate matches ({selected.candidates.length})</h4>
                  <div className="space-y-2">
                    {selected.candidates.map((cand: any, idx: number) => (
                      <div key={idx} className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-sm text-slate-900 font-[family-name:var(--font-geist-mono)] truncate">
                            Candidate {String.fromCharCode(65 + idx)}: {cand.target_record_id}
                          </span>
                          <span className="pill bg-blue-50 text-blue-700 border border-blue-200 shrink-0">
                            {cand.confidence_score?.toFixed(1) ?? "—"}% score
                          </span>
                        </div>
                        <div className="grid grid-cols-3 gap-3 text-xs font-[family-name:var(--font-geist-mono)] text-slate-500 pt-2 border-t border-slate-200">
                          <div>Amount: <span className="font-bold text-slate-900">${(cand.target_amount ?? 0).toFixed(2)}</span></div>
                          <div>Date: <span className="font-bold text-slate-900">{cand.target_date || "N/A"}</span></div>
                          <div>Δ: <span className={`font-bold ${(cand.amount_diff ?? 0) > 0 ? "text-red-600" : "text-slate-900"}`}>${(cand.amount_diff ?? 0).toFixed(2)}</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Evidence JSON */}
              {selected.evidence && Object.keys(selected.evidence).length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-slate-400" /> Evidence
                  </h4>
                  <pre className="bg-slate-950 text-slate-200 text-[11px] rounded-xl p-4 overflow-x-auto font-mono leading-relaxed">
                    {JSON.stringify(selected.evidence, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; danger?: boolean }> = ({ label, value, danger }) => (
  <div className="bg-slate-50 border border-slate-200 p-3.5 rounded-xl">
    <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wide block">{label}</span>
    <span className={`text-base font-bold font-[family-name:var(--font-geist-mono)] mt-1 block ${danger ? "text-red-600" : "text-slate-900"}`}>
      {value}
    </span>
  </div>
);
