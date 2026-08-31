"use client";

import React, { useState, useEffect } from "react";
import { X, CheckCircle2, DollarSign } from "lucide-react";
import { ExceptionItem } from "@/lib/api";

interface ExceptionDetailModalProps {
  exception: ExceptionItem | null;
  onClose: () => void;
}

export const ExceptionDetailModal: React.FC<ExceptionDetailModalProps> = ({
  exception,
  onClose
}) => {
  const [resolvedAction, setResolvedAction] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (exception) {
      setResolvedAction(null);
      requestAnimationFrame(() => setIsVisible(true));
    } else {
      setIsVisible(false);
    }
  }, [exception]);

  if (!exception) return null;

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(onClose, 200);
  };

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-200 ${
        isVisible ? "bg-black/30 backdrop-blur-sm" : "bg-transparent"
      }`}
      onClick={(e) => { if (e.target === e.currentTarget) handleClose(); }}
    >
      <div className={`bg-white rounded-2xl border border-slate-200 shadow-xl max-w-xl w-full overflow-hidden flex flex-col max-h-[85vh] transition-all duration-200 ${
        isVisible ? "opacity-100 scale-100 translate-y-0" : "opacity-0 scale-95 translate-y-2"
      }`}>
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="text-base font-bold text-slate-900 font-[family-name:var(--font-geist-mono)]">
                {exception.record_id}
              </h3>
              <span className="pill bg-amber-50 text-amber-700 border border-amber-200">
                {exception.decision}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Source: <span className="font-medium text-slate-600">{exception.source}</span>
              <span className="mx-1.5 text-slate-300">•</span>
              Reason: <span className="font-medium text-slate-600">{exception.reason_code}</span>
            </p>
          </div>
          <button
            onClick={handleClose}
            className="text-slate-400 hover:text-slate-600 p-2 rounded-lg hover:bg-slate-100 transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="px-6 py-5 space-y-5 overflow-y-auto">
          {/* Success Alert */}
          {resolvedAction && (
            <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-sm text-emerald-800 font-medium flex items-center gap-2.5 animate-slide-up">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
              <span>{resolvedAction}</span>
            </div>
          )}

          {/* KPI Summary Grid */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-50 border border-slate-200 p-3.5 rounded-xl">
              <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wide block">Recorded Amount</span>
              <span className="text-lg font-bold text-slate-900 font-[family-name:var(--font-geist-mono)] mt-1 block">
                ${exception.amount !== undefined ? exception.amount.toFixed(2) : "0.00"}
              </span>
            </div>
            <div className="bg-slate-50 border border-slate-200 p-3.5 rounded-xl">
              <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wide block">Fee Delta</span>
              <span className={`text-lg font-bold font-[family-name:var(--font-geist-mono)] mt-1 block ${exception.amount_discrepancy > 0 ? "text-red-600" : "text-slate-700"}`}>
                {exception.amount_discrepancy > 0 ? `Δ $${exception.amount_discrepancy.toFixed(2)}` : "$0.00"}
              </span>
            </div>
            <div className="bg-slate-50 border border-slate-200 p-3.5 rounded-xl">
              <span className="text-[11px] text-slate-400 uppercase font-semibold tracking-wide block">Top Match Score</span>
              <span className="text-lg font-bold text-slate-900 font-[family-name:var(--font-geist-mono)] mt-1 block">
                {exception.confidence.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Explanation */}
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-slate-800">Deterministic Audit Explanation</h4>
            <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl text-sm text-slate-700 leading-relaxed">
              {exception.explanation}
            </div>
          </div>

          {/* Candidates Comparison */}
          {exception.candidates && exception.candidates.length > 0 && (
            <div className="space-y-2.5">
              <h4 className="text-sm font-semibold text-slate-800">
                Candidate Matches ({exception.candidates.length})
              </h4>
              <div className="space-y-2">
                {exception.candidates.map((cand, idx) => (
                  <div
                    key={idx}
                    className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm text-slate-900 font-[family-name:var(--font-geist-mono)]">
                        Candidate {String.fromCharCode(65 + idx)}: {cand.target_record_id}
                      </span>
                      <span className="pill bg-blue-50 text-blue-700 border border-blue-200">
                        {cand.confidence_score.toFixed(1)}% Score
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-3 text-xs font-[family-name:var(--font-geist-mono)] text-slate-500 pt-2 border-t border-slate-200">
                      <div>Bank Amt: <span className="font-bold text-slate-900">${cand.target_amount.toFixed(2)}</span></div>
                      <div>Date: <span className="font-bold text-slate-900">{cand.target_date || "N/A"}</span></div>
                      <div>Delta: <span className={`font-bold ${cand.amount_diff > 0 ? "text-red-600" : "text-slate-900"}`}>${cand.amount_diff.toFixed(2)}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Box */}
          <div className="p-4 bg-blue-50/60 border border-blue-200 rounded-xl space-y-3">
            <h4 className="font-semibold text-blue-950 text-sm">
              Recommended Financial Action
            </h4>
            <p className="text-blue-800 text-sm leading-relaxed">
              {exception.reason_code === "AMOUNT_MISMATCH"
                ? `Journalize payment processing fee adjustment of $${exception.amount_discrepancy.toFixed(2)} to reconcile gross ledger against net bank settlement.`
                : exception.reason_code === "AMBIGUOUS_CANDIDATES"
                ? "Multiple counterpart entries match amount and date. Manual cross-referencing required."
                : exception.reason_code === "DUPLICATE"
                ? "Void duplicate ledger transaction entry to correct cash balances."
                : "Post missing transaction to ledger."}
            </p>

            <div className="flex items-center gap-2.5 pt-1">
              {exception.reason_code === "AMOUNT_MISMATCH" && (
                <button
                  type="button"
                  onClick={() => setResolvedAction(`Fee adjustment entry of $${exception.amount_discrepancy.toFixed(2)} journalized to Expense:Bank Fees.`)}
                  className="bg-gradient-to-b from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-medium text-sm px-4 py-2 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer shadow-sm active:scale-[0.98]"
                >
                  <DollarSign className="w-3.5 h-3.5" />
                  <span>Journalize Fee (${exception.amount_discrepancy.toFixed(2)})</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setResolvedAction(`Record ${exception.record_id} marked as audited.`)}
                className="bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 hover:border-slate-400 font-medium text-sm px-4 py-2 rounded-lg transition-all cursor-pointer"
              >
                Mark Audited
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex justify-end">
          <button
            onClick={handleClose}
            className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-semibold transition-all cursor-pointer active:scale-[0.98]"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
