import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProjectMind AI",
  description: "The persistent memory layer for AI coding agents",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#0f1117] text-[#e6edf3]">
        <nav className="border-b border-[#30363d] bg-[#161b22] px-6 py-3 flex items-center gap-6">
          <span className="text-base font-semibold text-white tracking-tight">
            ◈ ProjectMind AI
          </span>
          <a href="/" className="text-sm text-[#8b949e] hover:text-white transition-colors">Dashboard</a>
          <a href="/graph" className="text-sm text-[#8b949e] hover:text-white transition-colors">Graph</a>
          <a href="/memory" className="text-sm text-[#8b949e] hover:text-white transition-colors">Memory</a>
          <a href="/review" className="text-sm text-[#8b949e] hover:text-white transition-colors">Review</a>
          <span className="ml-auto text-xs text-[#8b949e] font-mono">v0.2.0</span>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
