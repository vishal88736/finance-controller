"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  ShieldCheck, RefreshCw, Clock, AlertOctagon, X, Wrench,
} from "lucide-react";
import { api, AuditLogItem } from "@/lib/api";

interface AuditTrailViewProps {
  threadId: string;
}

type Category = "documents" | "reconciliation" | "qa" | "guardrails" | "errors" | "evaluation" | "all";

const CATEGORIES: { id: Category | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "documents", label: "Documents" },
  { id: "reconciliation", label: "Reconciliation" },
  { id: "qa", label: "Q&A" },
  { id: "guardrails", label: "Guardrails" },
  { id: "errors", label: "Errors" },
  { id: "evaluation", label: "Evaluation" },
];

function categorize(action: string): Category {
  const a = action.toUpperCase();
  if (a.includes("ERROR")) return "errors";
  if (a.includes("GUARDRAIL") || a.includes("PERMISSION")) return "guardrails";
  if (a.includes("RECONCIL") || a.includes("DEMO_BATCH") || a.includes("RUN")) return "reconciliation";
  if (a.includes("DUPLICATE") || a.includes("DOCUMENT") || a.includes("THREAD")) return "documents";
  if (a.includes("QA") || a.includes("MESSAGE")) return "qa";
  if (a.includes("EVAL")) return "evaluation";
  return "documents";
}

const badgeFor = (cat: Category) => {
  switch (cat) {
    case "reconciliation":
      return <span className="pill bg-blue-50 text-blue-700 border border-blue-200">Reconciliation</span>;
    case "documents":
      return <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200">Documents</span>;
    case "qa":
      return <span className="pill bg-indigo-50 text-indigo-700 border border-indigo-200">Q&amp;A</span>;
    case "guardrails":
      return <span className="pill bg-amber-50 text-amber-700 border border-amber-200">Guardrail</span>;
    case "errors":
      return <span className="pill bg-red-50 text-red-700 border border-red-200">Error</span>;
    case "evaluation":
      return <span className="pill bg-violet-50 text-violet-700 border border-violet-200">Evaluation</span>;
    default:
      return null;
  }
};

export const AuditTrailView: React.FC<AuditTrailViewProps> = ({ threadId }) => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [filter, setFilter] = useState<Category | "all">("all");
  const [selected, setSelected] = useState<AuditLogItem | null>(null);

  const fetchAudit = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getAuditTrail(threadId, 200);
      setLogs(data);
    } catch (e: any) {
      setError(e?.message || "Could not load audit trail.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const filtered = useMemo(
    () => (filter === "all" ? logs : logs.filter((l) => categorize(l.action) === filter)),
    [logs, filter]
  );

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Audit Trail</h3>
            <p className="text-xs text-slate-400 font-mono">append-only · thread {threadId}</p>
          </div>
        </div>
        <button
          onClick={fetchAudit}
          disabled={isLoading}
          className="flex items-center gap-1.5 bg-white hover:bg-slate-50 text-slate-600 border border-slate-200 hover:border-slate-300 text-xs font-medium px-3 py-1.5 rounded-lg transition-all cursor-pointer shadow-xs disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Filters */}
      <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            onClick={() => setFilter(c.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer border ${
              filter === c.id
                ? "bg-slate-900 text-white border-slate-900"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="max-h-[600px] overflow-y-auto">
        {error ? (
          <div className="p-12 text-center text-xs text-slate-500 space-y-2">
            <AlertOctagon className="w-8 h-8 mx-auto text-red-300" />
            <div className="font-semibold text-red-600">Audit trail unavailable</div>
            <div>{error}</div>
            <button onClick={fetchAudit} className="text-blue-600 underline font-medium cursor-pointer">
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-400 space-y-2">
            <Clock className="w-8 h-8 mx-auto text-slate-300" />
            <div>No audit entries{filter !== "all" ? " in this category " : ""} recorded yet for this thread.</div>
          </div>
        ) : (
          <ol className="divide-y divide-slate-100">
            {filtered.map((log) => {
              const cat = categorize(log.action);
              return (
                <li key={log.id}>
                  <button
                    onClick={() => setSelected(log)}
                    className="w-full text-left p-4 hover:bg-slate-50/60 transition-colors space-y-2 cursor-pointer"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        {badgeFor(cat)}
                        <span className="text-xs font-bold text-slate-800 font-mono truncate">{log.action}</span>
                      </div>
                      <span className="text-[11px] text-slate-400 font-mono shrink-0">
                        {log.timestamp
                          ? new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                          : "N/A"}
                      </span>
                    </div>
                    {log.result_summary && (
                      <p className="text-xs text-slate-600 leading-relaxed pl-1 line-clamp-2">
                        {log.result_summary}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400 pl-1 pt-0.5 flex-wrap">
                      {log.agent && <span>Agent: <strong className="text-slate-600">{log.agent}</strong></span>}
                      {log.tool && (
                        <span className="inline-flex items-center gap-1">
                          <Wrench className="w-3 h-3" /> {log.tool}
                        </span>
                      )}
                      {log.run_id && <span>Run: {log.run_id}</span>}
                    </div>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      {/* Detail drawer */}
      {selected && (
        <div
          className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-sm animate-fade-in"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <div className="bg-white w-full max-w-md h-full shadow-2xl flex flex-col animate-slide-in-right" role="dialog" aria-label="Audit event details">
            <div className="px-5 py-4 border-b border-slate-100 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  {badgeFor(categorize(selected.action))}
                  <h3 className="text-sm font-bold text-slate-900 font-mono">{selected.action}</h3>
                </div>
                <p className="text-[11px] text-slate-400 mt-1 font-mono">
                  {selected.timestamp ? new Date(selected.timestamp).toLocaleString() : ""}
                </p>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label="Close audit details"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              <div className="space-y-2 text-xs">
                <Row label="Event ID" value={selected.id} mono />
                <Row label="Thread" value={threadId} mono />
                {selected.run_id && <Row label="Run" value={selected.run_id} mono />}
                {selected.agent && <Row label="Agent" value={selected.agent} />}
                {selected.tool && <Row label="Tool" value={selected.tool} mono />}
              </div>

              {selected.result_summary && (
                <div>
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Summary</h4>
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 text-xs text-slate-700 leading-relaxed">
                    {selected.result_summary}
                  </div>
                </div>
              )}

              {(selected.parameters || selected.details) && (
                <div>
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Payload</h4>
                  <pre className="bg-slate-950 text-slate-200 text-[11px] rounded-xl p-4 overflow-x-auto font-mono leading-relaxed">
                    {JSON.stringify({ parameters: selected.parameters, details: selected.details }, null, 2)}
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

const Row: React.FC<{ label: string; value: string; mono?: boolean }> = ({ label, value, mono }) => (
  <div className="flex justify-between gap-3">
    <span className="text-slate-400 shrink-0">{label}</span>
    <span className={`text-slate-800 font-medium text-right break-all ${mono ? "font-mono" : ""}`}>{value}</span>
  </div>
);
