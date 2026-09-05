"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { ThreadSidebar } from "@/components/ThreadSidebar";
import { DocumentWorkspace } from "@/components/DocumentWorkspace";
import { ReconciliationControl } from "@/components/ReconciliationControl";
import { OverviewCards } from "@/components/OverviewCards";
import { ResultsView } from "@/components/ResultsView";
import { ExceptionInvestigator } from "@/components/ExceptionInvestigator";
import { EvaluationView } from "@/components/EvaluationView";
import { ChatPanel } from "@/components/ChatPanel";
import { AuditTrailView } from "@/components/AuditTrailView";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";
import { CashForecastView } from "@/components/CashForecastView";
import { TaxMatchView } from "@/components/TaxMatchView";
import {
  CheckCircle2, AlertTriangle, BarChart3, MessageSquare, ShieldCheck,
  Menu, FileText, WifiOff, TrendingUp, Percent,
} from "lucide-react";
import {
  api, ThreadItem, ThreadDocumentItem, LatestRun, MatchItem, ExceptionItem, AuditLogItem,
} from "@/lib/api";

type Tab = "overview" | "matches" | "qa" | "forecast" | "tax" | "exceptions" | "evaluation" | "audit";

const TABS = [
  { id: "overview" as const, label: "Overview", icon: FileText },
  { id: "matches" as const, label: "Reconciliation", icon: CheckCircle2 },
  { id: "qa" as const, label: "Settlement Q&A", icon: MessageSquare },
  { id: "forecast" as const, label: "Cash Forecast", icon: TrendingUp },
  { id: "tax" as const, label: "Tax Matcher", icon: Percent },
  { id: "exceptions" as const, label: "Exceptions", icon: AlertTriangle },
  { id: "evaluation" as const, label: "Evaluation", icon: BarChart3 },
  { id: "audit" as const, label: "Audit", icon: ShieldCheck },
];

