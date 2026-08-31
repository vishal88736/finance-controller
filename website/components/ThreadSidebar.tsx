"use client";

import React, { useState } from "react";
import { Plus, MessageSquare, Trash2, Edit2, Check, X, Shield, Layers, FileText } from "lucide-react";
import { ThreadItem } from "@/lib/api";

interface ThreadSidebarProps {
  threads: ThreadItem[];
  activeThreadId: string;
  onSelectThread: (id: string) => void;
  onCreateThread: () => void;
  onDeleteThread: (id: string) => void;
  isOpen: boolean;
  onToggleOpen: () => void;
  documentCount?: number;
  onOpenDocumentPanel?: () => void;
}

export const ThreadSidebar: React.FC<ThreadSidebarProps> = ({
  threads,
  activeThreadId,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
  isOpen,
  onToggleOpen,
  documentCount = 0,
  onOpenDocumentPanel
}) => {
  return (
    <aside
      className={`fixed lg:static inset-y-0 left-0 z-40 w-72 bg-slate-900 text-slate-200 flex flex-col border-r border-slate-800 transition-transform duration-300 ${
        isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      }`}
    >
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center text-white font-bold text-xs shadow-md shadow-blue-500/20">
            FC
          </div>
          <div>
            <span className="font-bold text-white text-sm">Finance Controller</span>
            <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Deterministic Core</span>
            </div>
          </div>
        </div>
        <button
          onClick={onToggleOpen}
          className="lg:hidden text-slate-400 hover:text-white p-1 rounded-md"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* New Chat Button */}
      <div className="p-3">
        <button
          onClick={onCreateThread}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl transition-all shadow-sm shadow-blue-600/20 cursor-pointer active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          <span>New Thread</span>
        </button>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-2.5 py-1">
          Recent Threads
        </div>

        {threads.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-slate-500">
            No threads yet. Click &quot;New Thread&quot; to begin.
          </div>
        ) : (
          threads.map((t) => {
            const isActive = t.id === activeThreadId;
            return (
              <div
                key={t.id}
                onClick={() => onSelectThread(t.id)}
                className={`group flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium cursor-pointer transition-all ${
                  isActive
                    ? "bg-slate-800 text-white shadow-xs font-semibold"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`}
              >
                <div className="flex items-center gap-2.5 truncate">
                  <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-blue-400" : "text-slate-500"}`} />
                  <span className="truncate">{t.title}</span>
                </div>

                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (threads.length > 1) {
                        onDeleteThread(t.id);
                      }
                    }}
                    className="p-1 hover:text-red-400 rounded transition-colors"
                    title="Delete thread"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Info / Document Registry Button */}
      <div className="p-3 border-t border-slate-800/80 space-y-2">
        {onOpenDocumentPanel && (
          <button
            onClick={onOpenDocumentPanel}
            className="w-full flex items-center justify-between px-3 py-2 bg-slate-800/80 hover:bg-slate-800 rounded-xl text-xs text-slate-300 font-medium transition-all cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-blue-400" />
              <span>Document Registry</span>
            </div>
            <span className="bg-slate-700 text-slate-300 text-[10px] font-bold px-2 py-0.5 rounded-full">
              {documentCount}
            </span>
          </button>
        )}

        <div className="flex items-center gap-2 px-2 text-[11px] text-slate-500">
          <Shield className="w-3.5 h-3.5 text-slate-400" />
          <span>Strict Thread Isolation</span>
        </div>
      </div>
    </aside>
  );
};
