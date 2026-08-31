"use client";

import React, { useState, useRef } from "react";
import { X, FileText, Upload, AlertTriangle, CheckCircle2, Copy, Check, FileSpreadsheet, ShieldAlert } from "lucide-react";
import { ThreadDocumentItem, UploadOutcome } from "@/lib/api";

interface DocumentDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  documents: ThreadDocumentItem[];
  onUploadFiles: (files: File[]) => Promise<{ uploaded_count: number; results: UploadOutcome[] }>;
  onLoadSyntheticBatch: () => void;
}

export const DocumentDrawer: React.FC<DocumentDrawerProps> = ({
  isOpen,
  onClose,
  documents,
  onUploadFiles,
  onLoadSyntheticBatch
}) => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState<UploadOutcome[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const fileList = Array.from(e.target.files);
    setIsUploading(true);
    try {
      const outcome = await onUploadFiles(fileList);
      setUploadFeedback(outcome.results);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const isExcel = (fn: string) => fn.endsWith(".xlsx") || fn.endsWith(".xls");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-scale-in">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900">Thread Document Registry</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Cryptographic SHA-256 validation & Level 2 canonical duplicate detection.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Action Bar */}
        <div className="px-6 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".csv,.xlsx,.xls,.json,.pdf"
            className="hidden"
            onChange={handleFileChange}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-3.5 py-2 rounded-lg transition-all cursor-pointer shadow-xs disabled:opacity-50"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{isUploading ? "Processing..." : "Upload New File"}</span>
            </button>
            <button
              onClick={onLoadSyntheticBatch}
              className="text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 px-3.5 py-2 rounded-lg transition-all cursor-pointer shadow-xs"
            >
              Reset 200+ Demo Batch
            </button>
          </div>
          <span className="text-xs font-medium text-slate-400">
            {documents.length} document(s) registered
          </span>
        </div>

        {/* Upload Alerts & Feedback */}
        {uploadFeedback && uploadFeedback.length > 0 && (
          <div className="p-4 space-y-2 bg-slate-50/80 border-b border-slate-100 max-h-48 overflow-y-auto">
            {uploadFeedback.map((fb, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-xl text-xs flex items-start gap-2.5 ${
                  fb.status === "DUPLICATE_EXACT"
                    ? "bg-amber-50 border border-amber-200 text-amber-900"
                    : fb.status === "DUPLICATE_LOGICAL"
                    ? "bg-purple-50 border border-purple-200 text-purple-900"
                    : fb.status === "SUCCESS"
                    ? "bg-emerald-50 border border-emerald-200 text-emerald-900"
                    : "bg-red-50 border border-red-200 text-red-900"
                }`}
              >
                {fb.status === "DUPLICATE_EXACT" && <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />}
                {fb.status === "DUPLICATE_LOGICAL" && <AlertTriangle className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />}
                {fb.status === "SUCCESS" && <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />}
                <div>
                  <div className="font-bold">
                    {fb.status === "DUPLICATE_EXACT" && "Level 1: Exact File Duplicate Detected"}
                    {fb.status === "DUPLICATE_LOGICAL" && "Level 2: Logical Dataset Duplicate Detected"}
                    {fb.status === "SUCCESS" && "Document Ingested & Verified"}
                  </div>
                  <div className="mt-0.5 text-[11px] leading-relaxed">{fb.message}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Document List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {documents.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-xs">
              No documents in this thread. Upload CSV or Excel files above.
            </div>
          ) : (
            documents.map((doc) => (
              <div
                key={doc.id}
                className="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-4 transition-all shadow-xs space-y-2.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                      isExcel(doc.filename) ? "bg-emerald-50 text-emerald-600" : "bg-blue-50 text-blue-600"
                    }`}>
                      {isExcel(doc.filename) ? <FileSpreadsheet className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                    </div>
                    <div>
                      <div className="font-semibold text-sm text-slate-900">{doc.filename}</div>
                      <div className="text-[11px] text-slate-400 font-mono">
                        {doc.record_count} records · Type: {doc.document_type}
                      </div>
                    </div>
                  </div>
                  <span className="pill bg-emerald-50 text-emerald-700 border border-emerald-200">
                    {doc.processing_status}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-slate-100 text-[11px] font-mono text-slate-500">
                  <div className="truncate">
                    <span className="text-slate-400 font-sans">SHA-256: </span>
                    <span className="text-slate-700">{doc.sha256}</span>
                  </div>
                  {doc.dataset_fingerprint && (
                    <div className="truncate">
                      <span className="text-slate-400 font-sans">Fingerprint: </span>
                      <span className="text-slate-700">{doc.dataset_fingerprint.slice(0, 16)}...</span>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
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
    </div>
  );
};