export default function Home() {
  // ── Thread selection ──
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [backendDown, setBackendDown] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);

  // ── Thread data ──
  const [documents, setDocuments] = useState<ThreadDocumentItem[]>([]);
  const [latestRun, setLatestRun] = useState<LatestRun | null>(null);
  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [matchCategory, setMatchCategory] = useState("ALL");
  const [matchSearch, setMatchSearch] = useState("");
  const [exceptionReason, setExceptionReason] = useState("ALL");
  const [exceptionCategory, setExceptionCategory] = useState("ALL");
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [totalExceptions, setTotalExceptions] = useState(0);
  const [exceptionsLoading, setExceptionsLoading] = useState(false);
  const [presetFilter, setPresetFilter] = useState<{ reason?: string; category?: string } | null>(null);

  // ── Run state ──
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [stepProgress, setStepProgress] = useState<string[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);

  // Stale-request guard: only the latest requested thread may write results.
  const activeThreadRef = useRef<string | null>(null);

  // ── Initial load ──
  const refreshThreads = useCallback(async (): Promise<ThreadItem[]> => {
    const list = await api.listThreads();
    setThreads(list);
    return list;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        setBackendDown(false);
        const list = await refreshThreads();
        if (list.length > 0) {
          setActiveThreadId(list[0].id);
        } else {
          const created = await api.createThread("My First Reconciliation");
          setThreads([created]);
          setActiveThreadId(created.id);
        }
      } catch {
        setBackendDown(true);
      }
    })();
  }, [refreshThreads]);

  const loadResults = useCallback(async (threadId: string, category: string, search: string) => {
    setMatchesLoading(true);
    try {
      const res = await api.getResults(threadId, category, search);
      if (activeThreadRef.current !== threadId) return;
      setMatches(res.matches);
      setTotalMatches(res.total);
    } catch {
      if (activeThreadRef.current !== threadId) return;
      setMatches([]);
      setTotalMatches(0);
    } finally {
      if (activeThreadRef.current === threadId) setMatchesLoading(false);
    }
  }, []);

  const loadExceptions = useCallback(async (threadId: string, reason: string, category: string) => {
    setExceptionsLoading(true);
    try {
      const res = await api.getExceptions(threadId, reason, category);
      if (activeThreadRef.current !== threadId) return;
      setExceptions(res.exceptions);
      setTotalExceptions(res.total);
    } catch {
      if (activeThreadRef.current !== threadId) return;
      setExceptions([]);
      setTotalExceptions(0);
    } finally {
      if (activeThreadRef.current === threadId) setExceptionsLoading(false);
    }
  }, []);

  // ── Load thread context ──
  const loadThreadData = useCallback(async (threadId: string) => {
    activeThreadRef.current = threadId;
    const th = await api.getThread(threadId).catch(() => null);
    if (activeThreadRef.current !== threadId) return;

    // Reset view state (after the await boundary) so stale data never leaks across threads
    setMatchCategory("ALL");
    setMatchSearch("");
    setExceptionReason("ALL");
    setExceptionCategory("ALL");
    setPresetFilter(null);
    setRunError(null);
    setStepProgress([]);
    setMatches([]);
    setTotalMatches(0);
    setExceptions([]);
    setTotalExceptions(0);

    if (!th) {
      setDocuments([]);
      setLatestRun(null);
      return;
    }

    setDocuments(th.documents || []);
    setLatestRun(th.latest_run);
    setRunId(th.latest_run?.id ?? null);
    if (th.latest_run) void loadResults(threadId, "ALL", "");
    void loadExceptions(threadId, "ALL", "ALL");
    void api.getAuditTrail(threadId).then((logs) => {
      if (activeThreadRef.current === threadId) setAuditLogs(logs);
    }).catch(() => {
      if (activeThreadRef.current === threadId) setAuditLogs([]);
    });
  }, [loadResults, loadExceptions]);

  useEffect(() => {
    if (activeThreadId) void loadThreadData(activeThreadId);
  }, [activeThreadId, loadThreadData]);

  // ── Handlers ──
  const handleCreateThread = async () => {
    try {
      const t = await api.createThread(`Analysis ${new Date().toLocaleDateString()}`);
      await refreshThreads();
      setActiveThreadId(t.id);
      setActiveTab("overview");
    } catch {
      setBackendDown(true);
    }
  };

  const handleDeleteThread = async (id: string) => {
    try {
      await api.deleteThread(id);
      const list = await refreshThreads();
      if (activeThreadId === id) {
        setActiveThreadId(list.length > 0 ? list[0].id : null);
      }
    } catch {
      /* keep state; surface via backendDown only for hard failures */
    }
  };

  const handleRenameThread = async (id: string, title: string) => {
    try {
      await api.renameThread(id, title);
      await refreshThreads();
    } catch {
      /* ignore */
    }
  };

  const handleRunReconciliation = async () => {
    if (!activeThreadId || isRunning) return;
    setIsRunning(true);
    setRunError(null);
    setStepProgress([]);
    try {
      const res = await api.reconcileThread(activeThreadId);
      if (res.run_id) setRunId(res.run_id);
      if (res.step_progress) setStepProgress(res.step_progress);
      const th = await api.getThread(activeThreadId);
      setDocuments(th.documents || []);
      setLatestRun(th.latest_run);
      setRunId(th.latest_run?.id ?? res.run_id);
      await Promise.all([
        loadResults(activeThreadId, "ALL", ""),
        loadExceptions(activeThreadId, "ALL", "ALL"),
        api.getAuditTrail(activeThreadId).then(setAuditLogs).catch(() => {}),
      ]);
      await refreshThreads();
    } catch (e: any) {
      setRunError(e?.message || "Reconciliation failed.");
    } finally {
      setIsRunning(false);
    }
  };

  const handleOpenRecord = (recordId: string) => {
    setActiveTab("qa");
    setDocsOpen(false);
    // The chat input is pre-filled by a custom event the ChatPanel listens for
    window.dispatchEvent(
      new CustomEvent("copilot:ask", { detail: { question: `What is the status of ${recordId}?` } })
    );
  };

  const jumpToExceptions = useCallback((filter?: { category?: string }) => {
    setPresetFilter(filter?.category ? { category: filter.category } : null);
    setExceptionCategory(filter?.category || "ALL");
    setExceptionReason("ALL");
    if (activeThreadId) void loadExceptions(activeThreadId, "ALL", filter?.category || "ALL");
    setActiveTab("exceptions");
  }, [activeThreadId, loadExceptions]);

  useEffect(() => {
    const handleJumpTab = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.tab) {
        if (detail.tab === "exceptions") {
          jumpToExceptions(detail.category ? { category: detail.category } : undefined);
        } else {
          setActiveTab(detail.tab);
        }
      }
    };
    window.addEventListener("navigation:jump-tab", handleJumpTab as EventListener);
    return () => window.removeEventListener("navigation:jump-tab", handleJumpTab as EventListener);
  }, [jumpToExceptions]);

  const threadTitle = threads.find((t) => t.id === activeThreadId)?.title || "…";

  // ── Backend-down screen ──
  if (backendDown) {
    return (
      <div className="min-h-screen bg-[var(--bg-page)] flex items-center justify-center p-6">
        <div className="card max-w-md w-full p-10 text-center space-y-4">
          <WifiOff className="w-12 h-12 mx-auto text-slate-300" />
          <h1 className="text-lg font-bold text-slate-900">Backend unavailable</h1>
          <p className="text-sm text-slate-500">
            The Finance Controller API is not reachable. No cached or sample data is shown —
            start the backend and retry.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all cursor-pointer"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-page)] flex">
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={(id) => {
          setActiveThreadId(id);
          setActiveTab("overview");
        }}
        onCreateThread={handleCreateThread}
        onDeleteThread={handleDeleteThread}
        onRenameThread={handleRenameThread}
        isOpen={sidebarOpen}
        onToggleOpen={() => setSidebarOpen((p) => !p)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="bg-white/80 backdrop-blur-xl border-b border-slate-200/80 sticky top-0 z-30">
          <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={() => setSidebarOpen((prev) => !prev)}
                className="lg:hidden p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 cursor-pointer"
                aria-label="Toggle sidebar"
              >
                <Menu className="w-5 h-5" />
              </button>
              <div className="flex items-center gap-2 text-sm min-w-0">
                <span className="font-bold text-slate-900 shrink-0">Finance Controller</span>
                <span className="text-slate-300 font-light shrink-0">/</span>
                <span className="text-slate-600 font-medium font-mono truncate" title={threadTitle}>
                  {threadTitle}
                </span>
              </div>
            </div>



            <div className="flex items-center gap-2.5 shrink-0">
              <button
                onClick={() => setDocsOpen(true)}
                className="flex items-center gap-1.5 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold px-3 py-2 rounded-lg transition-all shadow-xs cursor-pointer"
              >
                <FileText className="w-3.5 h-3.5 text-blue-500" />
                <span className="hidden sm:inline">Documents</span>
                <span className="bg-blue-50 text-blue-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {documents.length}
                </span>
              </button>
              <button
                onClick={handleRunReconciliation}
                disabled={isRunning || documents.filter((d) => d.processing_status === "PROCESSED").length === 0}
                className="flex items-center gap-2 bg-gradient-to-b from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold px-4 py-2 rounded-lg transition-all shadow-sm cursor-pointer active:scale-[0.98]"
              >
                <CheckCircle2 className={`w-3.5 h-3.5 ${isRunning ? "animate-spin" : ""}`} />
                <span>{isRunning ? "Reconciling…" : "Run Reconciliation"}</span>
              </button>
            </div>
          </div>
        </header>

        <main className="max-w-[1400px] w-full mx-auto px-4 sm:px-8 py-6 space-y-6">
          {!activeThreadId ? (
            <div className="card p-12 text-center text-sm text-slate-400">
              Create or select an analysis thread to begin.
            </div>
          ) : (
            <>
              <ReconciliationControl
                documents={documents}
                latestRun={latestRun}
                isRunning={isRunning}
                onRun={handleRunReconciliation}
                runError={runError}
                activeSteps={stepProgress}
              />

              {activeTab === "overview" && (
                <OverviewCards
                  latestRun={latestRun}
                  hasDocuments={documents.length > 0}
                  documentCount={documents.length}
                  onSelect={(tab, filter) => {
                    if (tab === "documents") setDocsOpen(true);
                    else if (tab === "matches") {
                      loadResults(activeThreadId, matchCategory, matchSearch);
                      setActiveTab("matches");
                    } else if (tab === "exceptions") {
                      jumpToExceptions(filter?.category ? { category: filter.category } : undefined);
                    }
                  }}
                />
              )}

              {/* Tabs */}
              <div className="space-y-4">
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200/80 w-fit max-w-full overflow-x-auto scroll-x-afford" role="tablist" aria-label="Workspace views">
                  {TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    const badge =
                      tab.id === "matches" ? (latestRun ? totalMatches.toLocaleString() : null)
                      : tab.id === "exceptions" ? (latestRun && totalExceptions > 0 ? totalExceptions.toLocaleString() : null)
                      : null;
                    return (
                      <button
                        key={tab.id}
                        role="tab"
                        aria-selected={isActive}
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                          isActive ? "bg-white text-slate-900 shadow-sm font-semibold" : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <Icon className={`w-3.5 h-3.5 ${isActive ? "text-blue-600" : "text-slate-400"}`} />
                        <span>{tab.label}</span>
                        {badge !== null && (
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${isActive ? "bg-blue-50 text-blue-700" : "bg-slate-200 text-slate-600"}`}>
                            {badge}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>

                <div className="animate-fade-in">
                  {activeTab === "overview" && (
                    <div className="space-y-4">
                      <AgentActivityPanel
                        auditLogs={auditLogs}
                        isRunning={isRunning}
                      />
                      {latestRun === null && documents.length === 0 && (
                        <EmptyWorkspace onUpload={() => setDocsOpen(true)} />
                      )}
                      {latestRun === null && documents.length > 0 && (
                        <PendingRunNotice onRun={handleRunReconciliation} disabled={isRunning} />
                      )}
                      {latestRun !== null && (
                        <RunSummary latestRun={latestRun} onJumpExceptions={() => jumpToExceptions({ category: "MATERIAL" })} />
                      )}
                    </div>
                  )}

                  {activeTab === "matches" && (
                    <ResultsView
                      matches={matches}
                      totalMatches={totalMatches}
                      onSearchChange={(q) => {
                        setMatchSearch(q);
                        if (activeThreadId) void loadResults(activeThreadId, matchCategory, q);
                      }}
                      onCategoryChange={(cat) => {
                        setMatchCategory(cat);
                        if (activeThreadId) void loadResults(activeThreadId, cat, matchSearch);
                      }}
                      selectedCategory={matchCategory}
                      isLoading={matchesLoading}
                    />
                  )}

                  {activeTab === "exceptions" && (
                    <ExceptionInvestigator
                      exceptions={exceptions}
                      totalExceptions={totalExceptions}
                      onReasonChange={(reason) => {
                        setExceptionReason(reason);
                        if (activeThreadId) void loadExceptions(activeThreadId, reason, exceptionCategory);
                      }}
                      selectedReason={exceptionReason}
                      onCategoryChange={(cat) => {
                        setExceptionCategory(cat);
                        if (activeThreadId) void loadExceptions(activeThreadId, exceptionReason, cat);
                      }}
                      onOpenRecord={handleOpenRecord}
                      isLoading={exceptionsLoading}
                      presetFilter={presetFilter}
                      onClearPreset={() => {
                        setPresetFilter(null);
                        setExceptionCategory("ALL");
                        if (activeThreadId) void loadExceptions(activeThreadId, exceptionReason, "ALL");
                      }}
                    />
                  )}

                  {activeTab === "evaluation" && (
                    <EvaluationView threadId={activeThreadId} hasRun={!!latestRun} />
                  )}

                  {activeTab === "qa" && (
                    <div className="max-w-3xl mx-auto">
                      <ChatPanel
                        threadId={activeThreadId}
                        runId={runId}
                        onOpenRecord={handleOpenRecord}
                        onReconciled={() => loadThreadData(activeThreadId)}
                      />
                    </div>
                  )}

                  {activeTab === "forecast" && (
                    <CashForecastView
                      threadId={activeThreadId}
                      hasDocuments={documents.length > 0}
                      onUploadClick={() => setDocsOpen(true)}
                    />
                  )}

                  {activeTab === "tax" && (
                    <TaxMatchView
                      threadId={activeThreadId}
                      hasDocuments={documents.length > 0}
                      onUploadClick={() => setDocsOpen(true)}
                    />
                  )}

                  {activeTab === "audit" && (
                    <div className="max-w-3xl mx-auto">
                      <AuditTrailView threadId={activeThreadId} />
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      <DocumentWorkspace
        isOpen={docsOpen}
        onClose={() => setDocsOpen(false)}
        threadId={activeThreadId || ""}
        documents={documents}
        onDocumentsChanged={() => {
          if (activeThreadId) {
            api.getThread(activeThreadId).then((th) => {
              setDocuments(th.documents || []);
              setLatestRun(th.latest_run);
            }).catch(() => undefined);
          }
        }}
      />
    </div>
  );
}

/* ── Empty state ── */
const EmptyWorkspace: React.FC<{ onUpload: () => void }> = ({ onUpload }) => (
  <div className="card p-12 text-center space-y-4">
    <div className="w-14 h-14 mx-auto bg-blue-50 rounded-2xl flex items-center justify-center">
      <FileText className="w-7 h-7 text-blue-500" />
    </div>
    <h3 className="text-base font-bold text-slate-900">Start a new reconciliation</h3>
    <p className="text-sm text-slate-500 max-w-md mx-auto leading-relaxed">
      Upload your source documents — for example an internal ledger export and the corresponding
      bank statement. The engine will parse, fingerprint, and reconcile them deterministically.
    </p>
    <button
      onClick={onUpload}
      className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all cursor-pointer"
    >
      <FileText className="w-4 h-4" />
      Upload documents
    </button>
  </div>
);

const PendingRunNotice: React.FC<{ onRun: () => void; disabled: boolean }> = ({ onRun, disabled }) => (
  <div className="card p-8 text-center space-y-3">
    <AlertTriangle className="w-10 h-10 mx-auto text-amber-400" />
    <h3 className="text-sm font-bold text-slate-900">Documents ready — reconciliation pending</h3>
    <p className="text-xs text-slate-500">
      Your documents are parsed and fingerprinted. Run the reconciliation to produce matches and exceptions.
    </p>
    <button
      onClick={onRun}
      disabled={disabled}
      className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all cursor-pointer"
    >
      <CheckCircle2 className="w-4 h-4" />
      Run Reconciliation
    </button>
  </div>
);

const RunSummary: React.FC<{ latestRun: LatestRun; onJumpExceptions: () => void }> = ({ latestRun, onJumpExceptions }) => (
  <div className="card p-5">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <div className="flex items-center gap-2">
          <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200">Completed</span>
          <span className="text-xs font-mono text-slate-400">run {latestRun.id}</span>
        </div>
        <h3 className="text-sm font-bold text-slate-900 mt-2">
          {latestRun.matched_count.toLocaleString()} matched · {latestRun.exceptions_count.toLocaleString()} exceptions ·{" "}
          {latestRun.match_rate.toFixed(1)}% match rate
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          {latestRun.total_records.toLocaleString()} records processed in {latestRun.processing_time_sec.toFixed(2)}s
          {" "}({latestRun.throughput_records_sec.toFixed(0)} rec/s)
          {latestRun.evaluated
            ? " · evaluated against authorized benchmark ground truth"
            : " · evaluation N/A (no authorized ground truth for user documents)"}
        </p>
      </div>
      {latestRun.exceptions_count > 0 && (
        <button
          onClick={onJumpExceptions}
          className="flex items-center gap-2 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 text-xs font-semibold px-4 py-2.5 rounded-xl transition-all cursor-pointer"
        >
          <AlertTriangle className="w-4 h-4" />
          Investigate {latestRun.exceptions_count} exception{latestRun.exceptions_count === 1 ? "" : "s"}
        </button>
      )}
    </div>
  </div>
);
