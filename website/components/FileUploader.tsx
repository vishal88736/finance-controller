"use client";

import React, { useRef, useState } from "react";
import { Upload, FileText, X, FileSpreadsheet, Plus } from "lucide-react";

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

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isExcel = (name: string) => name.endsWith(".xlsx") || name.endsWith(".xls");

  return (
    <div
      className={`card p-5 space-y-4 transition-all ${
        isDragging ? "!border-blue-400 !bg-blue-50/50 ring-2 ring-blue-500/10" : ""
      }`}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <h3 className="text-sm font-semibold text-slate-900">
            Ingestion Sources
          </h3>
          <span className="pill bg-slate-100 text-slate-600 border border-slate-200 !text-[10px]">
            {files.length} files
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onLoadSyntheticBatch}
            className="text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition-all cursor-pointer"
          >
            Reset Demo Batch
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-all cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Upload</span>
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".csv,.xlsx,.xls,.json,.pdf"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      {/* File Chips Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {files.map((file) => (
          <div
            key={file.id}
            className="group flex items-center justify-between bg-slate-50 hover:bg-slate-100/80 border border-slate-200 hover:border-slate-300 px-3.5 py-2.5 rounded-xl text-sm transition-all"
          >
            <div className="flex items-center gap-2.5 truncate">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                isExcel(file.name) ? "bg-emerald-50" : "bg-blue-50"
              }`}>
                {isExcel(file.name) ? (
                  <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                ) : (
                  <FileText className="w-4 h-4 text-blue-600" />
                )}
              </div>
              <div className="truncate">
                <div className="font-medium text-slate-800 truncate text-xs font-[family-name:var(--font-geist-mono)]">
                  {file.name}
                </div>
                <div className="text-[11px] text-slate-400 font-[family-name:var(--font-geist-mono)]">
                  {formatSize(file.size)}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemoveFile(file.id)}
              className="text-slate-300 hover:text-red-500 p-1 ml-2 opacity-0 group-hover:opacity-100 transition-all cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
