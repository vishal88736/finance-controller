"use client";

import React, { useState } from "react";
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

  if (!exception) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-lg border border-gray-200 shadow-xl max-w-xl w-full overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="p-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold text-gray-900 font-mono">
                {exception.record_id}
              </h3>
              <span className="text-[10px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.2 rounded">
                {exception.decision}
              </span>
            </div>
            <p className="text-xs text-gray-500 font-mono mt-0.5">
              Source: {exception.source} • Reason: {exception.reason_code}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-4 space-y-4 overflow-y-auto text-xs">
          {/* Action Success Alert if user interacted */}
          {resolvedAction && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded text-emerald-800 font-medium flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{resolvedAction}</span>
            </div>
          )}

          {/* KPI Summary Grid */}
          <div className="grid grid-cols-3 gap-2 bg-gray-50 p-3 rounded border border-gray-200 font-mono">
            <div>
              <span className="text-gray-400 block text-[10px] uppercase font-medium">Recorded Amount</span>
              <span className="text-gray-900 font-bold text-xs">
                ${exception.amount !== undefined ? exception.amount.toFixed(2) : "0.00"}
              </span>
            </div>
            <div>
              <span className="text-gray-400 block text-[10px] uppercase font-medium">Fee Delta</span>
              <span className={`font-bold text-xs ${exception.amount_discrepancy > 0 ? "text-rose-600" : "text-gray-700"}`}>
                {exception.amount_discrepancy > 0 ? `Δ $${exception.amount_discrepancy.toFixed(2)}` : "$0.00"}
              </span>
            </div>
            <div>
              <span className="text-gray-400 block text-[10px] uppercase font-medium">Top Match Score</span>
              <span className="text-gray-800 font-bold text-xs">
                {exception.confidence.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Explanation */}
          <div className="space-y-1">
            <div className="font-semibold text-gray-700 text-xs">Deterministic Audit Explanation</div>
            <div className="bg-gray-50 border border-gray-200 p-3 rounded text-gray-800 leading-relaxed">
              {exception.explanation}
            </div>
          </div>

          {/* Candidates Comparison Breakdown */}
          {exception.candidates && exception.candidates.length > 0 && (
            <div className="space-y-1.5">
              <div className="font-semibold text-gray-700 text-xs">
                Candidate Matches ({exception.candidates.length})
              </div>
              <div className="space-y-1.5">
                {exception.candidates.map((cand, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 bg-gray-50 border border-gray-200 rounded space-y-1 font-mono text-[11px]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-gray-900">
                        Candidate {String.fromCharCode(65 + idx)}: {cand.target_record_id}
                      </span>
                      <span className="text-blue-700 font-bold">
                        {cand.confidence_score.toFixed(1)}% Score
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-gray-600 pt-1 border-t border-gray-200">
                      <div>Bank Amt: <span className="font-bold text-gray-900">${cand.target_amount.toFixed(2)}</span></div>
                      <div>Date: <span className="font-bold text-gray-900">{cand.target_date || "N/A"}</span></div>
                      <div>Delta: <span className={`font-bold ${cand.amount_diff > 0 ? "text-rose-600" : "text-gray-900"}`}>${cand.amount_diff.toFixed(2)}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Accounting Action Box */}
          <div className="p-3 bg-blue-50/70 border border-blue-200 rounded space-y-2">
            <div className="font-semibold text-blue-950 text-xs">
              Recommended Financial Action
            </div>
            <p className="text-blue-900 text-[11px] leading-relaxed">
              {exception.reason_code === "AMOUNT_MISMATCH"
                ? `Journalize payment processing fee adjustment of $${exception.amount_discrepancy.toFixed(2)} to reconcile gross ledger against net bank settlement.`
                : exception.reason_code === "AMBIGUOUS_CANDIDATES"
                ? "Multiple counterpart entries match amount and date. Manual cross-referencing required."
                : exception.reason_code === "DUPLICATE"
                ? "Void duplicate ledger transaction entry to correct cash balances."
                : "Post missing transaction to ledger."}
            </p>

            <div className="flex items-center space-x-2 pt-1">
              {exception.reason_code === "AMOUNT_MISMATCH" && (
                <button
                  type="button"
                  onClick={() => setResolvedAction(`Fee adjustment entry of $${exception.amount_discrepancy.toFixed(2)} journalized to Expense:Bank Fees.`)}
                  className="bg-[#0C6CF2] hover:bg-blue-600 text-white font-medium text-xs px-3 py-1.5 rounded transition-colors flex items-center space-x-1"
                >
                  <DollarSign className="w-3 h-3" />
                  <span>Journalize Fee (${exception.amount_discrepancy.toFixed(2)})</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setResolvedAction(`Record ${exception.record_id} marked as audited.`)}
                className="bg-white hover:bg-gray-100 text-gray-700 border border-gray-300 font-medium text-xs px-3 py-1.5 rounded transition-colors"
              >
                Mark Audited
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 bg-gray-50 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 bg-gray-900 hover:bg-gray-800 text-white rounded text-xs font-semibold"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
