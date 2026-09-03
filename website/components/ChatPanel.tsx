"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Send, Copy, Check, Sparkles, User, ShieldAlert, Wrench, Link2, RefreshCw, ExternalLink, ArrowUpRight } from "lucide-react";
import { api, MessageItem } from "@/lib/api";

interface ChatPanelProps {
  threadId: string;
  runId?: string | null;
  onOpenRecord?: (recordId: string) => void;
  onReconciled?: () => void;
}

// Evidence reference parsed from answers like `TXN-1023` — clickable
const ID_PATTERN = /\b([A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+)\b/;

interface EvidenceRef {
  id: string;
}

/* ── Rich markdown-ish renderer (bold, code, lists, headers) ── */
const FormattedMessage: React.FC<{ content: string; isUser: boolean; onOpenRecord?: (id: string) => void }> = ({
  content,
  isUser,
  onOpenRecord,
}) => {
  const renderInline = (text: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let keyIdx = 0;

    while (remaining.length > 0) {
      const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
      const codeMatch = remaining.match(/`(.+?)`/);

      let earliest: { index: number; length: number; type: "bold" | "code"; matchText: string } | null = null;

      if (boldMatch && boldMatch.index !== undefined) {
        earliest = { index: boldMatch.index, length: boldMatch[0].length, type: "bold", matchText: boldMatch[1] };
      }
      if (codeMatch && codeMatch.index !== undefined && (!earliest || codeMatch.index < earliest.index)) {
        earliest = { index: codeMatch.index, length: codeMatch[0].length, type: "code", matchText: codeMatch[1] };
      }

      if (!earliest) {
        // look for clickable record ids in the tail (local regex instance — safe for concurrency)
        const idMatch = remaining.match(new RegExp(ID_PATTERN.source));
        if (idMatch && onOpenRecord) {
          const id = idMatch[1];
          const idx = remaining.indexOf(idMatch[0]);
          if (idx > 0) parts.push(remaining.substring(0, idx));
          parts.push(
            <button
              key={`id_${keyIdx++}`}
              onClick={() => onOpenRecord(id)}
              className={`font-mono font-semibold underline decoration-dotted underline-offset-2 hover:text-blue-700 transition-colors cursor-pointer ${
                isUser ? "text-blue-100" : "text-blue-600"
              }`}
              title={`Open ${id}`}
            >
              {id}
            </button>
          );
          remaining = remaining.substring(idx + idMatch[0].length);
          continue;
        }
        parts.push(remaining);
        break;
      }

      if (earliest.index > 0) parts.push(remaining.substring(0, earliest.index));
      if (earliest.type === "bold") {
        const inner = renderInline(earliest.matchText);
        parts.push(
          <strong key={`b_${keyIdx++}`} className={isUser ? "font-bold text-white" : "font-semibold text-slate-900"}>
            {inner}
          </strong>
        );
      } else {
        parts.push(
          <code
            key={`c_${keyIdx++}`}
            className={`px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold ${
              isUser ? "bg-blue-700/80 text-blue-100" : "bg-slate-100 text-blue-700 border border-slate-200/80"
            }`}
          >
            {earliest.matchText}
          </code>
        );
      }
      remaining = remaining.substring(earliest.index + earliest.length);
    }
    return parts;
  };

  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: React.ReactNode[] = [];
  let inList = false;

  const flushList = (keySuffix: number | string) => {
    if (inList && currentList.length > 0) {
      elements.push(
        <ul key={`list_${keySuffix}`} className="my-2 space-y-1.5 pl-1">
          {currentList}
        </ul>
      );
      currentList = [];
      inList = false;
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList(idx);
      elements.push(<div key={`blank_${idx}`} className="h-1.5" />);
      return;
    }

    const headerMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (headerMatch) {
      flushList(idx);
      elements.push(
        <h4 key={`head_${idx}`} className={`font-bold mt-2.5 mb-1.5 ${headerMatch[1].length === 1 ? "text-base" : "text-sm"} ${isUser ? "text-white" : "text-slate-900"}`}>
          {renderInline(headerMatch[2])}
        </h4>
      );
      return;
    }

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ") || trimmed.startsWith("• ")) {
      inList = true;
      currentList.push(
        <li key={`li_${idx}`} className="flex items-start gap-2 text-xs leading-relaxed">
          <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${isUser ? "bg-blue-200" : "bg-blue-500"}`} />
          <span className="flex-1">{renderInline(trimmed.substring(2))}</span>
        </li>
      );
      return;
    }

    const moreMatch = trimmed.match(/^\.{2,3}\s*and\s+(\d+)\s+more/i);
    if (moreMatch) {
      flushList(idx);
      const count = moreMatch[1];
      elements.push(
        <div key={`more_${idx}`} className="pt-2 pb-1">
          <button
            type="button"
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent("navigation:jump-tab", { detail: { tab: "exceptions", category: "MATERIAL" } })
              );
            }}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 hover:text-blue-800 border border-blue-200/80 rounded-lg transition-all shadow-2xs cursor-pointer group"
          >
            <span>View {count} more in Exception Investigator</span>
            <ExternalLink className="w-3.5 h-3.5 text-blue-500 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>
      );
      return;
    }

    if (trimmed.includes("action:view_exceptions") || trimmed.toLowerCase().includes("view all exceptions")) {
      flushList(idx);
      elements.push(
        <div key={`action_view_${idx}`} className="pt-2 pb-1">
          <button
            type="button"
            onClick={() => {
              window.dispatchEvent(
                new CustomEvent("navigation:jump-tab", { detail: { tab: "exceptions", category: "MATERIAL" } })
              );
            }}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-all shadow-xs cursor-pointer group"
          >
            <span>Open Exception Investigator</span>
            <ArrowUpRight className="w-3.5 h-3.5 text-blue-200 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>
      );
      return;
    }

    flushList(idx);
    elements.push(
      <p key={`p_${idx}`} className="leading-relaxed">
        {renderInline(trimmed)}
      </p>
    );
  });

  flushList("end");
  return <div className="space-y-1">{elements}</div>;
};

export const ChatPanel: React.FC<ChatPanelProps> = ({ threadId, runId, onOpenRecord, onReconciled }) => {
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestionsState, setSuggestionsState] = useState<string>("NO_DOCUMENTS");
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastToolActivity, setLastToolActivity] = useState<string[] | null>(null);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [needsReconcileMsg, setNeedsReconcileMsg] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadHistory = useCallback(async () => {
    setMessagesError(null);
    try {
      const [history, sugg] = await Promise.all([
        api.getMessages(threadId),
        api.getSuggestions(threadId),
      ]);
      setMessages(history);
      setSuggestions(sugg.suggestions || []);
      setSuggestionsState(sugg.state);
    } catch (e: any) {
      setMessagesError(e?.message || "Could not load conversation.");
    }
  }, [threadId]);

  useEffect(() => {
    loadHistory();
  }, [threadId, loadHistory]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const copyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(id);
    setTimeout(() => setCopiedMsgId(null), 1500);
  };

  const handleSend = async (textToSend?: string) => {
    const question = (textToSend || input).trim();
    if (!question || isLoading) return;

    const tempUserMsg: MessageItem = {
      id: `temp_user_${Date.now()}`,
      role: "user",
      content: question,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setInput("");
    setIsLoading(true);
    setLastToolActivity(null);
    setNeedsReconcileMsg(false);

    try {
      const response = await api.sendMessage(threadId, question, runId || undefined);
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempUserMsg.id),
        response.user_message,
        response.assistant_message,
      ]);
      if (response.intent === "RECONCILIATION" && onReconciled) onReconciled();

      // Surface tool activity when present
      const meta = response.assistant_message?.metadata;
      if (meta?.tools_called?.length) {
        setLastToolActivity(meta.tools_called);
      }
      if (response.intent === "QA") {
        // refresh suggestions (thread state may have changed after reconciliation chat)
        api
          .getSuggestions(threadId)
          .then((s) => {
            setSuggestions(s.suggestions || []);
            setSuggestionsState(s.state);
          })
          .catch(() => undefined);
      }
    } catch (e: any) {
      const errorMsg: MessageItem = {
        id: `err_${Date.now()}`,
        role: "assistant",
        content:
          e?.message ||
          "I couldn't reach the reconciliation service. Please retry — I won't guess financial answers.",
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  // External "ask copilot" requests (e.g., from evidence links elsewhere in the app).
  // Latest-ref pattern keeps the listener stable while always invoking the
  // current closure of handleSend.
  const handleSendRef = useRef(handleSend);
  useEffect(() => {
    handleSendRef.current = handleSend;
  });
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.question) void handleSendRef.current(detail.question);
    };
    window.addEventListener("copilot:ask", handler as EventListener);
    return () => window.removeEventListener("copilot:ask", handler as EventListener);
  }, []);

  return (
    <div className="card flex flex-col h-[640px] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className="text-sm font-semibold text-slate-900">Financial Copilot</span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              <span className="text-[11px] text-slate-400 font-mono">Evidence-grounded · thread {threadId}</span>
            </div>
          </div>
        </div>
        <button
          onClick={loadHistory}
          className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          aria-label="Reload conversation"
          title="Reload conversation"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Message list */}
      <div className="flex-1 px-5 py-4 overflow-y-auto space-y-4 bg-slate-50/40">
        {messagesError && (
          <div className="mx-auto max-w-md bg-red-50 border border-red-200 text-red-800 rounded-xl px-4 py-3 text-xs text-center">
            <div className="font-semibold mb-1">Conversation unavailable</div>
            {messagesError}
            <button onClick={loadHistory} className="mt-2 block mx-auto text-red-700 underline font-medium cursor-pointer">
              Retry
            </button>
          </div>
        )}

        {!messagesError && messages.length === 0 && (
          <div className="text-center py-12 text-xs text-slate-400 space-y-2">
            <Sparkles className="w-8 h-8 mx-auto text-slate-200" />
            <div>Ask about this thread&apos;s transactions, exceptions, or reconciliation results.</div>
          </div>
        )}

        {messages.map((m) => {
          const isGuardrail = m.metadata?.intent === "OFF_TOPIC" || m.metadata?.answer_source === "refusal";
          return (
            <div key={m.id} className={`flex items-start gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""} animate-slide-up`}>
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                  m.role === "user" ? "bg-blue-600" : isGuardrail ? "bg-amber-500 text-white" : "bg-white border border-slate-200 shadow-xs"
                }`}
              >
                {m.role === "user" ? (
                  <User className="w-3.5 h-3.5 text-white" />
                ) : isGuardrail ? (
                  <ShieldAlert className="w-3.5 h-3.5 text-white" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                )}
              </div>

              <div className={`max-w-[82%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : isGuardrail
                    ? "bg-amber-50 border border-amber-200 text-amber-900"
                    : "bg-white text-slate-800 border border-slate-200 shadow-xs"
              }`}>
                <FormattedMessage content={m.content} isUser={m.role === "user"} onOpenRecord={onOpenRecord} />

                {m.role === "assistant" && (m.metadata?.tools_called?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-slate-100 text-[10px] text-slate-400 flex-wrap">
                    <Wrench className="w-3 h-3" />
                    {(m.metadata?.tools_called ?? []).map((t: string) => (
                      <code key={t} className="bg-slate-100 border border-slate-200 rounded px-1 py-0.5 font-mono">
                        {t.replace("_tool", "")}
                      </code>
                    ))}
                  </div>
                )}

                <div className={`flex items-center justify-between pt-2 mt-2 border-t text-[11px] ${
                  m.role === "user"
                    ? "border-blue-500/30 text-blue-200"
                    : isGuardrail
                      ? "border-amber-200 text-amber-700"
                      : "border-slate-100 text-slate-400"
                }`}>
                  <span>
                    {m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                    {m.role === "assistant" && m.metadata?.answer_source === "llm_validated" && (
                      <span className="ml-1.5" title="LLM answer validated against retrieved evidence">· verified</span>
                    )}
                  </span>
                  {m.role === "assistant" && (
                    <button
                      type="button"
                      onClick={() => copyMessage(m.id, m.content)}
                      className="hover:text-blue-600 flex items-center gap-1 cursor-pointer transition-colors"
                    >
                      {copiedMsgId === m.id ? (
                        <span className="text-emerald-600 flex items-center gap-0.5"><Check className="w-3 h-3" /> Copied</span>
                      ) : (
                        <span className="flex items-center gap-0.5"><Copy className="w-3 h-3" /> Copy</span>
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex items-start gap-2.5 animate-slide-up">
            <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 shadow-xs flex items-center justify-center shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-blue-600" />
            </div>
            <div className="bg-white border border-slate-200 px-4 py-3 rounded-xl shadow-xs">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: "0ms" }}></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: "150ms" }}></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: "300ms" }}></span>
                </div>
                <span>Querying this thread&apos;s financial evidence…</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested questions (backend-driven, guardrail-safe) */}
      <div className="px-4 py-2.5 bg-white border-t border-slate-100 flex items-center gap-2 overflow-x-auto">
        <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide shrink-0">Try:</span>
        {suggestions.length === 0 ? (
          <span className="text-[11px] text-slate-400 italic">
            {suggestionsState === "NO_DOCUMENTS"
              ? "Suggestions appear once you upload documents."
              : "Suggestions appear after reconciliation."}
          </span>
        ) : (
          suggestions.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(q)}
              disabled={isLoading}
              className="whitespace-nowrap disabled:opacity-50 text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 hover:border-slate-300 text-xs font-medium transition-all cursor-pointer"
            >
              {q}
            </button>
          ))
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-white border-t border-slate-100">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-3"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about transactions, exceptions, or reconciliation results…"
            className="flex-1 bg-slate-50 border border-slate-200 focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-500/10 rounded-xl px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none transition-all"
            aria-label="Ask a financial question"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="bg-gradient-to-b from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white px-4 py-2.5 rounded-xl text-sm font-semibold cursor-pointer transition-all shadow-sm active:scale-[0.98] flex items-center gap-1.5"
          >
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline">Send</span>
          </button>
        </form>
      </div>
    </div>
  );
};
