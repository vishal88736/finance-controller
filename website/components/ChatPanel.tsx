"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Copy, Check, Sparkles, User, ShieldAlert } from "lucide-react";
import { api, MessageItem } from "@/lib/api";

interface ChatPanelProps {
  threadId: string;
  runId?: string;
}

// ── Rich Markdown Renderer for Financial QA Messages ──
const FormattedMessage: React.FC<{ content: string; isUser: boolean }> = ({ content, isUser }) => {
  const parseInline = (text: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let keyIdx = 0;

    while (remaining.length > 0) {
      // 1. Bold: **text**
      const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
      // 2. Inline Code: `code`
      const codeMatch = remaining.match(/`(.+?)`/);
      // 3. Italic: *text* or _text_
      const italicMatch = remaining.match(/(?<!\*)\*([^*]+?)\*(?!\*)|(?<!_)_([^_]+?)_(?!_)/);

      let earliest: { index: number; length: number; type: "bold" | "code" | "italic"; matchText: string } | null = null;

      if (boldMatch && boldMatch.index !== undefined) {
        earliest = { index: boldMatch.index, length: boldMatch[0].length, type: "bold", matchText: boldMatch[1] };
      }
      if (codeMatch && codeMatch.index !== undefined && (!earliest || codeMatch.index < earliest.index)) {
        earliest = { index: codeMatch.index, length: codeMatch[0].length, type: "code", matchText: codeMatch[1] };
      }
      if (italicMatch && italicMatch.index !== undefined && (!earliest || italicMatch.index < earliest.index)) {
        earliest = {
          index: italicMatch.index,
          length: italicMatch[0].length,
          type: "italic",
          matchText: italicMatch[1] || italicMatch[2]
        };
      }

      if (!earliest) {
        parts.push(remaining);
        break;
      }

      if (earliest.index > 0) {
        parts.push(remaining.substring(0, earliest.index));
      }

      if (earliest.type === "bold") {
        parts.push(
          <strong
            key={`b_${keyIdx++}`}
            className={isUser ? "font-bold text-white" : "font-semibold text-slate-900"}
          >
            {earliest.matchText}
          </strong>
        );
      } else if (earliest.type === "code") {
        parts.push(
          <code
            key={`c_${keyIdx++}`}
            className={`px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold ${
              isUser
                ? "bg-blue-700/80 text-blue-100"
                : "bg-slate-100 text-blue-700 border border-slate-200/80"
            }`}
          >
            {earliest.matchText}
          </code>
        );
      } else if (earliest.type === "italic") {
        parts.push(
          <em
            key={`i_${keyIdx++}`}
            className={isUser ? "italic text-blue-100" : "italic text-slate-500"}
          >
            {earliest.matchText}
          </em>
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

    // Empty line
    if (!trimmed) {
      flushList(idx);
      elements.push(<div key={`blank_${idx}`} className="h-1.5" />);
      return;
    }

    // Header: ### or ## or #
    const headerMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (headerMatch) {
      flushList(idx);
      const level = headerMatch[1].length;
      const title = headerMatch[2];
      elements.push(
        <h4
          key={`head_${idx}`}
          className={`font-bold mt-2.5 mb-1.5 ${
            level === 1 ? "text-base" : "text-sm"
          } ${isUser ? "text-white" : "text-slate-900"}`}
        >
          {parseInline(title)}
        </h4>
      );
      return;
    }

    // Bullet line: starts with "- " or "* " or "• "
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ") || trimmed.startsWith("• ")) {
      inList = true;
      const bulletText = trimmed.substring(2);
      currentList.push(
        <li key={`li_${idx}`} className="flex items-start gap-2 text-xs leading-relaxed">
          <span
            className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${
              isUser ? "bg-blue-200" : "bg-blue-500"
            }`}
          />
          <span className="flex-1">{parseInline(bulletText)}</span>
        </li>
      );
      return;
    }

    // Regular paragraph line
    flushList(idx);
    elements.push(
      <p key={`p_${idx}`} className="leading-relaxed">
        {parseInline(trimmed)}
      </p>
    );
  });

  flushList("end");

  return <div className="space-y-1">{elements}</div>;
};

export const ChatPanel: React.FC<ChatPanelProps> = ({ threadId, runId }) => {
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Finance Operations Copilot ready for this thread. I query only verified reconciliation records, fee deductions, and benchmark metrics in the database. Ask any question about transactions, exceptions, or reconciliation accuracy."
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sampleQuestions = [
    "Why wasn't TXN-LEDGER-1184 matched?",
    "Show all payment gateway fee deductions",
    "What is our overall accuracy vs ground truth?",
    "Show me the most serious material exceptions",
    "Write me a poem"
  ];

  // Load thread messages on mount or threadId change
  useEffect(() => {
    async function loadHistory() {
      if (!threadId) return;
      const history = await api.getMessages(threadId);
      if (history.length > 0) {
        setMessages(history);
      } else {
        setMessages([
          {
            id: `welcome_${threadId}`,
            role: "assistant",
            content:
              "Finance Operations Copilot ready for this thread. I query only verified reconciliation records, fee deductions, and benchmark metrics in the database. Ask any question about transactions, exceptions, or reconciliation accuracy."
          }
        ]);
      }
    }
    loadHistory();
  }, [threadId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
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
      created_at: new Date().toISOString()
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await api.sendMessage(threadId, question, runId);
      if (response && response.assistant_message) {
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== tempUserMsg.id),
          response.user_message,
          response.assistant_message
        ]);
      }
    } catch (err: any) {
      const errorMsg: MessageItem = {
        id: `err_${Date.now()}`,
        role: "assistant",
        content: "I can help with reconciliation, settlement analysis, financial exceptions, and questions about the data in this thread.",
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="card flex flex-col h-[560px] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <span className="text-sm font-semibold text-slate-900">Financial QA Copilot</span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              <span className="text-[11px] text-slate-400 font-mono">Thread: {threadId}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 px-5 py-4 overflow-y-auto space-y-4 bg-slate-50/40">
        {messages.map((m) => {
          const isGuardrail = m.content.includes("I can help with reconciliation, settlement analysis");
          return (
            <div
              key={m.id}
              className={`flex items-start gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""} animate-slide-up`}
            >
              {/* Avatar */}
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                  m.role === "user"
                    ? "bg-blue-600"
                    : isGuardrail
                    ? "bg-amber-500 text-white"
                    : "bg-white border border-slate-200 shadow-xs"
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

              {/* Message Bubble */}
              <div
                className={`max-w-[82%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-blue-600 text-white"
                    : isGuardrail
                    ? "bg-amber-50 border border-amber-200 text-amber-900"
                    : "bg-white text-slate-800 border border-slate-200 shadow-xs"
                }`}
              >
                <FormattedMessage content={m.content} isUser={m.role === "user"} />

                <div
                  className={`flex items-center justify-between pt-2 mt-2 border-t text-[11px] ${
                    m.role === "user"
                      ? "border-blue-500/30 text-blue-200"
                      : isGuardrail
                      ? "border-amber-200 text-amber-700"
                      : "border-slate-100 text-slate-400"
                  }`}
                >
                  <span>
                    {m.created_at
                      ? new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                      : ""}
                  </span>
                  {m.role === "assistant" && (
                    <button
                      type="button"
                      onClick={() => copyMessage(m.id, m.content)}
                      className="hover:text-blue-600 flex items-center gap-1 cursor-pointer transition-colors"
                    >
                      {copiedMsgId === m.id ? (
                        <span className="text-emerald-600 flex items-center gap-0.5">
                          <Check className="w-3 h-3" /> Copied
                        </span>
                      ) : (
                        <span className="flex items-center gap-0.5">
                          <Copy className="w-3 h-3" /> Copy
                        </span>
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
                <span>Querying financial database & evidence...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompt Chips */}
      <div className="px-4 py-2.5 bg-white border-t border-slate-100 flex items-center gap-2 overflow-x-auto">
        <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide shrink-0">Prompts:</span>
        {sampleQuestions.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            className="whitespace-nowrap text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 hover:border-slate-300 text-xs font-medium transition-all cursor-pointer"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Chat Input */}
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
            placeholder="Ask about transactions, fee deductions, or benchmark accuracy..."
            className="flex-1 bg-slate-50 border border-slate-200 focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-500/10 rounded-xl px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none transition-all"
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
