"use client";

import React, { useState } from "react";
import {
  Cpu,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ShieldCheck,
  Search,
  Layers,
  FileCheck,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  TrendingUp,
  Percent,
} from "lucide-react";
import { AuditLogItem } from "@/lib/api";

interface AgentActivityPanelProps {
  auditLogs: AuditLogItem[];
  isRunning: boolean;
}

interface AgentNodeDef {
  id: string;
  name: string;
  shortName: string;
  role: string;
  icon: React.ComponentType<{ className?: string }>;
}

const WORKFLOW_AGENTS: AgentNodeDef[] = [
  {
    id: "router",
    name: "Router / Orchestrator",
    shortName: "Router",
    role: "Intent classification & workflow routing",
    icon: Cpu,
  },
  {
    id: "document",
    name: "Document Registry",
    shortName: "Documents",
    role: "SHA-256 byte check & canonical fingerprints",
    icon: FileCheck,
  },
  {
    id: "reconciliation",
    name: "Reconciliation Agent",
    shortName: "Reconcile",
    role: "4-pass deterministic matching pipeline",
    icon: Layers,
  },
  {
    id: "exceptions",
    name: "Exception Investigator",
    shortName: "Exceptions",
    role: "Material exception & fee isolation",
    icon: AlertCircle,
  },
  {
    id: "qa",
    name: "Finance Q&A Copilot",
    shortName: "Q&A",
    role: "Deterministic tools & Groq synthesis",
    icon: Search,
  },
  {
    id: "forecast",
    name: "Forward Cash Forecaster",
    shortName: "Forecaster",
    role: "Deterministic 7/30-day forward cash flow",
    icon: TrendingUp,
  },
  {
    id: "tax",
    name: "Tax-Line Matcher",
    shortName: "Tax Match",
    role: "Deterministic GST/VAT statutory reconciliation",
    icon: Percent,
  },
  {
    id: "guardrails",
    name: "6-Layer Guardrail",
    shortName: "Guardrails",
    role: "Input safety, thread scope & output scrubbing",
    icon: ShieldCheck,
  },
];

