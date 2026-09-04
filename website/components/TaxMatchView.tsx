"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Search,
  AlertCircle,
  RefreshCw,
  ChevronRight,
  X,
  ShieldAlert,
  Percent,
  Calculator,
  Loader2,
} from "lucide-react";
import { api, TaxMatchData, TaxMatchItem } from "@/lib/api";

interface TaxMatchViewProps {
  threadId: string;
  hasDocuments: boolean;
  onUploadClick?: () => void;
}

export const TaxMatchView: React.FC<TaxMatchViewProps> = ({
  threadId,
  hasDocuments,
  onUploadClick,
}) => {
  const [taxRate, setTaxRate] = useState<number>(0.18);
  const [taxData, setTaxData] = useState<TaxMatchData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [search, setSearch] = useState<string>("");
  const [selected, setSelected] = useState<TaxMatchItem | null>(null);

  const fetchTaxMatches = useCallback(
    async (rate: number) => {
      if (!threadId) return;
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.runTaxMatch(threadId, rate);
        setTaxData(data);
      } catch (err: any) {
        setError(err?.message || "Failed to load tax line matches.");
      } finally {
        setIsLoading(false);
      }
    },
    [threadId]
  );

  useEffect(() => {
    void fetchTaxMatches(taxRate);
  }, [fetchTaxMatches, taxRate]);

  const filteredLines = useMemo(() => {
    if (!taxData?.tax_lines) return [];
    return taxData.tax_lines.filter((line) => {
      const matchStatus = statusFilter === "ALL" || line.status === statusFilter;
      const matchSearch =
        !search ||
        line.record_id.toLowerCase().includes(search.toLowerCase()) ||
        line.source.toLowerCase().includes(search.toLowerCase());
      return matchStatus && matchSearch;
    });
  }, [taxData, statusFilter, search]);

  if (!hasDocuments && (!taxData || taxData.total_records === 0)) {
    return (
      <div className="card p-12 text-center max-w-xl mx-auto space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 mx-auto">
          <Percent className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">Tax-Line Matcher</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            Upload transaction and invoice documents to verify GST, VAT, and sales tax deduction lines
            against deterministic statutory calculations.
          </p>
        </div>
        {onUploadClick && (
          <button
            onClick={onUploadClick}
            className="btn btn-primary text-xs font-semibold px-4 py-2"
          >
            Upload Documents
          </button>
        )}
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "MATCH":
        return <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200">MATCH</span>;
      case "MISMATCH":
        return <span className="pill bg-red-50 text-red-700 border border-red-200">MISMATCH</span>;
      case "MISSING":
        return <span className="pill bg-amber-50 text-amber-700 border border-amber-200">MISSING TAX</span>;
      case "AMBIGUOUS":
        return <span className="pill bg-purple-50 text-purple-700 border border-purple-200">AMBIGUOUS</span>;
      case "NOT_TAX_APPLICABLE":
        return <span className="pill bg-slate-100 text-slate-600 border border-slate-200">NOT APPLICABLE</span>;
      case "TAX_DATA_UNAVAILABLE":
        return <span className="pill bg-sky-50 text-sky-700 border border-sky-200">UNAVAILABLE</span>;
      default:
        return <span className="pill bg-slate-100 text-slate-700 border border-slate-200">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Top Controls ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Tax-Line Matcher (Agent 4)
            </span>
            <span className="pill bg-indigo-50 text-indigo-700 border border-indigo-200">
              Deterministic Tax Verification
            </span>
          </div>
          <h2 className="text-base font-bold text-slate-900 mt-0.5">
            Statutory Tax Line &amp; Deduction Matching
          </h2>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200/80 px-2.5 py-1.5 rounded-lg">
            <Calculator className="w-3.5 h-3.5 text-slate-400" />
            <span>Statutory Rate:</span>
            <select
              value={taxRate}
              onChange={(e) => setTaxRate(parseFloat(e.target.value))}
              className="bg-white border border-slate-200 rounded px-2 py-0.5 font-bold text-slate-900 focus:outline-none cursor-pointer"
            >
              <option value={0.18}>18% (Standard GST)</option>
              <option value={0.12}>12% (Concessional)</option>
              <option value={0.05}>5% (Essential)</option>
              <option value={0.08}>8% (Standard Sales Tax)</option>
            </select>
          </div>
          <div className="text-[10px] text-slate-400 font-medium max-w-xs">
            Selected rate is user-configured; a per-line <code className="font-mono">tax_rate</code> in the source
            overrides it (source-derived).
          </div>

          <button
            onClick={() => fetchTaxMatches(taxRate)}
            disabled={isLoading}
            className="btn btn-secondary text-xs font-semibold px-3 py-2 flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>{isLoading ? "Matching…" : "Re-Match"}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── No taxable lines: explicit empty state (never "0.0%") ── */}
      {taxData && taxData.tax_eligible_count === 0 && taxData.total_records > 0 ? (
        <div className="card p-10 text-center space-y-5">
          <div className="w-12 h-12 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-500 mx-auto">
            <Percent className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900">No tax-bearing lines found</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
              This thread has financial records, but none carry tax evidence
              (tax/gst/vat/taxable/tax_rate fields). Tax matching is not applicable.
            </p>
          </div>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-left max-w-2xl mx-auto">
            {[
              ["Taxable lines", String(taxData.tax_eligible_count ?? 0)],
              ["Evaluated lines", String(taxData.matched_count ?? 0)],
              ["Mismatches", String(taxData.mismatched_count ?? 0)],
              ["Status", "Not applicable"],
            ].map(([label, value]) => (
              <div key={label} className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
                <div className="text-[10px] uppercase tracking-wide font-bold text-slate-400">{label}</div>
                <div className="text-sm font-bold font-mono text-slate-800 mt-1">{value}</div>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        <>
          {/* ── Summary KPI Cards ── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Match Rate */}
        <div className="card p-4 border-t-4 border-t-emerald-500 bg-white">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Tax Match Rate
          </div>
          <div className="text-2xl font-bold font-mono text-slate-900 mt-1">
            {taxData ? `${taxData.tax_match_rate.toFixed(1)}%` : "—"}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {taxData ? `${taxData.matched_count} / ${taxData.tax_eligible_count ?? taxData.total_records} eligible lines matched` : "—"}
          </div>
        </div>

        {/* Matched */}
        <div className="card p-4 border-t-4 border-t-emerald-400 bg-white">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Matched Lines
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-600 mt-1">
            {taxData ? taxData.matched_count : "—"}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Exact calculation verified</div>
        </div>

        {/* Mismatched */}
        <div className="card p-4 border-t-4 border-t-red-500 bg-white">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Tax Mismatches
          </div>
          <div className="text-2xl font-bold font-mono text-red-600 mt-1">
            {taxData ? taxData.mismatched_count : "—"}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Incorrect rate or calculation</div>
        </div>

        {/* Missing Tax */}
        <div className="card p-4 border-t-4 border-t-amber-500 bg-white">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Missing Tax Lines
          </div>
          <div className="text-2xl font-bold font-mono text-amber-600 mt-1">
            {taxData ? taxData.missing_count : "—"}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Zero tax on taxable item</div>
        </div>

        {/* Total Discrepancy */}
        <div className="card p-4 border-t-4 border-t-indigo-500 bg-white">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Abs. Variance (cumulative)
          </div>
          <div className="text-2xl font-bold font-mono text-indigo-700 mt-1">
            ${(taxData?.total_tax_discrepancy ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Signed net variance: {taxData ? `${taxData.net_tax_variance && taxData.net_tax_variance > 0 ? "+" : ""}$${(taxData.net_tax_variance ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "—"}
            {taxData && taxData.not_applicable_count ? ` · ${taxData.not_applicable_count} not applicable` : ""}
          </div>
        </div>
      </div>

      {/* ── Filter & Search Toolbar ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {[
            { id: "ALL", label: `All (${taxData?.total_records ?? 0})` },
            { id: "MISMATCH", label: `Mismatches (${taxData?.mismatched_count ?? 0})` },
            { id: "MISSING", label: `Missing (${taxData?.missing_count ?? 0})` },
            { id: "MATCH", label: `Matched (${taxData?.matched_count ?? 0})` },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setStatusFilter(f.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                statusFilter === f.id
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search record ID, source…"
            className="w-full pl-9 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* ── Table ── */}
      <div className="card overflow-hidden bg-white border border-slate-200">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs fintech-table">
            <thead className="bg-slate-50 border-b border-slate-100 text-slate-600 font-bold uppercase tracking-wider text-[10px]">
              <tr>
                <th>Record ID</th>
                <th>Source</th>
                <th>Taxable Base</th>
                <th>Rate</th>
                <th>Expected Tax</th>
                <th>Reported Tax</th>
                <th>Difference</th>
                <th>Status</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-400 font-sans">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto text-indigo-500 mb-2" />
                    Calculating deterministic tax lines…
                  </td>
                </tr>
              ) : filteredLines.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-400 font-sans">
                    No tax lines match current filter criteria.
                  </td>
                </tr>
              ) : (
                filteredLines.map((line) => (
                  <tr
                    key={line.id}
                    onClick={() => setSelected(line)}
                    className="hover:bg-slate-50/80 cursor-pointer transition-colors group"
                  >
                    <td className="font-bold text-slate-900">{line.record_id}</td>
                    <td className="text-slate-500 font-sans">{line.source}</td>
                    <td>${line.taxable_amount.toFixed(2)}</td>
                    <td>{line.tax_rate != null ? `${(line.tax_rate * 100).toFixed(1)}%` : "—"}</td>
                    <td className="text-emerald-700 font-semibold">${line.expected_tax.toFixed(2)}</td>
                    <td className="text-slate-800">${line.reported_tax.toFixed(2)}</td>
                    <td className={line.tax_difference > 0 ? "text-red-600 font-bold" : "text-slate-400"}>
                      {line.tax_difference > 0 ? `Δ $${line.tax_difference.toFixed(2)}` : "—"}
                    </td>
                    <td>{getStatusBadge(line.status)}</td>
                    <td className="text-right font-sans">
                      <span className="text-indigo-600 hover:text-indigo-700 font-semibold inline-flex items-center gap-0.5 group-hover:gap-1.5 transition-all">
                        Inspect <ChevronRight className="w-3.5 h-3.5" />
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      </>
      )}
      {/* ── Slide-Out Detail Drawer ── */}
      {selected && (
        <div
          className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-sm animate-fade-in"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <div
            className="bg-white w-full max-w-md h-full shadow-2xl flex flex-col animate-slide-in-right p-6 space-y-5 overflow-y-auto"
            role="dialog"
            aria-label={`Tax Detail for ${selected.record_id}`}
          >
            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900 font-mono">
                    {selected.record_id}
                  </h3>
                  {getStatusBadge(selected.status)}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Source: <span className="font-semibold text-slate-700">{selected.source}</span>
                </p>
              </div>

              <button
                onClick={() => setSelected(null)}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Deterministic Tax Calculation Box */}
            <div className="bg-slate-900 text-slate-100 rounded-xl p-4 font-mono text-xs space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-slate-400 font-sans font-bold">
                Deterministic Tax Calculation
                {selected.tax_rate_source && (
                  <span className="ml-1.5 normal-case tracking-normal text-slate-500">
                    · rate {selected.tax_rate_source.replace("_", " ").toLowerCase()}
                  </span>
                )}
              </div>
              <div className="text-emerald-400 font-bold text-sm">
                {selected.tax_rate != null
                  ? `$${selected.taxable_amount.toFixed(2)} × ${(selected.tax_rate * 100).toFixed(1)}% = $${selected.expected_tax.toFixed(2)}`
                  : `$${selected.taxable_amount.toFixed(2)} (no tax rate) → $${selected.expected_tax.toFixed(2)}`}
              </div>
              <div className="text-slate-300 pt-1 border-t border-slate-800 flex justify-between">
                <span>Reported Tax:</span>
                <span className="font-bold text-white">${selected.reported_tax.toFixed(2)}</span>
              </div>
              <div className="text-red-400 pt-1 border-t border-slate-800 flex justify-between font-bold">
                <span>Tax Discrepancy:</span>
                <span>Δ ${selected.tax_difference.toFixed(2)}</span>
              </div>
            </div>

            {/* Explanation */}
            <div className="space-y-1.5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Audit Explanation
              </h4>
              <div className="text-xs text-slate-600 leading-relaxed bg-slate-50 border border-slate-200 p-3 rounded-xl">
                {selected.explanation}
              </div>
            </div>

            {/* Evidence details */}
            {selected.evidence && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5" /> Supporting Evidence
                </h4>
                <pre className="bg-slate-950 text-slate-200 text-[11px] rounded-xl p-3.5 overflow-x-auto font-mono max-h-48">
                  {JSON.stringify(selected.evidence, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
