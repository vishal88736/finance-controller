"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Copy, Check } from "lucide-react";
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
    <div className="bg-white border border-gray-200 rounded-lg shadow-xs flex flex-col h-[520px] overflow-hidden">
      {/* Header */}
      <div className="p-3.5 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold text-gray-900">Financial QA Copilot</span>
          <span className="text-[10px] text-gray-500 font-mono bg-gray-200/80 px-1.5 py-0.2 rounded">
            SQLite Live
          </span>
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 p-4 overflow-y-auto space-y-3 bg-gray-50/40">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg p-3 text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-[#0C6CF2] text-white"
                  : "bg-white text-gray-900 border border-gray-200 shadow-2xs"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.content}</div>

              <div className="flex items-center justify-between pt-1.5 mt-1 border-t border-gray-100 text-[10px] opacity-70">
                <span>{m.timestamp}</span>
                {m.role === "assistant" && (
                  <button
                    type="button"
                    onClick={() => copyMessage(m.id, m.content)}
                    className="hover:text-blue-600 flex items-center space-x-1"
                  >
                    {copiedMsgId === m.id ? (
                      <span className="text-emerald-600 font-medium">Copied</span>
                    ) : (
                      <span>Copy</span>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-center space-x-2 text-xs text-gray-500 bg-white border border-gray-200 p-2.5 rounded-lg w-fit">
            <span className="w-2 h-2 rounded-full bg-[#0C6CF2] animate-ping"></span>
            <span>Querying financial database...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompt Chips */}
      <div className="px-3 py-2 bg-gray-50 border-t border-gray-200 flex items-center space-x-1.5 overflow-x-auto text-[11px]">
        <span className="text-gray-400 font-medium text-[10px] uppercase shrink-0">Sample:</span>
        {sampleQuestions.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            className="whitespace-nowrap text-gray-600 hover:text-gray-900 bg-white hover:bg-gray-100 px-2 py-0.5 rounded border border-gray-200 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Chat Input */}
      <div className="p-2.5 bg-white border-t border-gray-200">
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
            placeholder="Ask about transactions, fee deductions, or benchmark accuracy..."
            className="flex-1 bg-gray-50 border border-gray-300 focus:border-blue-500 focus:bg-white rounded-md px-3 py-1.5 text-xs text-gray-900 placeholder-gray-400 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="bg-[#0C6CF2] hover:bg-blue-600 disabled:opacity-40 text-white px-3 py-1.5 rounded-md text-xs font-semibold"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
};
