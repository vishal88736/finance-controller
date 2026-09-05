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
  statusText = "AI-assisted. Auditor-ready.",
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
      {/* Flat professional fintech mark: ledger lines + checkmark */}
      <div className={`${iconSizes[size]} bg-blue-600 flex items-center justify-center shrink-0`}>
        <svg
          className={svgSizes[size]}
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          {/* Ledger document */}
          <path
            d="M6 3.5h8L19 8.5v12H6V3.5Z"
            stroke="white"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path
            d="M13.5 3.5v5.5H19"
            stroke="white"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          {/* Ledger lines */}
          <path
            d="M9 13.2h3.4M9 16h2.2"
            stroke="white"
            strokeWidth="1.6"
            strokeLinecap="round"
            opacity="0.85"
          />
          {/* Reconciliation checkmark */}
          <path
            d="M9.2 18.6l2 2 3.8-4.2"
            stroke="white"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      {/* Brand text & tagline */}
      <div>
        <span className="font-bold text-white text-[15px] tracking-tight">
          LedgerPilot
        </span>

        {showStatus && (
          <div className="text-[10px] text-slate-400 font-medium mt-0.5">
            {statusText}
          </div>
        )}
      </div>
    </div>
  );
};
