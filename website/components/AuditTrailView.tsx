"use client";

import React, { useEffect, useState } from "react";
import { ShieldCheck, RefreshCw, Clock, Terminal, User, FileText, CheckCircle2 } from "lucide-react";
import { api, AuditLogItem } from "@/lib/api";

interface AuditTrailViewProps {
  threadId: string;
}

export const AuditTrailView: React.FC<AuditTrailViewProps> = ({ threadId }) => {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchAudit = async () => {
    setIsLoading(true);
    try {
      const data = await api.getAuditTrail(threadId);
      setLogs(data);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
  }, [threadId]);

  const getActionBadge = (action: string) => {
    if (action.includes("RECONCILIATION")) {
      return <span className="pill bg-blue-50 text-blue-700 border border-blue-200">Reconciliation</span>;
    } else if (action.includes("DUPLICATE")) {
      return <span className="pill bg-amber-50 text-amber-700 border border-amber-200">Duplicate Check</span>;
    } else if (action.includes("DOCUMENT")) {
      return <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200">Document Ingestion</span>;
    } else if (action.includes("OFF_TOPIC")) {
      return <span className="pill bg-red-50 text-red-700 border border-red-200">Guardrail Trigger</span>;
    }
    return <span className="pill bg-slate-100 text-slate-600 border border-slate-200">{action}</span>;
  };

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Immutable Audit Trail</h3>
            <p className="text-xs text-slate-400 font-mono">Thread ID: {threadId}</p>
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

      {/* Log Entries */}
      <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
        {logs.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-400 space-y-2">
            <Clock className="w-8 h-8 mx-auto text-slate-300" />
            <div>No audit entries recorded yet for this thread.</div>
          </div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="p-4 hover:bg-slate-50/60 transition-colors space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {getActionBadge(log.action)}
                  <span className="text-xs font-bold text-slate-800 font-mono">{log.action}</span>
                </div>
                <span className="text-[11px] text-slate-400 font-mono">
                  {log.timestamp ? new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "N/A"}
                </span>
              </div>

              {log.result_summary && (
                <p className="text-xs text-slate-600 leading-relaxed font-sans pl-1">
                  {log.result_summary}
                </p>
              )}

              {log.agent && (
                <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400 pl-1 pt-1">
                  <span>Agent: <strong className="text-slate-700">{log.agent}</strong></span>
                  {log.tool && <span>Tool: <strong className="text-slate-700">{log.tool}</strong></span>}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
