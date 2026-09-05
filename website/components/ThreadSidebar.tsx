"use client";

import React, { useState } from "react";
import { Plus, Trash2, Check, X, Shield, FileText, MessageSquare, Pencil, Layers } from "lucide-react";
import { ThreadItem } from "@/lib/api";
import { BrandLogo } from "./BrandLogo";

interface ThreadSidebarProps {
  threads: ThreadItem[];
  activeThreadId: string | null;
  onSelectThread: (id: string) => void;
  onCreateThread: () => void;
  onDeleteThread: (id: string) => void;
  onRenameThread: (id: string, title: string) => void;
  isOpen: boolean;
  onToggleOpen: () => void;
  disabled?: boolean;
}

function groupLabel(dateStr?: string): string {
  if (!dateStr) return "EARLIER";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "EARLIER";
  const now = new Date();
  const day = 86400000;
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = d.getTime();
  if (t >= midnight) return "TODAY";
  if (t >= midnight - day) return "YESTERDAY";
  if (t >= midnight - 7 * day) return "PREVIOUS 7 DAYS";
  return "EARLIER";
}

export const ThreadSidebar: React.FC<ThreadSidebarProps> = ({
  threads,
  activeThreadId,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
  onRenameThread,
  isOpen,
  onToggleOpen,
  disabled = false,
}) => {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const startRename = (t: ThreadItem) => {
    setRenamingId(t.id);
    setRenameValue(t.title);
  };

  const commitRename = (id: string) => {
    const title = renameValue.trim();
    if (title) onRenameThread(id, title);
    setRenamingId(null);
  };

  // Group threads by activity date
  const groups: { label: string; threads: ThreadItem[] }[] = [];
  for (const t of threads) {
    const label = groupLabel(t.updated_at || t.created_at);
    const g = groups.find((x) => x.label === label);
    if (g) g.threads.push(t);
    else groups.push({ label, threads: [t] });
  }

  return (
    <aside
      className={`fixed lg:static inset-y-0 left-0 z-40 w-72 bg-slate-900 text-slate-200 flex flex-col border-r border-slate-800 transition-transform duration-300 ${
        isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      }`}
      aria-label="Threads"
    >
      {/* Brand */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <BrandLogo />
        <button
          onClick={onToggleOpen}
          className="lg:hidden text-slate-400 hover:text-white p-1 rounded-md"
          aria-label="Close sidebar"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* New Analysis */}
      <div className="p-3">
        <button
          onClick={onCreateThread}
          disabled={disabled}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-xs px-4 py-2.5 rounded-xl transition-all shadow-sm shadow-blue-600/20 cursor-pointer active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          <span>New Analysis</span>
        </button>
      </div>

      {/* Thread list grouped by date */}
      <div className="flex-1 overflow-y-auto px-3 pb-2 space-y-4" role="list">
        {threads.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-slate-500">
            No threads yet. Click &quot;New Analysis&quot; to begin.
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="space-y-1">
              <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider px-2.5 py-1">
                {group.label}
              </div>
              {group.threads.map((t) => {
                const isActive = t.id === activeThreadId;
                const isRenaming = renamingId === t.id;
                const runStatus = t.latest_run_status?.status;
                const excCount = t.latest_run_status?.exceptions_count;
                return (
                  <div
                    key={t.id}
                    role="listitem"
                    onClick={() => !isRenaming && onSelectThread(t.id)}
                    onKeyDown={(e) => {
                      if (!isRenaming && (e.key === "Enter" || e.key === " ")) {
                        e.preventDefault();
                        onSelectThread(t.id);
                      }
                    }}
                    tabIndex={0}
                    className={`group px-3 py-2.5 rounded-xl transition-all outline-none ${
                      isActive
                        ? "bg-slate-800 shadow-xs"
                        : "hover:bg-slate-800/60 cursor-pointer"
                    }`}
                  >
                    {isRenaming ? (
                      <div className="flex items-center gap-1.5">
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") commitRename(t.id);
                            if (e.key === "Escape") setRenamingId(null);
                          }}
                          className="flex-1 bg-slate-950 border border-blue-500 rounded-lg px-2 py-1 text-xs text-white focus:outline-none min-w-0"
                          aria-label="Rename thread"
                        />
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            commitRename(t.id);
                          }}
                          className="p-1 text-emerald-400 hover:text-emerald-300"
                          aria-label="Save name"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenamingId(null);
                          }}
                          className="p-1 text-slate-400 hover:text-white"
                          aria-label="Cancel rename"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <MessageSquare
                              className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-blue-400" : "text-slate-500"}`}
                            />
                            <span
                              className={`truncate text-xs ${
                                isActive ? "text-white font-semibold" : "text-slate-300 font-medium"
                              }`}
                            >
                              {t.title}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 mt-1.5 pl-6 text-[10px] text-slate-500">
                            {typeof t.document_count === "number" && (
                              <span className="inline-flex items-center gap-1">
                                <FileText className="w-3 h-3" />
                                {t.document_count} doc{t.document_count === 1 ? "" : "s"}
                              </span>
                            )}
                            {runStatus && (
                              <span
                                className={`inline-flex items-center gap-1 font-medium ${
                                  runStatus === "COMPLETED"
                                    ? excCount && excCount > 0
                                      ? "text-amber-400"
                                      : "text-emerald-400"
                                    : "text-blue-400"
                                }`}
                              >
                                <Layers className="w-3 h-3" />
                                {runStatus === "COMPLETED"
                                  ? excCount && excCount > 0
                                    ? `${excCount} exception${excCount === 1 ? "" : "s"}`
                                    : "Completed"
                                  : runStatus.toLowerCase()}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-0.5 shrink-0 transition-opacity opacity-100 lg:opacity-0 lg:group-hover:opacity-100 lg:focus-within:opacity-100">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              startRename(t);
                            }}
                            className="p-1 text-slate-400 hover:text-blue-300 rounded transition-colors"
                            title="Rename thread"
                            aria-label={`Rename ${t.title}`}
                          >
                            <Pencil className="w-3 h-3" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteThread(t.id);
                            }}
                            className="p-1 text-slate-400 hover:text-red-400 rounded transition-colors"
                            title="Delete thread"
                            aria-label={`Delete ${t.title}`}
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-slate-800/80">
        <div className="flex items-center gap-2 px-2 text-[11px] text-slate-500">
          <Shield className="w-3.5 h-3.5 text-slate-400" />
          <span>Strict thread isolation enforced</span>
        </div>
      </div>
    </aside>
  );
};