export const AgentActivityPanel: React.FC<AgentActivityPanelProps> = ({
  auditLogs,
  isRunning,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);

  // Derive genuine agent states from real audit events and run state
  const hasReconciliation = auditLogs.some((l) =>
    l.action.startsWith("RECONCILIATION_")
  );
  const reconRun = auditLogs.find((l) => l.action === "RECONCILIATION_COMPLETED");
  const hasQA = auditLogs.some((l) => l.action.startsWith("QA_"));
  const qaAnswered = auditLogs.filter((l) => l.action === "QA_QUESTION_ANSWERED").length;
  const hasForecast = auditLogs.some((l) => l.action.startsWith("CASH_FORECAST_"));
  const hasTax = auditLogs.some((l) => l.action.startsWith("TAX_MATCH_"));
  const hasGuardrailBlock = auditLogs.some((l) => l.action.includes("GUARDRAIL_BLOCK"));
  const hasDocs = auditLogs.some(
    (l) => l.action.includes("DOCUMENT") || l.action.includes("DUPLICATE")
  );
  const registeredDocsCount = auditLogs.filter((l) => l.action === "REGISTER_DOCUMENT").length;
  const hasSchemaDetected = auditLogs.some((l) => l.action === "SCHEMA_DETECTED");
  const hasColumnsMapped = auditLogs.some((l) => l.action === "COLUMNS_MAPPED");
  const hasPythonRecon = auditLogs.some(
    (l) => l.action === "PYTHON_RECONCILIATION_COMPLETED" || l.action === "RECONCILIATION_COMPLETED"
  );

  const getAgentStatus = (id: string) => {
    if (isRunning) {
      if (id === "reconciliation") {
        return {
          state: "ACTIVE" as const,
          badge: "● ACTIVE",
          detail: "Matching records in 4 passes…",
          badgeClass: "bg-blue-50 text-blue-700 border-blue-300 animate-pulse",
          cardClass: "border-blue-400 ring-2 ring-blue-500/15 bg-blue-50/20",
        };
      }
      if (id === "router" || id === "document") {
        return {
          state: "COMPLETED" as const,
          badge: "✓ COMPLETED",
          detail: "Inputs verified",
          badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
          cardClass: "border-slate-200 bg-white",
        };
      }
      return {
        state: "WAITING" as const,
        badge: "◌ WAITING",
        detail: "Awaiting matches",
        badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
        cardClass: "border-slate-200/80 bg-slate-50/50",
      };
    }

    switch (id) {
      case "router":
        return auditLogs.length > 0
          ? {
              state: "COMPLETED" as const,
              badge: "✓ ACTIVE",
              detail: "Intent verified",
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Standby for intent",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "document":
        return hasDocs
          ? {
              state: "COMPLETED" as const,
              badge: "✓ COMPLETED",
              detail: `${registeredDocsCount || "Files"} registered & hashed`,
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Awaiting upload",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "reconciliation":
        return hasReconciliation
          ? {
              state: "COMPLETED" as const,
              badge: "✓ COMPLETED",
              detail: reconRun ? "Reconciliation finished" : "Pipeline complete",
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Ready to run",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "exceptions":
        return hasReconciliation
          ? {
              state: "COMPLETED" as const,
              badge: "✓ COMPLETED",
              detail: "Exceptions isolated",
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Awaiting matching",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "qa":
        return hasQA
          ? {
              state: "ACTIVE" as const,
              badge: "● ACTIVE",
              detail: `${qaAnswered} queries grounded`,
              badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
              cardClass: "border-blue-200 bg-blue-50/10",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Awaiting questions",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "forecast":
        return hasForecast
          ? {
              state: "COMPLETED" as const,
              badge: "✓ COMPLETED",
              detail: "Projections generated",
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Standby for horizon",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "tax":
        return hasTax
          ? {
              state: "COMPLETED" as const,
              badge: "✓ COMPLETED",
              detail: "Tax lines verified",
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ WAITING",
              detail: "Standby for tax match",
              badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      case "guardrails":
        return hasGuardrailBlock
          ? {
              state: "BLOCKED" as const,
              badge: "⚠ BLOCKED",
              detail: "Attack/off-topic halted",
              badgeClass: "bg-amber-50 text-amber-800 border-amber-300",
              cardClass: "border-amber-200 bg-amber-50/15",
            }
          : auditLogs.length > 0
          ? {
              state: "COMPLETED" as const,
              badge: "✓ PASSED",
              detail: "6 layers enforced",
              badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
              cardClass: "border-slate-200 bg-white",
            }
          : {
              state: "WAITING" as const,
              badge: "◌ ACTIVE",
              detail: "6 layers standing by",
              badgeClass: "bg-slate-100 text-slate-600 border-slate-200",
              cardClass: "border-slate-200 bg-white",
            };

      default:
        return {
          state: "WAITING" as const,
          badge: "◌ WAITING",
          detail: "Standby",
          badgeClass: "bg-slate-100 text-slate-500 border-slate-200",
          cardClass: "border-slate-200 bg-white",
        };
    }
  };

  const recentActivities = auditLogs.slice(0, 6);

  return (
    <div className="card bg-white border border-slate-200 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between bg-slate-50/60">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-600">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
              Agent Architecture &amp; Workflow
              {isRunning && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 border border-blue-200">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  RECONCILING
                </span>
              )}
            </h3>
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 cursor-pointer font-medium"
          aria-label={isExpanded ? "Collapse workflow" : "Expand workflow"}
        >
          <span>{isExpanded ? "Hide Details" : "Show Workflow"}</span>
          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {isExpanded && (
        <div className="p-5 space-y-5">
          {/* ── 6-Stage Deterministic Processing Flow ── */}
          <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-3.5">
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-700">
                  Processing Flow:
                </span>
                <span className="text-[11px] text-slate-500 hidden sm:inline">
                  Deterministic Python (Pandas/NumPy) Pipeline → Evidence-Grounded Q&amp;A
                </span>
              </div>
              <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                STRICT SEPARATION
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-6 gap-2">
              {[
                {
                  id: "upload",
                  label: "1. Upload",
                  desc: "All files ingested",
                  done: hasDocs,
                  active: !hasDocs,
                },
                {
                  id: "schema",
                  label: "2. Schema Detection",
                  desc: "Columns inspected",
                  done: hasSchemaDetected || hasReconciliation,
                  active: hasDocs && !hasSchemaDetected && !hasReconciliation,
                },
                {
                  id: "mapping",
                  label: "3. Column Mapping",
                  desc: "Semantics mapped",
                  done: hasColumnsMapped || hasReconciliation,
                  active: hasDocs && !hasColumnsMapped && !hasReconciliation,
                },
                {
                  id: "reconciliation",
                  label: "4. Python Reconcile",
                  desc: "Pandas + NumPy engine",
                  done: hasPythonRecon,
                  active: isRunning,
                },
                {
                  id: "results",
                  label: "5. Structured Results",
                  desc: "Provenance & deltas",
                  done: hasReconciliation,
                  active: isRunning,
                },
                {
                  id: "qa",
                  label: "6. Q&A Copilot",
                  desc: "Grounded in results",
                  done: hasQA,
                  active: hasReconciliation,
                },
              ].map((stage) => (
                <div
                  key={stage.id}
                  className={`p-2 rounded-lg border text-xs transition-all ${
                    stage.done
                      ? "bg-emerald-50/60 border-emerald-200 text-emerald-900"
                      : stage.active
                      ? "bg-blue-50 border-blue-300 text-blue-900 ring-2 ring-blue-500/10"
                      : "bg-white border-slate-200 text-slate-500 opacity-75"
                  }`}
                >
                  <div className="flex items-center gap-1.5 font-bold mb-0.5">
                    {stage.done ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                    ) : stage.active && isRunning ? (
                      <Loader2 className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />
                    ) : (
                      <div className="w-1.5 h-1.5 rounded-full bg-slate-300 shrink-0" />
                    )}
                    <span className="truncate">{stage.label}</span>
                  </div>
                  <div className="text-[10px] text-slate-500 truncate">{stage.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Horizontal Connected Workflow Pipeline ── */}
          <div className="overflow-x-auto scroll-x-afford pb-1" tabIndex={0} aria-label="Agent workflow pipeline, scroll horizontally for all agents">
            <div className="flex items-center min-w-[700px] justify-between gap-2">
              {WORKFLOW_AGENTS.map((agent, idx) => {
                const Icon = agent.icon;
                const status = getAgentStatus(agent.id);
                const isLast = idx === WORKFLOW_AGENTS.length - 1;

                return (
                  <React.Fragment key={agent.id}>
                    <div
                      className={`flex-1 min-w-[110px] p-3 rounded-xl border transition-all ${status.cardClass}`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <Icon className="w-4 h-4 text-slate-700" />
                        <span
                          className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full border ${status.badgeClass}`}
                        >
                          {status.badge}
                        </span>
                      </div>
                      <div className="font-semibold text-xs text-slate-900 leading-tight">
                        {agent.shortName}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1 font-mono truncate" title={status.detail}>
                        {status.detail}
                      </div>
                    </div>

                    {!isLast && (
                      <div className="shrink-0 flex items-center text-slate-300 px-0.5">
                        <div className="w-3 h-[2px] bg-slate-200" />
                        <ArrowRight className="w-3 h-3 text-slate-300" />
                      </div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>

          {/* ── Compact Event Timeline (Clean & Scannable) ── */}
          <div className="pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2.5">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Real Graph &amp; Tool Events ({auditLogs.length} logged)
              </h4>
              <span className="text-[10px] text-slate-400 font-mono">Append-only audit trail</span>
            </div>

            {recentActivities.length === 0 ? (
              <div className="text-center py-5 border border-dashed border-slate-200 rounded-lg text-slate-400 text-xs">
                No events in current thread. Upload documents or run reconciliation to observe live telemetry.
              </div>
            ) : (
              <div className="space-y-1.5 font-mono text-xs">
                {recentActivities.map((log) => {
                  const isBlocked = log.action.includes("BLOCKED") || log.action.includes("DENIED");
                  const isCompleted = log.action.includes("COMPLETED");
                  const isTool = log.action.includes("TOOL");

                  return (
                    <div
                      key={log.id}
                      className="flex items-start sm:items-center justify-between gap-3 px-3 py-2 rounded-lg bg-slate-50/70 hover:bg-slate-100/80 border border-slate-200/60 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-wrap sm:flex-nowrap">
                        {/* Time */}
                        <span className="text-[10px] text-slate-400 w-16 shrink-0">
                          {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "—"}
                        </span>

                        {/* Status Icon / Bullet */}
                        <span
                          className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                            isBlocked
                              ? "bg-amber-500 ring-2 ring-amber-400/30"
                              : isCompleted
                              ? "bg-emerald-500 ring-2 ring-emerald-400/30"
                              : isTool
                              ? "bg-sky-500 ring-2 ring-sky-400/30"
                              : "bg-blue-500 ring-2 ring-blue-400/30"
                          }`}
                        />

                        {/* Agent */}
                        <span className="font-semibold text-slate-800 text-[11px] w-28 shrink-0 truncate">
                          {log.agent || "System"}
                        </span>

                        {/* Action Badge */}
                        <span
                          className={`text-[10px] px-1.5 py-0.2 rounded border font-semibold shrink-0 ${
                            isBlocked
                              ? "bg-amber-50 text-amber-800 border-amber-200"
                              : isCompleted
                              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                              : "bg-slate-100 text-slate-700 border-slate-200"
                          }`}
                        >
                          {log.action}
                        </span>

                        {/* Result summary / Tool */}
                        <span className="text-slate-600 text-[11px] truncate font-sans">
                          {log.tool ? `tool: ${log.tool}` : log.result_summary || "Completed"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
