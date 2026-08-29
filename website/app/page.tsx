"use client";

import React, { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { FileUploader, UploadedFileItem } from "@/components/FileUploader";
import { RunProgress } from "@/components/RunProgress";
import { MetricCards } from "@/components/MetricCards";
import { ReconciliationTable } from "@/components/ReconciliationTable";
import { ExceptionTable } from "@/components/ExceptionTable";
import { ExceptionDetailModal } from "@/components/ExceptionDetailModal";
import { EvaluationView } from "@/components/EvaluationView";
import { ChatPanel } from "@/components/ChatPanel";
import {
  api,
  ReconciliationRunSummary,
  MatchItem,
  ExceptionItem,
  EvaluationMetricData
} from "@/lib/api";
import {
  Layers,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  MessageSquare,
  Sparkles,
  ShieldCheck
} from "lucide-react";

export default function Home() {
  // State
  const [prompt, setPrompt] = useState(
    "Reconcile these financial records and identify anything that doesn't match."
  );
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileItem[]>([
    { id: "synth_1", name: "source_a_ledger.csv", size: 34200, type: "csv" },
    { id: "synth_2", name: "source_b_bank.csv", size: 32800, type: "csv" },
    { id: "synth_3", name: "source_c_payouts.xlsx", size: 18400, type: "xlsx" }
  ]);
  const [isRunning, setIsRunning] = useState(false);
  const [stepIndex, setStepIndex] = useState(7);
  const [activeTab, setActiveTab] = useState<"matches" | "exceptions" | "evaluation" | "qa">("matches");

  // Reconciliation Results
  const [runId, setRunId] = useState<string | null>(null);
  const [summary, setSummary] = useState<ReconciliationRunSummary>({
    total_records: 380,
    matched_records: 154,
    unmatched_records: 35,
    exception_records: 35,
    match_rate: 81.1,
    accuracy: 96.9,
    precision: 100.0,
    recall: 96.2,
    f1_score: 98.1,
    processing_time_sec: 0.61,
    throughput_records_sec: 622.5,
    status: "COMPLETED"
  });

  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [totalMatches, setTotalMatches] = useState(154);
  const [matchCategory, setMatchCategory] = useState("ALL");
  const [matchSearch, setMatchSearch] = useState("");

  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [totalExceptions, setTotalExceptions] = useState(35);
  const [exceptionReason, setExceptionReason] = useState("ALL");
  const [selectedException, setSelectedException] = useState<ExceptionItem | null>(null);

  const [metrics, setMetrics] = useState<EvaluationMetricData | null>(null);
  const [recentRuns, setRecentRuns] = useState<any[]>([]);

  // Load initial run on mount
  useEffect(() => {
    handleRunReconciliation();
  }, []);

  const handleRunReconciliation = async () => {
    setIsRunning(true);
    setStepIndex(0);

    // Simulate animated stepper while LangGraph executes
    const stepInterval = setInterval(() => {
      setStepIndex((prev) => (prev < 6 ? prev + 1 : prev));
    }, 200);

    try {
      const runRes = await api.runReconciliation(prompt, true);
      clearInterval(stepInterval);
      setStepIndex(7);

      const newRunId = runRes.run_id;
      setRunId(newRunId);

      // Load run details
      const details = await api.getRunDetails(newRunId);
      setSummary(details.summary);

      // Load matches & exceptions
      const matchesData = await api.getMatches(newRunId, matchCategory, matchSearch);
      setMatches(matchesData.matches || []);
      setTotalMatches(matchesData.total || 0);

      const excData = await api.getExceptions(newRunId, exceptionReason);
      setExceptions(excData.exceptions || []);
      setTotalExceptions(excData.total || 0);

      // Load metrics
      try {
        const m = await api.getMetrics(newRunId);
        setMetrics(m);
      } catch (err) {
        // fallback
      }

      // Load recent runs
      try {
        const runs = await api.getAllRuns();
        setRecentRuns(runs || []);
      } catch (err) {}
    } catch (err: any) {
      console.error("Error executing reconciliation:", err);
    } finally {
      clearInterval(stepInterval);
      setIsRunning(false);
    }
  };

  const handleMatchSearch = async (query: string) => {
    setMatchSearch(query);
    if (!runId) return;
    try {
      const res = await api.getMatches(runId, matchCategory, query);
      setMatches(res.matches || []);
      setTotalMatches(res.total || 0);
    } catch (err) {}
  };

  const handleMatchCategory = async (cat: string) => {
    setMatchCategory(cat);
    if (!runId) return;
    try {
      const res = await api.getMatches(runId, cat, matchSearch);
      setMatches(res.matches || []);
      setTotalMatches(res.total || 0);
    } catch (err) {}
  };

  const handleExceptionReason = async (reason: string) => {
    setExceptionReason(reason);
    if (!runId) return;
    try {
      const res = await api.getExceptions(runId, reason);
      setExceptions(res.exceptions || []);
      setTotalExceptions(res.total || 0);
    } catch (err) {}
  };

  const handleLoadSyntheticBatch = () => {
    setUploadedFiles([
      { id: "synth_1", name: "source_a_ledger.csv", size: 34200, type: "csv" },
      { id: "synth_2", name: "source_b_bank.csv", size: 32800, type: "csv" },
      { id: "synth_3", name: "source_c_payouts.xlsx", size: 18400, type: "xlsx" }
    ]);
  };

  const handleSelectRecentRun = async (selectedRunId: string) => {
    setRunId(selectedRunId);
    try {
      const details = await api.getRunDetails(selectedRunId);
      setSummary(details.summary);
      const matchesData = await api.getMatches(selectedRunId);
      setMatches(matchesData.matches || []);
      setTotalMatches(matchesData.total || 0);
      const excData = await api.getExceptions(selectedRunId);
      setExceptions(excData.exceptions || []);
      setTotalExceptions(excData.total || 0);
      const m = await api.getMetrics(selectedRunId);
      setMetrics(m);
    } catch (err) {}
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col">
      {/* Top Navbar */}
      <Navbar
        onTriggerDemo={handleRunReconciliation}
        isRunning={isRunning}
        totalProcessed={summary?.total_records}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Workspace Command Header */}
        <WorkspaceHeader
          prompt={prompt}
          setPrompt={setPrompt}
          onExecute={handleRunReconciliation}
          isRunning={isRunning}
          recentRuns={recentRuns}
          onSelectRecentRun={handleSelectRecentRun}
        />

        {/* Multi-Document Uploader */}
        <FileUploader
          files={uploadedFiles}
          onAddFiles={(newFiles) => setUploadedFiles((prev) => [...prev, ...newFiles])}
          onRemoveFile={(id) => setUploadedFiles((prev) => prev.filter((f) => f.id !== id))}
          onLoadSyntheticBatch={handleLoadSyntheticBatch}
        />

        {/* Live LangGraph Stepper */}
        <RunProgress currentStepIndex={stepIndex} />

        {/* Summary Metric KPI Row */}
        <MetricCards summary={summary} />

        {/* Interactive Workspace Navigation Tabs */}
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200">
            <div className="flex space-x-2">
              <button
                onClick={() => setActiveTab("matches")}
                className={`flex items-center space-x-2 py-3 px-4 text-xs font-bold border-b-2 transition-all ${
                  activeTab === "matches"
                    ? "border-blue-600 text-blue-700 bg-blue-50/50"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
                }`}
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Matched Records ({totalMatches})</span>
              </button>

              <button
                onClick={() => setActiveTab("exceptions")}
                className={`flex items-center space-x-2 py-3 px-4 text-xs font-bold border-b-2 transition-all ${
                  activeTab === "exceptions"
                    ? "border-amber-500 text-amber-700 bg-amber-50/50"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
                }`}
              >
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <span>Exceptions & Discrepancies ({totalExceptions})</span>
              </button>

              <button
                onClick={() => setActiveTab("evaluation")}
                className={`flex items-center space-x-2 py-3 px-4 text-xs font-bold border-b-2 transition-all ${
                  activeTab === "evaluation"
                    ? "border-indigo-600 text-indigo-700 bg-indigo-50/50"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
                }`}
              >
                <ShieldCheck className="w-4 h-4 text-indigo-600" />
                <span>Ground Truth Benchmark ({summary.accuracy.toFixed(1)}%)</span>
              </button>

              <button
                onClick={() => setActiveTab("qa")}
                className={`flex items-center space-x-2 py-3 px-4 text-xs font-bold border-b-2 transition-all ${
                  activeTab === "qa"
                    ? "border-blue-600 text-blue-700 bg-blue-50/50"
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
                }`}
              >
                <MessageSquare className="w-4 h-4 text-blue-600" />
                <span>QA Copilot Chat</span>
              </button>
            </div>
          </div>

          {/* Tab Contents */}
          {activeTab === "matches" && (
            <ReconciliationTable
              matches={matches}
              totalMatches={totalMatches}
              onSearchChange={handleMatchSearch}
              onCategoryChange={handleMatchCategory}
              selectedCategory={matchCategory}
            />
          )}

          {activeTab === "exceptions" && (
            <ExceptionTable
              exceptions={exceptions}
              totalExceptions={totalExceptions}
              onSelectException={(exc) => setSelectedException(exc)}
              onReasonChange={handleExceptionReason}
              selectedReason={exceptionReason}
            />
          )}

          {activeTab === "evaluation" && (
            <EvaluationView metrics={metrics} summary={summary} />
          )}

          {activeTab === "qa" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <ChatPanel runId={runId || undefined} />
              </div>
              <div className="space-y-4">
                <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center space-x-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                    <span>Investigative Queries</span>
                  </h4>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    The QA Copilot uses direct SQLite database queries to answer questions without mathematical hallucinations.
                  </p>
                  <div className="space-y-2 text-xs">
                    <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700">
                      <strong>Specific Record:</strong> "Why was TXN-LEDGER-1184 not matched?"
                    </div>
                    <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700">
                      <strong>Amount Discrepancy:</strong> "Show all fees deducted on wire transfers"
                    </div>
                    <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700">
                      <strong>Operational Metrics:</strong> "What is our overall accuracy vs ground truth?"
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Exception Detail Inspector Modal */}
      <ExceptionDetailModal
        exception={selectedException}
        onClose={() => setSelectedException(null)}
      />
    </div>
  );
}
