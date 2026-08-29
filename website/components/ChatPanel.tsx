"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Sparkles, MessageSquare, Database, ShieldCheck, CornerDownLeft } from "lucide-react";
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
        "Hello! I am your AI Finance Controller Copilot. You can ask me specific questions about matched transactions, unresolved exceptions, amount discrepancies, or aggregate benchmark metrics.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sampleQuestions = [
    "Why wasn't TXN-LEDGER-1184 matched?",
    "What is the current match rate and accuracy?",
    "Show me all amount discrepancies and fees.",
    "Which source has the most exceptions?",
    "What is the total processing throughput?"
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

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
        content: "Sorry, I encountered an error connecting to the controller database. Please try again.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col h-[600px] overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-xs">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-900">
              Reconciliation QA Copilot
            </h3>
            <p className="text-[10px] text-slate-500 flex items-center space-x-1">
              <Database className="w-2.5 h-2.5 text-emerald-600" />
              <span>Grounded in active SQLite records & ground truth</span>
            </p>
          </div>
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 p-4 overflow-y-auto space-y-4">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex items-start space-x-2.5 ${
              m.role === "user" ? "flex-row-reverse space-x-reverse" : ""
            }`}
          >
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs ${
                m.role === "user"
                  ? "bg-slate-800 text-white"
                  : "bg-blue-100 text-blue-700"
              }`}
            >
              {m.role === "user" ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            </div>

            <div
              className={`max-w-[85%] rounded-xl p-3.5 text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-50 text-slate-800 border border-slate-200/80"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.content}</div>
              <div
                className={`text-[9px] mt-1 text-right ${
                  m.role === "user" ? "text-blue-200" : "text-slate-400"
                }`}
              >
                {m.timestamp}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-start space-x-2.5">
            <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center shrink-0">
              <Bot className="w-3.5 h-3.5 animate-pulse" />
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs text-slate-500 flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-blue-600 animate-ping"></span>
              <span>Retrieving records & synthesizing financial response...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested chips */}
      <div className="px-4 py-2 bg-slate-50/50 border-t border-slate-100 flex items-center space-x-1.5 overflow-x-auto text-[11px]">
        <Sparkles className="w-3 h-3 text-blue-500 shrink-0" />
        {sampleQuestions.slice(0, 3).map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            className="whitespace-nowrap text-slate-600 hover:text-blue-700 bg-white hover:bg-blue-50 px-2.5 py-1 rounded-full border border-slate-200 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input Form */}
      <div className="p-3 bg-white border-t border-slate-200">
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
            placeholder="Ask anything about matched records, discrepancies, or metrics..."
            className="flex-1 bg-slate-50 border border-slate-300 focus:border-blue-500 focus:bg-white rounded-lg px-3.5 py-2.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="bg-[#0066FF] hover:bg-blue-700 disabled:opacity-40 text-white p-2.5 rounded-lg shadow-xs transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
