"use client";

import React from "react";
import { Play, CheckCircle2, Loader2, Circle, FileText, Copy, Layers, Gauge, FlaskConical } from "lucide-react";
import { ThreadDocumentItem, LatestRun } from "@/lib/api";

interface ReconciliationControlProps {
  documents: ThreadDocumentItem[];
  latestRun: LatestRun | null;
  isRunning: boolean;
  onRun: () => void;
  runError: string | null;
  activeSteps: string[]; // step_progress from an in-flight/last run
}

/**
 * Live pipeline reflecting actual backend state:
 * Documents → Parsing → Normalization → Matching → Exception Analysis → Persistence → Complete
 * The step list shows real progress returned by the reconciliation graph.
 */
export const PIPELINE_STEPS = [
  { key: "upload", label: "Upload", match: /(?:Upload|Loaded|Ingested)/i },
  { key: "schema", label: "Schema Detection", match: /Schema Detection/i },
  { key: "mapping", label: "Column Mapping", match: /Column Mapping/i },
  { key: "reconciliation", label: "Python Reconciliation", match: /(?:Python Reconciliation|deterministic matching)/i },
  { key: "results", label: "Results", match: /(?:Results|Compiled structured)/i },
  { key: "qa", label: "Q&A Ready", match: /(?:Finalized|Completed run|Pipeline Finalized)/i },
];

export const ReconciliationControl: React.FC<ReconciliationControlProps> = ({
  documents,
  latestRun,
  isRunning,
  onRun,
  runError,
  activeSteps,
}) => {
  const uniqueDocs = documents.filter((d) => d.processing_status === "PROCESSED").length;
  const totalRecords = documents.reduce((s, d) => s + (d.record_count || 0), 0);
  const duplicateDocs = documents.filter((d) => d.duplicate || d.processing_status === "DUPLICATE").length;
  const canRun = uniqueDocs > 0 && !isRunning;

  const completedStepCount = PIPELINE_STEPS.filter((s) =>
    activeSteps.some((p) => s.match.test(p))
  ).length;
  const currentStepIdx = isRunning
    ? Math.min(completedStepCount, PIPELINE_STEPS.length - 1)
    : latestRun
      ? PIPELINE_STEPS.length
      : -1;

  return (
    <div className="card p-5 space-y-4">
      {/* Header row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Reconciliation Control</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Deterministic multi-pass matching over this thread&apos;s documents — never demo data.
          </p>
        </div>
        <button
          onClick={onRun}
          disabled={!canRun}
          className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all cursor-pointer shadow-sm active:scale-[0.98] shrink-0"
        >
          {isRunning ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Reconciling…</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              <span>Run Reconciliation</span>
            </>
          )}
        </button>
      </div>

      {/* Pre-run facts */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <FactPill
          icon={<FileText className="w-3.5 h-3.5 text-blue-500" />}
          label="Documents selected"
          value={`${uniqueDocs}`}
        />
        <FactPill
          icon={<Layers className="w-3.5 h-3.5 text-indigo-500" />}
          label="Records detected"
          value={totalRecords.toLocaleString()}
        />
        <FactPill
          icon={<Copy className="w-3.5 h-3.5 text-amber-500" />}
          label="Duplicate docs"
          value={`${duplicateDocs}`}
        />
        <FactPill
          icon={<Gauge className="w-3.5 h-3.5 text-emerald-500" />}
          label="Previous run"
          value={latestRun ? latestRun.status : "None"}
        />
      </div>

      {/* Evaluation availability */}
      <div className="flex items-center gap-2 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
        <FlaskConical className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        <span>
          Evaluation availability:&nbsp;
          {latestRun?.evaluated ? (
            <span className="text-emerald-700 font-semibold">benchmark evaluation active for this run</span>
          ) : (
            <span className="font-medium">
              no authorized ground truth for user documents — precision/recall shown as N/A
            </span>
          )}
        </span>
      </div>

      {/* Live pipeline */}
      {(isRunning || activeSteps.length > 0) && (
        <div className="border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Pipeline
            </span>
            {isRunning && (
              <span className="text-[11px] font-semibold text-blue-600 animate-pulse">
                Executing reconciliation graph…
              </span>
            )}
          </div>
          <ol className="flex items-start gap-1" aria-label="Reconciliation pipeline progress">
            {PIPELINE_STEPS.map((step, idx) => {
              const done = currentStepIdx > idx;
              const current = currentStepIdx === idx && isRunning;
              return (
                <li key={step.key} className="flex-1 min-w-0">
                  <div
                    className={`rounded-lg border p-2.5 h-full transition-all ${
                      done
                        ? "bg-emerald-50/70 border-emerald-200"
                        : current
                          ? "bg-blue-50 border-blue-400 ring-2 ring-blue-500/15"
                          : "bg-slate-50 border-slate-200"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      {done ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                      ) : current ? (
                        <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />
                      ) : (
                        <Circle className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                      )}
                      <span
                        className={`text-[10px] font-bold ${
                          done ? "text-emerald-800" : current ? "text-blue-800" : "text-slate-400"
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {/* Schema & Semantic Column Mapping Inspection */}
      {latestRun?.mapped_columns && Object.keys(latestRun.mapped_columns).length > 0 && (
        <div className="bg-slate-50/70 border border-slate-200 rounded-xl p-3.5 text-xs space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-700 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-blue-600" />
              Detected Schemas &amp; Semantic Column Mappings
            </span>
            <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              Deterministic Python (Pandas/NumPy)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.entries(latestRun.mapped_columns).map(([docId, mappings]) => {
              const docItem = documents.find((d) => d.id === docId);
              return (
                <div key={docId} className="bg-white border border-slate-200 rounded-lg p-2.5">
                  <div className="font-semibold text-slate-900 truncate mb-1.5 flex items-center justify-between">
                    <span>{docItem?.filename || docId}</span>
                    <span className="text-[10px] text-slate-400 font-normal">
                      {Object.keys(mappings).length} fields mapped
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1 font-mono text-[10px]">
                    {Object.entries(mappings).map(([semantic, rawCol]) => (
                      <span key={semantic} className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200">
                        <span className="text-blue-600 font-semibold">{semantic}</span>: {rawCol}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Diagnostics for zero match or rejections */}
          {latestRun.diagnostics?.zero_match_diagnostics && (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-2.5 text-xs">
              <span className="font-bold">Reconciliation Diagnostics: </span>
              {latestRun.diagnostics.zero_match_diagnostics}
            </div>
          )}
        </div>
      )}

      {runError && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl px-3.5 py-2.5 text-xs flex items-start gap-2">
          <span className="font-semibold shrink-0">Reconciliation failed.</span>
          <span className="flex-1">{runError}</span>
        </div>
      )}
    </div>
  );
};

const FactPill: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 min-w-0">
    <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
      <span className="shrink-0">{icon}</span>
      <span className="truncate">{label}</span>
    </div>
    <div className="text-sm font-bold text-slate-800 mt-1 truncate" title={value}>
      {value}
    </div>
  </div>
);
