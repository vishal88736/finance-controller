"use client";

import React, { useState } from "react";
import { X, AlertTriangle, ShieldAlert, Brain, CheckCircle2, DollarSign, Calendar, Tag, ArrowRight, FileCheck, Layers } from "lucide-react";
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-2xl w-full overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-amber-100 border border-amber-200 flex items-center justify-center text-amber-700 shadow-2xs">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2.5">
                <h3 className="text-base font-extrabold text-slate-900">
                  Exception Diagnosis: <span className="font-mono text-blue-700">{exception.record_id}</span>
                </h3>
                <span className="text-[10px] font-extrabold tracking-wider uppercase bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full">
                  {exception.decision}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-mono">
                ID: {exception.exception_id} • Ingestion Source: {exception.source}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-200/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 overflow-y-auto">
          {/* Action Success Alert if user interacted */}
          {resolvedAction && (
            <div className="p-3.5 bg-emerald-50 border border-emerald-300 rounded-xl text-xs text-emerald-900 font-medium flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{resolvedAction}</span>
            </div>
          )}

          {/* KPI Summary Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Booked Amount</span>
              <span className="text-slate-900 font-black text-sm font-mono">
                ${exception.amount !== undefined ? exception.amount.toFixed(2) : "0.00"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Amount Delta</span>
              <span className={`font-black text-sm font-mono ${exception.amount_discrepancy > 0 ? "text-rose-600" : "text-slate-700"}`}>
                {exception.amount_discrepancy > 0 ? `Δ $${exception.amount_discrepancy.toFixed(2)}` : "$0.00"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Reason Code</span>
              <span className="text-blue-700 font-bold text-xs">
                {exception.reason_code}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Top Match Score</span>
              <span className="text-slate-800 font-bold text-xs font-mono">
                {exception.confidence.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Deterministic Explanation & Diagnosis */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center space-x-1.5">
              <Brain className="w-3.5 h-3.5 text-blue-600" />
              <span>Deterministic Explanation & Audit Note</span>
            </h4>
            <div className="bg-blue-50/70 border border-blue-200/90 p-4 rounded-xl text-xs text-slate-800 leading-relaxed shadow-2xs">
              {exception.explanation}
            </div>
          </div>

          {/* Candidates Comparison Breakdown */}
          {exception.candidates && exception.candidates.length > 0 && (
            <div className="space-y-2.5">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center space-x-1.5">
                <Layers className="w-3.5 h-3.5 text-purple-600" />
                <span>Candidate Counterparts Analyzed ({exception.candidates.length})</span>
              </h4>
              <div className="space-y-2">
                {exception.candidates.map((cand, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-2.5 text-xs razorpay-card"
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-bold text-slate-900 flex items-center space-x-2">
                        <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center font-bold text-[10px]">
                          {String.fromCharCode(65 + idx)}
                        </span>
                        <span className="font-mono">{cand.target_record_id}</span>
                        <span className="text-[10px] text-slate-400 font-normal">({cand.target_source})</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-blue-800 font-extrabold bg-blue-100 px-2.5 py-0.5 rounded-full text-[11px] font-mono">
                          {cand.confidence_score.toFixed(1)}% Score
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-[11px] text-slate-600 pt-1.5 border-t border-slate-200 font-mono">
                      <div>Bank Amount: <span className="font-bold text-slate-900">${cand.target_amount.toFixed(2)}</span></div>
                      <div>Bank Date: <span className="font-bold text-slate-900">{cand.target_date || "N/A"}</span></div>
                      <div>Delta: <span className={`font-bold ${cand.amount_diff > 0 ? "text-rose-600" : "text-emerald-600"}`}>${cand.amount_diff.toFixed(2)}</span></div>
                    </div>

                    {cand.notes && (
                      <div className="text-[10px] text-slate-500 bg-white p-2 rounded-lg border border-slate-200 font-mono">
                        Scoring Vectors: {cand.notes}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommended Financial Ops Resolution */}
          <div className="p-4 bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-xl text-xs space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-bold text-amber-950 flex items-center space-x-1.5 text-xs">
                <ShieldAlert className="w-4 h-4 text-amber-700" />
                <span>Recommended Financial Action</span>
              </span>
              <span className="text-[10px] font-mono font-bold text-amber-800 bg-amber-200/60 px-2 py-0.5 rounded">
                Human-in-the-Loop Safe
              </span>
            </div>
            <p className="text-amber-900 leading-relaxed text-[11px]">
              {exception.reason_code === "AMOUNT_MISMATCH"
                ? `Post an automatic payment gateway fee adjustment of $${exception.amount_discrepancy.toFixed(2)} to balance ledger account vs net bank credit.`
                : exception.reason_code === "AMBIGUOUS_CANDIDATES"
                ? "Multiple counterpart entries share identical amount and date. Request remittance slip before posting to prevent incorrect invoice clearing."
                : exception.reason_code === "DUPLICATE"
                ? "Void the duplicate ledger entry to ensure accurate cash book balances."
                : "Record missing transaction into internal ledger or investigate pending bank clearance."}
            </p>

            {/* Simulated Action Buttons */}
            <div className="flex flex-wrap gap-2 pt-1">
              {exception.reason_code === "AMOUNT_MISMATCH" && (
                <button
                  type="button"
                  onClick={() => setResolvedAction(`Fee adjustment entry of $${exception.amount_discrepancy.toFixed(2)} posted to Expense:Bank Fees.`)}
                  className="bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs px-3 py-1.5 rounded-lg shadow-2xs transition-colors flex items-center space-x-1"
                >
                  <DollarSign className="w-3.5 h-3.5" />
                  <span>Journalize Fee (${exception.amount_discrepancy.toFixed(2)})</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setResolvedAction(`Record ${exception.record_id} marked as reviewed and queued for controller approval.`)}
                className="bg-white hover:bg-amber-100/60 text-amber-900 border border-amber-300 font-bold text-xs px-3 py-1.5 rounded-lg transition-colors"
              >
                Approve for Audit
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end space-x-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold shadow-xs transition-colors"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
