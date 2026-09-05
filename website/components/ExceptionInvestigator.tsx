"use client";

import React, { useMemo, useState, useEffect, useRef } from "react";
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
  { id: "MISSING_COUNTERPART", label: "Missing counterpart" },
  { id: "UNRECORDED_TRANSACTION", label: "Unrecorded" },
  { id: "DUPLICATE_TRANSACTION", label: "Duplicate" },
  { id: "AMBIGUOUS_CANDIDATE_CONFLICT", label: "Ambiguous" },
  { id: "CURRENCY_MISMATCH", label: "Currency mismatch" },
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
  const drawerCloseRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Drawer focus: focus close on open, Escape to close, return focus to trigger.
  useEffect(() => {
    if (!selected) return;
    triggerRef.current = document.activeElement as HTMLElement | null;
    drawerCloseRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      triggerRef.current?.focus?.();
    };
  }, [selected]);

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
      case "AMBIGUOUS_CANDIDATE_CONFLICT":
        return <span className="pill bg-purple-50 text-purple-700 border border-purple-200">Ambiguous</span>;
      case "DUPLICATE_TRANSACTION":
        return <span className="pill bg-amber-50 text-amber-700 border border-amber-200">Duplicate</span>;
      case "UNRECORDED_TRANSACTION":
        return <span className="pill bg-blue-50 text-blue-700 border border-blue-200">Unrecorded</span>;
      case "ONE_DISAGREES":
        return <span className="pill bg-orange-50 text-orange-700 border border-orange-200">One Disagrees</span>;
      case "ALL_DISAGREE":
        return <span className="pill bg-red-50 text-red-700 border border-red-200">All Disagree</span>;
      case "CURRENCY_MISMATCH":
        return <span className="pill bg-pink-50 text-pink-700 border border-pink-200">Currency Mismatch</span>;
      case "MISSING_SETTLEMENT":
      case "MISSING_PAYOUT":
        return <span className="pill bg-slate-50 text-slate-700 border border-slate-200">Missing Settlement</span>;
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
              aria-label={`Sort exceptions by ${sortKey}. Activate to change sort.`}
            >
              <ArrowUpDown className="w-3 h-3" aria-hidden="true" />
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
          <div className="segment-group scroll-x-afford max-w-full" role="tablist" aria-label="Exception type filter">
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
      <div className="overflow-x-auto scroll-x-afford">
        <table className="w-full text-left fintech-table">
          <thead className="bg-slate-50/80 border-b border-slate-100">
            <tr>
              <th scope="col">Record ID</th>
              <th scope="col">Source</th>
              <th scope="col">Type</th>
              <th scope="col">Amount</th>
              <th scope="col">Difference</th>
              <th scope="col">Severity</th>
              <th scope="col" className="text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="py-6 px-5">
                  <div className="space-y-2" aria-label="Loading exceptions">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="skeleton h-10 w-full" />
                    ))}
                  </div>
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                  <div className="flex flex-col items-center gap-2">
                    <AlertCircle className="w-8 h-8 text-slate-200" />
                    <span>No exceptions match the current filters.</span>
                    <span className="text-xs text-slate-400">Try clearing the severity or reason filter.</span>
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((exc) => (
                <tr key={exc.exception_id} onClick={() => setSelected(exc)} className="cursor-pointer group">
                  <td className="mono-fin text-xs font-medium text-slate-900">
                    {exc.record_id}
                  </td>
                  <td className="text-xs text-slate-500 mono-fin">{exc.source}</td>
                  <td>{getReasonTag(exc.reason_code)}</td>
                  <td className="mono-fin text-sm font-bold text-slate-900">
                    {exc.amount !== undefined && exc.amount !== null
                      ? `$${exc.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "N/A"}
                  </td>
                  <td className="mono-fin text-xs">
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
                  <h3 className="text-base font-bold text-slate-900 mono-fin">
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
                ref={drawerCloseRef}
                onClick={() => setSelected(null)}
                className="text-slate-400 hover:text-slate-600 p-2 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label="Close exception details"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              {/* ── SECTION 1: WHY THIS IS AN EXCEPTION ── */}
              <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-200/80 pb-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Why This is an Exception
                  </h4>
                  <span
                    className={`pill ${
                      selected.discrepancy_category === "MATERIAL"
                        ? "bg-red-50 text-red-700 border border-red-200"
                        : "bg-slate-100 text-slate-600 border border-slate-200"
                    }`}
                  >
                    {selected.discrepancy_category || "MATERIAL"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-slate-400 block uppercase tracking-wide text-[10px] font-semibold">
                      Transaction Record
                    </span>
                    <span className="font-mono font-bold text-slate-900 text-sm">
                      {selected.record_id}
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-400 block uppercase tracking-wide text-[10px] font-semibold">
                      Recorded Amount
                    </span>
                    <span className="font-mono font-bold text-slate-900 text-sm">
                      {selected.amount !== undefined && selected.amount !== null
                        ? `$${selected.amount.toFixed(2)}`
                        : "N/A"}
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-400 block uppercase tracking-wide text-[10px] font-semibold">
                      Discrepancy Delta
                    </span>
                    <span
                      className={`font-mono font-bold text-sm ${
                        selected.amount_discrepancy > 0 ? "text-red-600" : "text-slate-600"
                      }`}
                    >
                      {selected.amount_discrepancy > 0 ? `Δ $${selected.amount_discrepancy.toFixed(2)}` : "None"}
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-400 block uppercase tracking-wide text-[10px] font-semibold">
                      Reason Code
                    </span>
                    <span className="font-mono font-bold text-slate-800 text-xs">
                      {selected.reason_code}
                    </span>
                  </div>
                </div>
              </div>

              {/* ── SECTION 2: DETERMINISTIC EVIDENCE ── */}
              <div className="bg-white border border-blue-200/90 rounded-xl p-4 shadow-xs space-y-3.5">
                <div className="flex items-center justify-between border-b border-blue-100 pb-2">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-blue-600" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-blue-900">
                      Deterministic Evidence
                    </h4>
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200" title="Computed by deterministic Python from thread evidence">
                    Deterministic
                  </span>
                </div>

                <div className="text-xs text-slate-700 leading-relaxed bg-slate-50 border border-slate-200/70 p-3 rounded-lg">
                  {selected.explanation}
                </div>

                {/* Evidence Sources Breakdown */}
                <div className="space-y-1.5 pt-1">
                  <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400 block">
                    Verified Sources
                  </span>
                  <div className="space-y-1 text-xs font-mono">
                    <div className="flex items-center gap-2 text-slate-700">
                      <span className="text-emerald-600 font-bold">✓</span>
                      <span className="text-slate-500">Source:</span>
                      <span className="font-semibold">{selected.source}</span>
                      <span className="text-slate-300">•</span>
                      <span className="text-slate-500">ID:</span>
                      <span className="font-semibold">{selected.record_id}</span>
                    </div>

                    {selected.candidates && selected.candidates.length > 0 ? (
                      <div className="flex items-center gap-2 text-slate-700">
                        <span className="text-purple-600 font-bold">✓</span>
                        <span className="text-slate-500">Counterpart Candidate:</span>
                        <span className="font-semibold">{selected.candidates[0].target_record_id}</span>
                        <span className="text-slate-300">•</span>
                        <span className="text-slate-500">Amount:</span>
                        <span className="font-semibold">${(selected.candidates[0].target_amount ?? 0).toFixed(2)}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-amber-700">
                        <span className="text-amber-500 font-bold">⚠</span>
                        <span>No counterpart record found in opposite source.</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Mathematical Calculation Box */}
                {selected.amount_discrepancy > 0 && selected.candidates && selected.candidates.length > 0 && (
                  <div className="bg-slate-900 text-slate-100 rounded-lg p-3 font-mono text-xs space-y-1">
                    <span className="text-[10px] uppercase tracking-wider text-slate-400 block">
                      Deterministic Calculation
                    </span>
                    <div className="text-emerald-400 font-semibold">
                      ${selected.amount?.toFixed(2)} (Ledger) − ${(selected.candidates[0].target_amount ?? 0).toFixed(2)} (Settlement)
                    </div>
                    <div className="text-red-400 font-bold pt-1 border-t border-slate-800">
                      = ${selected.amount_discrepancy.toFixed(2)} (Fee deduction / Variance)
                    </div>
                  </div>
                )}

                {/* Recommendation */}
                <div className="pt-2 border-t border-slate-100 text-xs text-slate-600">
                  <span className="font-bold text-slate-900">Controller Action: </span>
                  {selected.reason_code === "AMOUNT_MISMATCH"
                    ? "Verify standard payment gateway MDR fee schedule (typically 2.0% - 2.5%) or request fee adjustment note."
                    : selected.reason_code === "AMBIGUOUS_CANDIDATE_CONFLICT"
                    ? "Review candidate reference IDs to select the definitive settlement entry."
                    : selected.reason_code === "DUPLICATE_TRANSACTION"
                    ? "Inspect journal entry for double posting; reverse redundant transaction if confirmed."
                    : selected.reason_code === "UNRECORDED_TRANSACTION"
                    ? "Post the missing journal entry into the internal ledger."
                    : "Initiate settlement tracer with payment processor for unrecorded counterpart transaction."}
                </div>
              </div>

              {/* ── Candidate matches (if any) ── */}
              {selected.candidates && selected.candidates.length > 0 && (
                <div className="space-y-2.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Candidate Matches ({selected.candidates.length})
                  </h4>
                  <div className="space-y-2">
                    {selected.candidates.map((cand: any, idx: number) => (
                      <div key={idx} className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-xs text-slate-900 font-mono truncate">
                            Candidate {String.fromCharCode(65 + idx)}: {cand.target_record_id}
                          </span>
                          <span className="pill bg-blue-50 text-blue-700 border border-blue-200 shrink-0">
                            {cand.confidence_score?.toFixed(1) ?? "—"}% score
                          </span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs font-mono text-slate-500 pt-2 border-t border-slate-200">
                          <div>Amount: <span className="font-bold text-slate-900">${(cand.target_amount ?? 0).toFixed(2)}</span></div>
                          <div>Date: <span className="font-bold text-slate-900">{cand.target_date || "N/A"}</span></div>
                          <div>Δ: <span className={`font-bold ${(cand.amount_diff ?? 0) > 0 ? "text-red-600" : "text-slate-900"}`}>${(cand.amount_diff ?? 0).toFixed(2)}</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Collapsible Evidence JSON ── */}
              {selected.evidence && Object.keys(selected.evidence).length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5 text-slate-400" /> Raw Audit Evidence
                  </h4>
                  <pre className="bg-slate-950 text-slate-200 text-[11px] rounded-xl p-3.5 overflow-x-auto font-mono leading-relaxed max-h-48">
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
