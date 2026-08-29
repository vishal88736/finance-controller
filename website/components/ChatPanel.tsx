"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Sparkles, MessageSquare, Database, ShieldCheck, Copy, Check } from "lucide-react";
import { api, ChatResponse } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  retrieved_records?: any[];
  retrieved_exceptions?: any[];
  retrieved_metrics?: any;
}

interface ChatPanelProps {
  runId?: string;
  initialOpen?: boolean;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ runId }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hello! I am your **AI Finance Controller Copilot**.\n\nI have direct access to the live SQLite database and benchmark ground truth. You can ask me specific questions regarding:\n- Specific record lookups (e.g. *\"Why wasn't TXN-LEDGER-1184 matched?\"*)\n- Aggregate match rates, precision & accuracy\n- Payment gateway fee deductions\n- Duplicate ledger bookings & missing bank transactions",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sampleQuestions = [
    "Why wasn't TXN-LEDGER-1184 matched?",
    "What is the current match rate and accuracy?",
    "Show all amount discrepancies and processing fees.",
    "Which source has the most unresolved exceptions?",
    "What is our batch processing throughput?"
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
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        retrieved_records: response.retrieved_records,
        retrieved_exceptions: response.retrieved_exceptions,
        retrieved_metrics: response.retrieved_metrics
      };
      setMessages((prev) => [...prev, asstMsg]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: `err_${Date.now()}`,
        role: "assistant",
        content: "Sorry, I encountered an error connecting to the controller database. Please ensure the backend is running.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col h-[620px] overflow-hidden razorpay-card">
      {/* Header */}
      <div className="p-4 sm:p-5 border-b border-slate-200 bg-slate-50/80 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-blue-500 flex items-center justify-center text-white shadow-xs">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-xs font-extrabold text-slate-900 flex items-center space-x-2">
              <span>Financial QA Copilot</span>
              <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.2 rounded-full">
                SQLite Live
              </span>
            </h3>
            <p className="text-[11px] text-slate-500 flex items-center space-x-1">
              <Database className="w-3 h-3 text-emerald-600" />
              <span>Grounded in active reconciliation runs without numerical hallucination</span>
            </p>
          </div>
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 p-4 sm:p-5 overflow-y-auto space-y-4 bg-[#FAFCFF]">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex items-start space-x-3 group ${
              m.role === "user" ? "flex-row-reverse space-x-reverse" : ""
            }`}
          >
            <div
              className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-xs shadow-2xs font-bold ${
                m.role === "user"
                  ? "bg-[#0C2340] text-white"
                  : "bg-blue-100 text-blue-700 border border-blue-200"
              }`}
            >
              {m.role === "user" ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
            </div>

            <div
              className={`max-w-[85%] rounded-2xl p-4 text-xs leading-relaxed relative ${
                m.role === "user"
                  ? "bg-[#0066FF] text-white shadow-sm"
                  : "bg-white text-slate-800 border border-slate-200/90 shadow-2xs"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.content}</div>
              
              <div className="flex items-center justify-between pt-2 mt-1 border-t border-slate-100/50 text-[10px] opacity-70">
                <span>{m.timestamp}</span>
                {m.role === "assistant" && (
                  <button
                    type="button"
                    onClick={() => copyMessage(m.id, m.content)}
                    className="hover:text-blue-600 flex items-center space-x-1 transition-colors"
                  >
                    {copiedMsgId === m.id ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-600" />
                        <span className="text-emerald-600 font-bold">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-start space-x-3">
            <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center shrink-0 border border-blue-200">
              <Bot className="w-4 h-4 animate-pulse" />
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 text-xs text-slate-600 flex items-center space-x-2.5 shadow-2xs">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-600 animate-ping"></span>
              <span>Querying database records & computing exact answer...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompt Chips */}
      <div className="px-4 py-2.5 bg-slate-50/80 border-t border-slate-100 flex items-center space-x-2 overflow-x-auto text-[11px]">
        <span className="text-slate-400 font-bold text-[10px] uppercase tracking-wider shrink-0 flex items-center">
          <Sparkles className="w-3 h-3 text-blue-500 mr-1" /> Quick:
        </span>
        {sampleQuestions.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            className="whitespace-nowrap text-slate-700 hover:text-blue-700 font-medium bg-white hover:bg-blue-50/80 px-3 py-1 rounded-full border border-slate-200 transition-colors shadow-2xs"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Chat Input Form */}
      <div className="p-3.5 bg-white border-t border-slate-200">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center space-x-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about matched transactions, fees, discrepancies, or metrics..."
            className="flex-1 bg-slate-50 border border-slate-300 focus:border-blue-500 focus:bg-white rounded-xl px-4 py-3 text-xs text-slate-900 placeholder-slate-400 focus:outline-none transition-all shadow-inner"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="bg-[#0066FF] hover:bg-blue-700 disabled:opacity-40 text-white p-3 rounded-xl shadow-xs transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
