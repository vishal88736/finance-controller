"use client";

import React from "react";

interface BrandLogoProps {
  size?: "sm" | "md" | "lg";
  showStatus?: boolean;
  statusText?: string;
  showBadge?: boolean;
  badgeText?: string;
  className?: string;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({
  size = "md",
  showStatus = true,
  statusText = "Autonomous Agent Active",
  showBadge = true,
  badgeText = "AI",
  className = "",
}) => {
  const iconSizes = {
    sm: "w-7 h-7 rounded-lg",
    md: "w-9 h-9 rounded-xl",
    lg: "w-11 h-11 rounded-2xl",
  };

  const svgSizes = {
    sm: "w-4 h-4",
    md: "w-5 h-5",
    lg: "w-6 h-6",
  };

  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      {/* ── Outer glowing container ── */}
      <div className="relative group cursor-pointer">
        {/* Ambient background blur glow */}
        <div className="absolute -inset-0.5 bg-gradient-to-r from-blue-500 via-indigo-500 to-cyan-400 rounded-xl blur-[5px] opacity-60 group-hover:opacity-100 transition duration-500 group-hover:duration-200 animate-pulse" />

        {/* Dynamic gradient border wrapper */}
        <div
          className={`relative ${iconSizes[size]} p-[1px] bg-gradient-to-br from-cyan-400 via-blue-500 to-indigo-600 shadow-md shadow-blue-500/25 transition-transform duration-300 group-hover:scale-105`}
        >
          {/* Dark high-tech inner surface */}
          <div className="relative w-full h-full bg-slate-950/95 backdrop-blur-md rounded-[10px] flex items-center justify-center overflow-hidden">
            {/* Subtle background tech grid shimmer */}
            <div className="absolute inset-0 bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:8px_8px] opacity-25" />

            {/* Futuristic Controller Emblem SVG */}
            <svg
              className={`${svgSizes[size]} relative z-10 drop-shadow-[0_0_6px_rgba(56,189,248,0.6)]`}
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <defs>
                <linearGradient id="brand-grad-primary" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#38BDF8" />
                  <stop offset="60%" stopColor="#6366F1" />
                  <stop offset="100%" stopColor="#A855F7" />
                </linearGradient>
                <linearGradient id="brand-grad-accent" x1="100%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#60A5FA" />
                  <stop offset="100%" stopColor="#34D399" />
                </linearGradient>
                <radialGradient id="spark-glow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#38BDF8" stopOpacity="1" />
                  <stop offset="100%" stopColor="#38BDF8" stopOpacity="0" />
                </radialGradient>
              </defs>

              {/* Interlocking Ledger Balance Chevrons (Reconciliation Nodes) */}
              <path
                d="M 4 8.5 L 11 3.5 L 14 6 L 8.5 10 L 4 8.5 Z"
                fill="url(#brand-grad-primary)"
                opacity="0.95"
              />
              <path
                d="M 20 15.5 L 13 20.5 L 10 18 L 15.5 14 L 20 15.5 Z"
                fill="url(#brand-grad-accent)"
                opacity="0.95"
              />

              {/* Central Controller Nexus Diamond */}
              <path
                d="M 12 6.5 L 17.5 12 L 12 17.5 L 6.5 12 Z"
                stroke="url(#brand-grad-primary)"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="#020617"
                fillOpacity="0.75"
              />

              {/* Center AI Core Pulse */}
              <circle cx="12" cy="12" r="2.2" fill="#38BDF8" />
              <circle cx="12" cy="12" r="4" fill="url(#spark-glow)" opacity="0.6" />
            </svg>

            {/* Corner metallic gloss highlight */}
            <div className="absolute -top-3 -right-3 w-6 h-6 bg-white/20 blur-[3px] rounded-full pointer-events-none" />
          </div>
        </div>
      </div>

      {/* ── Brand text & operational status ── */}
      <div>
        <div className="flex items-center gap-1.5">
          <span className="font-extrabold text-white text-[13.5px] tracking-tight group-hover:text-cyan-100 transition-colors">
            Finance
          </span>
          <span className="font-semibold bg-gradient-to-r from-blue-200 via-indigo-200 to-slate-300 bg-clip-text text-transparent text-[13.5px] tracking-tight">
            Controller
          </span>
          {showBadge && (
            <span className="ml-0.5 text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-md bg-gradient-to-r from-blue-500/20 to-indigo-500/20 text-cyan-300 border border-cyan-400/30 tracking-wider shadow-[0_0_8px_rgba(56,189,248,0.2)]">
              {badgeText}
            </span>
          )}
        </div>

        {showStatus && (
          <div className="text-[10px] text-slate-400 font-medium flex items-center gap-1.5 mt-0.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500 ring-2 ring-emerald-500/20" />
            </span>
            <span className="text-slate-400/90 font-mono tracking-tight text-[9.5px]">
              {statusText}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
