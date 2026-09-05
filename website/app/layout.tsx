import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "LedgerPilot — Reconciliation Platform",
  description: "LedgerPilot: AI-assisted, auditor-ready multi-source financial reconciliation with deterministic matching, evaluation, and analysis copilot.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`} suppressHydrationWarning>
      <body
        className="min-h-full flex flex-col font-[family-name:var(--font-inter)]"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
