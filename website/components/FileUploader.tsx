"use client";

import React, { useRef, useState } from "react";
import { Upload, FileText, X, CheckCircle2, FileSpreadsheet, Sparkles } from "lucide-react";

export interface UploadedFileItem {
  id: string;
  name: string;
  size: number;
  type: string;
  rawFile?: File;
}

interface FileUploaderProps {
  files: UploadedFileItem[];
  onAddFiles: (files: UploadedFileItem[]) => void;
  onRemoveFile: (id: string) => void;
  onLoadSyntheticBatch: () => void;
}

export const FileUploader: React.FC<FileUploaderProps> = ({
  files,
  onAddFiles,
  onRemoveFile,
  onLoadSyntheticBatch
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const newItems: UploadedFileItem[] = [];
    for (let i = 0; i < fileList.length; i++) {
      const f = fileList[i];
      newItems.push({
        id: `file_${Date.now()}_${i}`,
        name: f.name,
        size: f.size,
        type: f.name.split(".").pop()?.toLowerCase() || "csv",
        rawFile: f
      });
    }
    onAddFiles(newItems);
  };

  const getFileIcon = (name: string) => {
    if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
      return <FileSpreadsheet className="w-4 h-4 text-emerald-600" />;
    }
    return <FileText className="w-4 h-4 text-blue-600" />;
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Document Ingestion</h3>
          <p className="text-xs text-slate-500">
            Upload any number of multi-source financial ledgers, bank statements, or settlement exports (CSV, XLSX, PDF).
          </p>
        </div>
        <button
          type="button"
          onClick={onLoadSyntheticBatch}
          className="inline-flex items-center space-x-1.5 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg border border-blue-200 transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5 text-blue-600" />
          <span>Load 200+ Demo Batch</span>
        </button>
      </div>

      {/* Drag and Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
          isDragging
            ? "border-blue-500 bg-blue-50/50"
            : "border-slate-300 hover:border-blue-400 bg-slate-50/50 hover:bg-slate-50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".csv,.xlsx,.xls,.json,.pdf"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="flex flex-col items-center justify-center space-y-2">
          <div className="w-10 h-10 rounded-full bg-blue-100/70 flex items-center justify-center text-blue-600">
            <Upload className="w-5 h-5" />
          </div>
          <div className="text-xs font-medium text-slate-700">
            <span className="text-blue-600 font-semibold underline">Click to upload</span> or drag and drop financial documents
          </div>
          <p className="text-[11px] text-slate-400">Supported formats: CSV, Excel (.xlsx), PDF, JSON</p>
        </div>
      </div>

      {/* File List Chip preview */}
      {files.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-700 flex items-center justify-between">
            <span>Ready for Processing ({files.length} documents)</span>
            <span className="text-emerald-600 text-[11px] font-medium flex items-center space-x-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Multi-source batch configured</span>
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {files.map((file) => (
              <div
                key={file.id}
                className="flex items-center justify-between bg-slate-50 border border-slate-200 px-3 py-2 rounded-lg text-xs"
              >
                <div className="flex items-center space-x-2 truncate">
                  {getFileIcon(file.name)}
                  <div className="truncate">
                    <div className="font-medium text-slate-800 truncate">{file.name}</div>
                    <div className="text-[10px] text-slate-400">{formatSize(file.size)}</div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveFile(file.id);
                  }}
                  className="text-slate-400 hover:text-slate-600 p-1 ml-1"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
