"use client";

import React, { useCallback, useRef, useState } from "react";
import {
  X, FileText, Upload, AlertTriangle, CheckCircle2, FileSpreadsheet,
  ShieldAlert, Copy, Check, Loader2, Ban, Database,
} from "lucide-react";
import { ThreadDocumentItem, UploadOutcome, api } from "@/lib/api";

// ── Upload stage reflecting the REAL backend pipeline ──
type UploadStage = "idle" | "uploading" | "server" | "done";
interface ActiveUpload {
  filename: string;
  size: number;
  stage: UploadStage;
  outcome?: UploadOutcome;
}

const STAGE_LABELS: Record<Exclude<UploadStage, "idle" | "done">, string> = {
  uploading: "Uploading & validating",
  server: "Parsing · normalizing · fingerprinting",
};

interface DocumentWorkspaceProps {
  isOpen: boolean;
  onClose: () => void;
  threadId: string;
  documents: ThreadDocumentItem[];
  onDocumentsChanged: () => void;
}

const formatSize = (bytes?: number) => {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const isExcel = (fn: string) => /\.(xlsx|xls)$/i.test(fn);

export const DocumentWorkspace: React.FC<DocumentWorkspaceProps> = ({
  isOpen,
  onClose,
  threadId,
  documents,
  onDocumentsChanged,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploads, setUploads] = useState<ActiveUpload[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<ThreadDocumentItem | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleEscape = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") {
      if (selectedDoc) setSelectedDoc(null);
      else onClose();
    }
  }, [onClose, selectedDoc]);

  React.useEffect(() => {
    if (!isOpen) return;
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, handleEscape]);

  const uploadFiles = async (fileList: File[]) => {
    if (fileList.length === 0 || busy) return;
    setError(null);
    setBusy(true);

    const active: ActiveUpload[] = fileList.map((f) => ({
      filename: f.name,
      size: f.size,
      stage: "uploading",
    }));
    setUploads(active);

    try {
      const res = await api.uploadDocuments(threadId, fileList);
      setUploads(
        active.map((u, i) => ({
          ...u,
          stage: "done" as const,
          outcome: res.results[i],
        }))
      );
      onDocumentsChanged();
    } catch (e: any) {
      setError(e?.message || "Upload failed");
      setUploads(active.map((u) => ({ ...u, stage: "done" as const })));
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const copyText = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1400);
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Document workspace"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-3xl w-full max-h-[88vh] flex flex-col overflow-hidden animate-scale-in">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900">Documents</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              SHA-256 exact &amp; dataset-fingerprint duplicate detection, scoped to this thread.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
            aria-label="Close documents"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Drag & drop zone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              handleFileDrop(e.dataTransfer.files);
            }}
            className={`rounded-2xl border-2 border-dashed transition-all px-6 py-8 text-center cursor-pointer ${
              isDragging
                ? "border-blue-500 bg-blue-50/60 ring-2 ring-blue-500/10"
                : "border-slate-200 hover:border-slate-300 bg-slate-50/50"
            }`}
            onClick={() => !busy && fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            aria-label="Upload documents: drag files here or click to browse"
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".csv,.xlsx,.xls,.json"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) handleFileBrowse(e.target.files);
              }}
            />
            <Upload className={`w-8 h-8 mx-auto ${isDragging ? "text-blue-500" : "text-slate-300"}`} />
            <div className="mt-3 text-sm font-semibold text-slate-700">
              {isDragging ? "Drop files to upload" : "Drag files here, or click to browse"}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              CSV, XLSX, JSON · up to 25 MB each · parsed and fingerprinted on upload
            </div>
          </div>

          {/* Upload progress (real backend states) */}
          {uploads.length > 0 && (
            <div className="space-y-2">
              {uploads.map((u, idx) => (
                <div key={idx} className="bg-white border border-slate-200 rounded-xl p-3.5 space-y-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      {u.stage === "done" ? (
                        u.outcome?.status === "SUCCESS" ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                        ) : u.outcome?.status?.startsWith("DUPLICATE") ? (
                          <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                        ) : (
                          <Ban className="w-4 h-4 text-red-500 shrink-0" />
                        )
                      ) : (
                        <Loader2 className="w-4 h-4 text-blue-500 animate-spin shrink-0" />
                      )}
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-slate-800 truncate">{u.filename}</div>
                        <div className="text-[11px] text-slate-400">{formatSize(u.size)}</div>
                      </div>
                    </div>
                    <div className="text-[11px] font-medium text-slate-500 shrink-0">
                      {u.stage === "uploading" && "Uploading…"}
                      {u.stage === "server" && STAGE_LABELS.server}
                      {u.stage === "done" &&
                        (u.outcome?.status === "SUCCESS"
                          ? "Processed"
                          : u.outcome?.status === "DUPLICATE_EXACT"
                            ? "Exact duplicate"
                            : u.outcome?.status === "DUPLICATE_LOGICAL"
                              ? "Same dataset, different file"
                              : "Rejected")}
                    </div>
                  </div>

                  {/* honest progress bar: indeterminate while working */}
                  {u.stage !== "done" && (
                    <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full w-1/3 bg-blue-500 rounded-full animate-[progressSlide_1.2s_ease-in-out_infinite]" />
                    </div>
                  )}

                  {u.stage === "done" && u.outcome && (
                    <div
                      className={`text-[11px] leading-relaxed rounded-lg px-3 py-2 ${
                        u.outcome.status === "SUCCESS"
                          ? "bg-emerald-50 text-emerald-800 border border-emerald-100"
                          : u.outcome.status === "DUPLICATE_EXACT"
                            ? "bg-amber-50 text-amber-800 border border-amber-100"
                            : u.outcome.status === "DUPLICATE_LOGICAL"
                              ? "bg-violet-50 text-violet-800 border border-violet-100"
                              : "bg-red-50 text-red-800 border border-red-100"
                      }`}
                    >
                      {u.outcome.message}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl p-3 text-xs flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Upload failed. </span>
                {error}
              </div>
            </div>
          )}

          {/* Registered documents */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
                Registered in this thread
              </h4>
              <span className="pill bg-slate-100 text-slate-600 border border-slate-200">
                {documents.length}
              </span>
            </div>

            {documents.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-xs border border-dashed border-slate-200 rounded-xl">
                <Database className="w-8 h-8 mx-auto text-slate-200 mb-2" />
                No documents in this thread yet. Upload a ledger and a bank
                statement to get started.
              </div>
            ) : (
              documents.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => setSelectedDoc(doc)}
                  className="w-full text-left bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-4 transition-all shadow-xs space-y-2.5 cursor-pointer group"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                          isExcel(doc.filename) ? "bg-emerald-50 text-emerald-600" : "bg-blue-50 text-blue-600"
                        }`}
                      >
                        {isExcel(doc.filename) ? (
                          <FileSpreadsheet className="w-4 h-4" />
                        ) : (
                          <FileText className="w-4 h-4" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className="font-semibold text-sm text-slate-900 truncate group-hover:text-blue-700 transition-colors">
                          {doc.filename}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono">
                          {doc.record_count} records · {doc.document_type} · {formatSize(doc.size_bytes)}
                        </div>
                      </div>
                    </div>
                    <span
                      className={`pill shrink-0 ${
                        doc.processing_status === "PROCESSED"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : doc.processing_status === "DUPLICATE"
                            ? "bg-amber-50 text-amber-700 border border-amber-200"
                            : "bg-slate-100 text-slate-600 border border-slate-200"
                      }`}
                    >
                      {doc.processing_status}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-slate-100 text-[11px] font-mono text-slate-500">
                    <div className="truncate">
                      <span className="text-slate-400 font-sans">SHA-256: </span>
                      <span className="text-slate-700">{(doc.sha256 || "").slice(0, 20)}…</span>
                    </div>
                    {doc.dataset_fingerprint && (
                      <div className="truncate">
                        <span className="text-slate-400 font-sans">Fingerprint: </span>
                        <span className="text-slate-700">{doc.dataset_fingerprint.slice(0, 16)}…</span>
                      </div>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>

      {/* Document detail drawer */}
      {selectedDoc && (
        <div
          className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-sm animate-fade-in"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedDoc(null);
          }}
        >
          <div className="bg-white w-full max-w-md h-full shadow-2xl flex flex-col animate-slide-in-right" role="dialog" aria-label={`Details for ${selectedDoc.filename}`}>
            <div className="px-5 py-4 border-b border-slate-100 flex items-start justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    isExcel(selectedDoc.filename) ? "bg-emerald-50 text-emerald-600" : "bg-blue-50 text-blue-600"
                  }`}
                >
                  {isExcel(selectedDoc.filename) ? (
                    <FileSpreadsheet className="w-5 h-5" />
                  ) : (
                    <FileText className="w-5 h-5" />
                  )}
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-slate-900 truncate">{selectedDoc.filename}</h3>
                  <div className="text-[11px] text-slate-400 font-mono">{selectedDoc.id}</div>
                </div>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label="Close document details"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {/* Document Information */}
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                  Document Information
                </h4>
                <dl className="space-y-2 text-xs">
                  {[
                    ["File type", selectedDoc.file_type.toUpperCase()],
                    ["Size", formatSize(selectedDoc.size_bytes)],
                    ["Detected type", selectedDoc.document_type],
                    ["Uploaded", selectedDoc.uploaded_at ? new Date(selectedDoc.uploaded_at).toLocaleString() : "—"],
                  ].map(([k, v]) => (
                    <div key={k as string} className="flex justify-between gap-3">
                      <dt className="text-slate-400">{k}</dt>
                      <dd className="text-slate-800 font-medium text-right">{v as any}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              {/* Processing Information */}
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                  Processing Information
                </h4>
                <div className="flex items-center gap-3">
                  <span
                    className={`pill ${
                      selectedDoc.processing_status === "PROCESSED"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : selectedDoc.processing_status === "DUPLICATE"
                          ? "bg-amber-50 text-amber-700 border border-amber-200"
                          : "bg-slate-100 text-slate-600 border border-slate-200"
                    }`}
                  >
                    {selectedDoc.processing_status}
                  </span>
                  <span className="text-xs text-slate-500">
                    {selectedDoc.record_count} records parsed &amp; normalized
                  </span>
                </div>
              </section>

              {/* Duplicate Detection */}
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                  Duplicate Detection
                </h4>
                {selectedDoc.duplicate ? (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-900 space-y-1">
                    <div className="flex items-center gap-2 font-bold">
                      <ShieldAlert className="w-4 h-4" /> Duplicate detected
                    </div>
                    <p>
                      This file was rejected at upload because it matches an existing document in the
                      thread (exact bytes or identical normalized dataset).
                    </p>
                  </div>
                ) : (
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3.5 text-xs text-emerald-900">
                    <div className="flex items-center gap-2 font-bold">
                      <CheckCircle2 className="w-4 h-4" /> Unique in this thread
                    </div>
                    <p className="mt-1">
                      No other document in this thread shares its SHA-256 hash or dataset fingerprint.
                    </p>
                  </div>
                )}
              </section>

              {/* Records & Fingerprint */}
              <section>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2.5">
                  Records &amp; Fingerprint
                </h4>
                <div className="space-y-3">
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                    <div className="text-[10px] uppercase font-semibold text-slate-400 mb-1">SHA-256 (exact bytes)</div>
                    <div className="flex items-center gap-2">
                      <code className="text-[11px] text-slate-700 break-all flex-1">{selectedDoc.sha256}</code>
                      <button
                        onClick={() => copyText("sha", selectedDoc.sha256)}
                        className="text-slate-400 hover:text-blue-600 shrink-0 cursor-pointer"
                        aria-label="Copy SHA-256"
                      >
                        {copied === "sha" ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>
                  {selectedDoc.dataset_fingerprint && (
                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                      <div className="text-[10px] uppercase font-semibold text-slate-400 mb-1">
                        Dataset fingerprint (normalized records)
                      </div>
                      <div className="flex items-center gap-2">
                        <code className="text-[11px] text-slate-700 break-all flex-1">{selectedDoc.dataset_fingerprint}</code>
                        <button
                          onClick={() => copyText("fp", selectedDoc.dataset_fingerprint || "")}
                          className="text-slate-400 hover:text-blue-600 shrink-0 cursor-pointer"
                          aria-label="Copy fingerprint"
                        >
                          {copied === "fp" ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                      <p className="text-[10px] text-slate-400 mt-1.5">
                        Catches identical datasets uploaded under different filenames or column headers.
                      </p>
                    </div>
                  )}
                </div>
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // Local helpers closing over state setters (kept after return for hoisting clarity)
  function handleFileDrop(files: FileList) {
    void uploadFiles(Array.from(files));
  }
  function handleFileBrowse(files: FileList) {
    void uploadFiles(Array.from(files));
  }
};
