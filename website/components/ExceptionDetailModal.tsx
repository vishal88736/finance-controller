"use client";

import React from "react";
import { X, AlertTriangle, CheckCircle, ShieldAlert, Brain, DollarSign, Calendar, Tag, ArrowRight } from "lucide-react";
import { ExceptionItem } from "@/lib/api";

interface ExceptionDetailModalProps {
  exception: ExceptionItem | null;
  onClose: () => void;
}

export const ExceptionDetailModal: React.FC<ExceptionDetailModalProps> = ({
  exception,
  onClose
}) => {
  if (!exception) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-2xl w-full overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-slate-900">
                  Exception Details: {exception.record_id}
                </h3>
                <span className="text-[10px] font-bold uppercase bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                  {exception.decision}
                </span>
              </div>
              <p className="text-xs text-slate-500">ID: {exception.exception_id} • Source: {exception.source}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 overflow-y-auto">
          {/* Summary Box */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-semibold">Recorded Amount</span>
              <span className="text-slate-900 font-bold text-sm">
                ${exception.amount !== undefined ? exception.amount.toFixed(2) : "0.00"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-semibold">Discrepancy Delta</span>
              <span className={`font-bold text-sm ${exception.amount_discrepancy > 0 ? "text-rose-600" : "text-slate-700"}`}>
                ${exception.amount_discrepancy.toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-semibold">Reason Code</span>
              <span className="text-blue-700 font-semibold text-xs">
                {exception.reason_code}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-semibold">Top Confidence</span>
              <span className="text-slate-800 font-semibold text-xs">
                {exception.confidence.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Reason & Explanation */}
          <div className="space-y-1.5">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center space-x-1.5">
              <Brain className="w-3.5 h-3.5 text-blue-600" />
              <span>Deterministic Explanation & Diagnosis</span>
            </h4>
            <div className="bg-blue-50/60 border border-blue-200 p-3.5 rounded-xl text-xs text-slate-800 leading-relaxed">
              {exception.explanation}
            </div>
          </div>

          {/* Candidates Breakdown */}
          {exception.candidates && exception.candidates.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Candidate Matches Considered ({exception.candidates.length})
              </h4>
              <div className="space-y-2">
                {exception.candidates.map((cand, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-semibold text-slate-900 flex items-center space-x-2">
                        <span>Candidate {String.fromCharCode(65 + idx)}: {cand.target_record_id}</span>
                        <span className="text-[10px] text-slate-500 font-normal">({cand.target_source})</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-blue-700 font-bold bg-blue-100 px-2 py-0.5 rounded text-[11px]">
                          {cand.confidence_score.toFixed(1)}% Confidence
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-[11px] text-slate-600 pt-1 border-t border-slate-200/60">
                      <div>Amount: <span className="font-semibold text-slate-900">${cand.target_amount.toFixed(2)}</span></div>
                      <div>Date: <span className="font-semibold text-slate-900">{cand.target_date || "N/A"}</span></div>
                      <div>Diff: <span className="font-semibold text-rose-600">${cand.amount_diff.toFixed(2)}</span></div>
                    </div>

                    {cand.notes && (
                      <div className="text-[10px] text-slate-500 bg-white p-2 rounded border border-slate-200">
                        Scoring: {cand.notes}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Recommendation */}
          <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-xs space-y-1">
            <span className="font-bold text-amber-900 flex items-center space-x-1">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-700" />
              <span>Recommended Finance Action</span>
            </span>
            <p className="text-amber-800 leading-relaxed text-[11px]">
              Do not force automatic reconciliation. Review with vendor invoice statement or verify if payment processing fee deduction should be journaled separately.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end space-x-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold shadow-xs"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
