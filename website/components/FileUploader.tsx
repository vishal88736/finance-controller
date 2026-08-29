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

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-xs space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-gray-900 uppercase tracking-wider">
            Uploaded Ingestion Sources ({files.length})
          </h3>
        </div>
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={onLoadSyntheticBatch}
            className="text-xs font-medium text-gray-700 hover:text-gray-900 bg-gray-100 hover:bg-gray-200/80 px-2.5 py-1 rounded transition-colors"
          >
            Reset 200+ Demo Batch
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center space-x-1 text-xs font-medium text-[#0C6CF2] hover:text-blue-700 bg-blue-50 hover:bg-blue-100 px-2.5 py-1 rounded transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Upload File</span>
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

      {/* Clean File Chips Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        {files.map((file) => (
          <div
            key={file.id}
            className="flex items-center justify-between bg-gray-50/80 border border-gray-200 px-3 py-2 rounded-md text-xs"
          >
            <div className="flex items-center space-x-2 truncate">
              {file.name.endsWith(".xlsx") || file.name.endsWith(".xls") ? (
                <FileSpreadsheet className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <FileText className="w-4 h-4 text-blue-600 shrink-0" />
              )}
              <div className="truncate">
                <div className="font-medium text-gray-800 truncate font-mono text-[11px]">{file.name}</div>
                <div className="text-[10px] text-gray-400 font-mono">{formatSize(file.size)}</div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemoveFile(file.id)}
              className="text-gray-400 hover:text-gray-600 p-1 ml-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
