"use client";

import React, { useEffect, useState } from "react";
import { Gauge, Target, BarChart3, Zap, FlaskConical, RefreshCw } from "lucide-react";
import { api, MetricsData } from "@/lib/api";

interface EvaluationViewProps {
  threadId: string;
  hasRun: boolean;
}

/**
 * Honest evaluation panel:
 * - Shows precision/recall/F1/accuracy ONLY when the run was evaluated
 *   against an authorized benchmark ground truth.
 * - Otherwise explains plainly that evaluation metrics don't apply to
 *   user-document runs.
 */
export const EvaluationView: React.FC<EvaluationViewProps> = ({ threadId, hasRun }) => {
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setMetrics(await api.getMetrics(threadId));
    } catch (e: any) {
      setError(e?.message || "Could not load metrics.");
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  if (!hasRun) {
    return (
      <div className="card p-10 text-center space-y-3">
        <FlaskConical className="w-10 h-10 mx-auto text-slate-300" />
        <h3 className="text-sm font-semibold text-slate-800">No reconciliation run yet</h3>
        <p className="text-xs text-slate-500 max-w-md mx-auto">
          Run a reconciliation first — its processing stats and evaluation status will appear here.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="card p-6 space-y-3" aria-label="Loading run metrics">
        <div className="skeleton h-5 w-40" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-16 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (error && !metrics) {
    return (
      <div className="card p-10 text-center space-y-3">
        <Gauge className="w-10 h-10 mx-auto text-slate-300" />
        <h3 className="text-sm font-semibold text-slate-800">Metrics unavailable</h3>
        <p className="text-xs text-slate-500 max-w-md mx-auto">{error}</p>
        <button
          onClick={load}
          className="mx-auto flex items-center gap-1.5 text-xs font-semibold text-blue-600 hover:text-blue-700 cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Retry
        </button>
      </div>
    );
  }

  if (!metrics) return null;

  // Not evaluated: be explicit, show only real operational stats.
  if (!metrics.evaluated) {
    return (
      <div className="space-y-5">
        <div className="card p-6 space-y-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-slate-100 rounded-lg flex items-center justify-center">
              <FlaskConical className="w-4.5 h-4.5 text-slate-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Run metrics</h3>
              <p className="text-xs text-slate-400 font-mono">run {metrics.run_id}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2">
            <Metric label="Total records" value={metrics.total_records.toLocaleString()} icon={<BarChart3 className="w-4 h-4 text-indigo-500" />} />
            <Metric label="Matched pairs" value={metrics.matched_count.toLocaleString()} icon={<Target className="w-4 h-4 text-emerald-500" />} />
            <Metric label="Match rate" value={`${metrics.match_rate.toFixed(1)}%`} icon={<Gauge className="w-4 h-4 text-blue-500" />} />
            <Metric label="Throughput" value={`${metrics.throughput_records_sec.toFixed(0)} rec/s`} icon={<Zap className="w-4 h-4 text-amber-500" />} />
          </div>
        </div>

        <div className="card p-6 border-dashed">
          <div className="flex items-start gap-3">
            <FlaskConical className="w-5 h-5 text-slate-400 shrink-0 mt-0.5" />
            <div className="space-y-1.5">
              <h4 className="text-sm font-semibold text-slate-800">
                Evaluation not available for this run
              </h4>
              <p className="text-xs text-slate-500 leading-relaxed max-w-2xl">
                Precision, recall, F1 and accuracy require an authorized ground truth associated with
                the run. This thread reconciles your uploaded documents, and no benchmark answer key
                applies to them — so instead of showing fabricated metrics, they are reported as
                <span className="font-semibold text-slate-700"> N/A</span>. Ground truth is only used
                by the explicit benchmark evaluation pipeline.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Evaluated run — real benchmark numbers
  const core = [
    { label: "Precision", value: `${(metrics.precision ?? 0).toFixed(1)}%`, icon: <Target className="w-4 h-4 text-emerald-500" />, accent: "border-l-emerald-500", iconBg: "bg-emerald-50" },
    { label: "Recall", value: `${(metrics.recall ?? 0).toFixed(1)}%`, icon: <Gauge className="w-4 h-4 text-blue-500" />, accent: "border-l-blue-500", iconBg: "bg-blue-50" },
    { label: "F1-Score", value: `${(metrics.f1_score ?? 0).toFixed(1)}%`, icon: <BarChart3 className="w-4 h-4 text-indigo-500" />, accent: "border-l-indigo-500", iconBg: "bg-indigo-50" },
    { label: "Accuracy", value: `${(metrics.accuracy ?? 0).toFixed(1)}%`, icon: <Zap className="w-4 h-4 text-amber-500" />, accent: "border-l-amber-500", iconBg: "bg-amber-50" },
  ];

  const cm = [
    { label: "True Positives", value: metrics.true_positives ?? 0, cls: "text-emerald-600 bg-emerald-50 border-emerald-100" },
    { label: "True Negatives", value: metrics.true_negatives ?? 0, cls: "text-blue-600 bg-blue-50 border-blue-100" },
    { label: "False Positives", value: metrics.false_positives ?? 0, cls: "text-slate-600 bg-slate-50 border-slate-200" },
    { label: "False Negatives", value: metrics.false_negatives ?? 0, cls: "text-amber-600 bg-amber-50 border-amber-100" },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        {core.map((m, idx) => (
          <div key={idx} className={`card border-l-[3px] ${m.accent} p-5 animate-slide-up`}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-slate-500">{m.label}</span>
              <div className={`w-8 h-8 ${m.iconBg} rounded-lg flex items-center justify-center`}>{m.icon}</div>
            </div>
            <div className="text-2xl font-bold text-slate-900 mono-fin tracking-tight">
              {m.value}
            </div>
          </div>
        ))}
      </div>

      <div className="card p-5 space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">
          Confusion matrix
          <span className="text-slate-400 font-normal ml-1.5">
            ({metrics.total_ground_truth_cases ?? 0} ground truth cases)
          </span>
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {cm.map((cell, idx) => (
            <div key={idx} className={`border p-4 rounded-xl ${cell.cls}`}>
              <div className="text-[10px] uppercase font-semibold tracking-wide opacity-70">{cell.label}</div>
              <div className="text-2xl font-bold mono-fin mt-1.5">{cell.value}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
          <Metric label="Total records" value={metrics.total_records.toLocaleString()} icon={<BarChart3 className="w-4 h-4 text-indigo-500" />} />
          <Metric label="Match rate" value={`${metrics.match_rate.toFixed(1)}%`} icon={<Gauge className="w-4 h-4 text-blue-500" />} />
          <Metric label="Processing time" value={`${metrics.processing_time_sec.toFixed(2)}s`} icon={<Zap className="w-4 h-4 text-amber-500" />} />
          <Metric label="Throughput" value={`${metrics.throughput_records_sec.toFixed(0)} rec/s`} icon={<Zap className="w-4 h-4 text-amber-500" />} />
        </div>
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: string; icon: React.ReactNode }> = ({ label, value, icon }) => (
  <div className="bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-3">
    <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
      {icon}
      {label}
    </div>
    <div className="text-sm font-bold text-slate-800 mono-fin mt-1">{value}</div>
  </div>
);
