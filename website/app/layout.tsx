import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AI Finance Controller — Reconciliation Platform",
  description: "AI-powered multi-source financial reconciliation with deterministic matching, benchmark evaluation, and natural-language QA copilot.",
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
