const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface ReconciliationRunSummary {
  run_id?: string;
  id?: string;
  created_at?: string;
  status: string;
  user_prompt?: string;
  total_records: number;
  matched_records: number;
  unmatched_records: number;
  exception_records: number;
  match_rate: number;
  accuracy: number;
  precision?: number;
  recall?: number;
  f1_score?: number;
  processing_time_sec: number;
  throughput_records_sec: number;
}

export interface MatchItem {
  match_id: string;
  record_id_a: string;
  record_id_b: string;
  source_a: string;
  source_b: string;
  amount_a: number;
  amount_b: number;
  date_a?: string;
  date_b?: string;
  entity_a?: string;
  entity_b?: string;
  confidence_score: number;
  match_category: string;
  status: string;
  score_breakdown: Record<string, number>;
}

export interface CandidateItem {
  target_record_id: string;
  target_source: string;
  target_amount: number;
  target_date?: string;
  target_entity?: string;
  confidence_score: number;
  match_category: string;
  amount_diff: number;
  date_diff_days: number;
  notes?: string;
}

export interface ExceptionItem {
  exception_id: string;
  record_id: string;
  source: string;
  amount?: number;
  entity?: string;
  date?: string;
  reason_code: string;
  confidence: number;
  decision: string;
  explanation: string;
  amount_discrepancy: number;
  candidates: CandidateItem[];
}

export interface EvaluationMetricData {
  run_id: string;
  total_ground_truth_cases: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  true_negatives: number;
  precision: number;
  recall: number;
  f1_score: number;
  accuracy: number;
  match_rate: number;
  processing_time_sec: number;
  throughput_records_sec: number;
  confusion_matrix?: Record<string, any>;
}

export interface ChatResponse {
  answer: string;
  query_type: string;
  retrieved_records: any[];
  retrieved_exceptions: any[];
  retrieved_metrics: any;
}

export const api = {
  async runReconciliation(userPrompt: string, useSyntheticBatch = true) {
    const res = await fetch(`${API_BASE}/reconciliation/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_prompt: userPrompt,
        use_synthetic_batch: useSyntheticBatch
      })
    });
    if (!res.ok) throw new Error("Failed to run reconciliation");
    return res.json();
  },

  async getRunDetails(runId: string) {
    const res = await fetch(`${API_BASE}/reconciliation/${runId}`);
    if (!res.ok) throw new Error("Failed to fetch run details");
    return res.json();
  },

  async getMatches(runId: string, category?: string, search?: string) {
    let url = `${API_BASE}/reconciliation/${runId}/matches?limit=250`;
    if (category && category !== "ALL") url += `&category=${encodeURIComponent(category)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch matches");
    return res.json();
  },

  async getExceptions(runId: string, reason?: string, search?: string) {
    let url = `${API_BASE}/reconciliation/${runId}/exceptions?limit=200`;
    if (reason && reason !== "ALL") url += `&reason=${encodeURIComponent(reason)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch exceptions");
    return res.json();
  },

  async getMetrics(runId: string): Promise<EvaluationMetricData> {
    const res = await fetch(`${API_BASE}/reconciliation/${runId}/metrics`);
    if (!res.ok) throw new Error("Failed to fetch metrics");
    return res.json();
  },

  async askChat(question: string, runId?: string): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, run_id: runId })
    });
    if (!res.ok) throw new Error("Failed to send chat message");
    return res.json();
  },

  async getAllRuns() {
    const res = await fetch(`${API_BASE}/runs`);
    if (!res.ok) throw new Error("Failed to fetch runs");
    return res.json();
  },

  async generateSyntheticBatch() {
    const res = await fetch(`${API_BASE}/synthetic/generate`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to generate synthetic batch");
    return res.json();
  }
};
