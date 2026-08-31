"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Copy, Check, Sparkles, User } from "lucide-react";
import { api, ChatResponse } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

interface ChatPanelProps {
  runId?: string;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ runId }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Finance Operations Copilot ready. I have direct access to active reconciliation records, fee deductions, and benchmark logs in the database. Ask any question about transactions or discrepancies.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sampleQuestions = [
    "Why wasn't TXN-LEDGER-1184 matched?",
    "What is our overall accuracy vs ground truth?",
    "Show all payment processing fee deductions",
    "Which file had the most exceptions?"
  ];

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

    const userMsg: Message = {
      id: `msg_${Date.now()}`,
      role: "user",
      content: question,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const response: ChatResponse = await api.askChat(question, runId);
      const asstMsg: Message = {
        id: `asst_${Date.now()}`,
        role: "assistant",
        content: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setMessages((prev) => [...prev, asstMsg]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: `err_${Date.now()}`,
        role: "assistant",
        content: "Error querying database. Please ensure the backend is connected.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
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
              <span className="text-[11px] text-slate-400 font-[family-name:var(--font-geist-mono)]">SQLite Live</span>
            </div>
          </div>
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 px-5 py-4 overflow-y-auto space-y-4 bg-slate-50/40">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex items-start gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""} animate-slide-up`}
          >
            {/* Avatar */}
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
              m.role === "user"
                ? "bg-blue-600"
                : "bg-white border border-slate-200 shadow-xs"
            }`}>
              {m.role === "user" ? (
                <User className="w-3.5 h-3.5 text-white" />
              ) : (
                <Sparkles className="w-3.5 h-3.5 text-blue-600" />
              )}
            </div>

            {/* Message Bubble */}
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-white text-slate-800 border border-slate-200 shadow-xs"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.content}</div>

              <div className={`flex items-center justify-between pt-2 mt-2 border-t text-[11px] ${
                m.role === "user" ? "border-blue-500/30 text-blue-200" : "border-slate-100 text-slate-400"
              }`}>
                <span>{m.timestamp}</span>
                {m.role === "assistant" && (
                  <button
                    type="button"
                    onClick={() => copyMessage(m.id, m.content)}
                    className="hover:text-blue-600 flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    {copiedMsgId === m.id ? (
                      <span className="text-emerald-500 flex items-center gap-0.5">
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
        ))}

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
                <span>Querying financial database...</span>
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
