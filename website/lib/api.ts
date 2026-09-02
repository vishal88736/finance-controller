/**
 * API client for the AI Finance Controller.
 *
 * Every method throws on failure — the UI renders honest error/empty/loading
 * states. NO fabricated fallback data is ever returned.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (e) {
    throw new ApiError("Cannot reach the Finance Controller backend. Is it running on port 8000?", 0);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* no body */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export interface ThreadItem {
  id: string;
  title: string;
  document_count?: number;
  message_count?: number;
  latest_run_status?: { status: string; exceptions_count: number } | null;
  created_at?: string;
  updated_at?: string;
}

export interface ThreadDocumentItem {
  id: string;
  filename: string;
  file_type: string;
  record_count: number;
  document_type: string;
  processing_status: string;
  sha256: string;
  dataset_fingerprint?: string | null;
  size_bytes?: number;
  duplicate?: boolean;
  uploaded_at?: string;
}

export interface LatestRun {
  id: string;
  status: string;
  total_records: number;
  matched_count: number;
  exceptions_count: number;
  match_rate: number;
  evaluated: boolean;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  processing_time_sec: number;
  throughput_records_sec: number;
  created_at?: string;
}

export interface ThreadDetail {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  documents: ThreadDocumentItem[];
  latest_run: LatestRun | null;
}

export interface MessageItem {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata?: Record<string, any>;
  created_at?: string;
}

export interface ReconciliationRunSummary {
  run_id?: string;
  total_records: number;
  matched_count: number;
  exceptions_count: number;
  match_rate: number;
  evaluated: boolean;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  processing_time_sec: number;
  throughput_records_sec: number;
  [key: string]: any;
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
  evidence?: Record<string, any>;
  score_breakdown?: Record<string, number>;
}

export interface ExceptionItem {
  exception_id: string;
  record_id: string;
  source: string;
  amount?: number;
  entity?: string;
  date?: string;
  reason_code: string;
  discrepancy_category?: "NORMAL" | "MATERIAL";
  confidence: number;
  decision: string;
  explanation: string;
  amount_discrepancy: number;
  candidates?: any[];
  evidence?: Record<string, any>;
}

export interface MetricsData {
  run_id: string;
  evaluated: boolean;
  total_ground_truth_cases: number | null;
  true_positives: number | null;
  false_positives: number | null;
  false_negatives: number | null;
  true_negatives: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  accuracy: number | null;
  match_rate: number;
  total_records: number;
  matched_count: number;
  exceptions_count: number;
  processing_time_sec: number;
  throughput_records_sec: number;
  confusion_matrix?: Record<string, any>;
}

export interface AuditLogItem {
  id: string;
  run_id?: string | null;
  action: string;
  agent?: string;
  tool?: string;
  parameters?: Record<string, any>;
  result_summary?: string;
  details?: Record<string, any>;
  timestamp?: string;
}

export interface UploadOutcome {
  status: "SUCCESS" | "DUPLICATE_EXACT" | "DUPLICATE_LOGICAL" | "REJECTED";
  message: string;
  reason_code?: string;
  duplicate_type?: "EXACT_FILE" | "LOGICAL_DATASET" | null;
  document?: {
    id: string;
    filename: string;
    record_count: number;
    document_type: string;
    sha256?: string;
    dataset_fingerprint?: string;
    uploaded_at?: string;
  };
}

export interface SendMessageResponse {
  user_message: MessageItem;
  assistant_message: MessageItem;
  intent: string;
  answer_source?: string;
  retrieved_records?: any[];
  retrieved_exceptions?: any[];
  retrieved_metrics?: Record<string, any>;
}

export interface SuggestionsData {
  thread_id: string;
  state: "NO_DOCUMENTS" | "PENDING_RECONCILIATION" | "READY";
  suggestions: string[];
}

export interface LangsmithStatus {
  tracing_active: boolean;
  project: string;
  endpoint: string;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  llm_configured: boolean;
}

// ─────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────

export const api = {
  // ── System ──
  async health(): Promise<HealthStatus> {
    return request<HealthStatus>("/health");
  },

  async langsmithStatus(): Promise<LangsmithStatus> {
    return request<LangsmithStatus>("/observability/langsmith");
  },

  // ── Threads ──
  async listThreads(): Promise<ThreadItem[]> {
    return request<ThreadItem[]>("/threads");
  },

  async createThread(title = "New Financial Investigation"): Promise<ThreadItem> {
    return request<ThreadItem>("/threads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  },

  async getThread(threadId: string): Promise<ThreadDetail> {
    return request<ThreadDetail>(`/threads/${threadId}`);
  },

  async renameThread(threadId: string, title: string): Promise<{ id: string; title: string }> {
    return request(`/threads/${threadId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  },

  async deleteThread(threadId: string): Promise<boolean> {
    await request(`/threads/${threadId}`, { method: "DELETE" });
    return true;
  },

  // ── Messages / Chat ──
  async getMessages(threadId: string): Promise<MessageItem[]> {
    return request<MessageItem[]>(`/threads/${threadId}/messages`);
  },

  async sendMessage(threadId: string, content: string, runId?: string): Promise<SendMessageResponse> {
    return request<SendMessageResponse>(`/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, run_id: runId }),
    });
  },

  // ── Suggestions ──
  async getSuggestions(threadId: string): Promise<SuggestionsData> {
    return request<SuggestionsData>(`/threads/${threadId}/suggestions`);
  },

  // ── Documents & Duplicates ──
  async getDocuments(threadId: string): Promise<ThreadDocumentItem[]> {
    return request<ThreadDocumentItem[]>(`/threads/${threadId}/documents`);
  },

  async uploadDocuments(
    threadId: string,
    files: File[]
  ): Promise<{ uploaded_count: number; duplicate_count: number; rejected_count: number; results: UploadOutcome[] }> {
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    return request(`/threads/${threadId}/documents`, {
      method: "POST",
      body: formData,
    });
  },

  // ── Reconciliation (never fabricates: throws on failure) ──
  async reconcileThread(threadId: string, userPrompt?: string, documentIds?: string[]) {
    return request<{ status: string; run_id: string; summary: ReconciliationRunSummary; step_progress: string[]; document_ids?: string[] }>(
      `/threads/${threadId}/reconcile`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_prompt: userPrompt, document_ids: documentIds ?? null }),
      }
    );
  },

  // ── Results / Exceptions / Metrics / Audit ──
  async getResults(threadId: string, category?: string, search?: string, limit = 250) {
    let url = `/threads/${threadId}/results?limit=${limit}`;
    if (category && category !== "ALL") url += `&category=${encodeURIComponent(category)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    return request<{ total: number; matches: MatchItem[] }>(url);
  },

  async getExceptions(threadId: string, reason?: string, category?: string, search?: string, limit = 200) {
    let url = `/threads/${threadId}/exceptions?limit=${limit}`;
    if (reason && reason !== "ALL") url += `&reason=${encodeURIComponent(reason)}`;
    if (category && category !== "ALL") url += `&category=${encodeURIComponent(category)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    return request<{ total: number; exceptions: ExceptionItem[] }>(url);
  },

  async getMetrics(threadId: string): Promise<MetricsData> {
    return request<MetricsData>(`/threads/${threadId}/metrics`);
  },

  async getAuditTrail(threadId: string, limit = 100): Promise<AuditLogItem[]> {
    return request<AuditLogItem[]>(`/threads/${threadId}/audit?limit=${limit}`);
  },
};
