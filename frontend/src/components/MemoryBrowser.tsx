"use client";

import { useState } from "react";
import type { MemoryEntry } from "@/lib/types";
import { Badge } from "@/components/ui/Card";

interface Props {
  decisions: MemoryEntry[];
  errors: MemoryEntry[];
  patterns: MemoryEntry[];
}

type Tab = "decisions" | "errors" | "patterns";

const TAB_LABELS: Record<Tab, string> = {
  decisions: "Decisions",
  errors:    "Known Errors",
  patterns:  "Patterns",
};

export function MemoryBrowser({ decisions, errors, patterns }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("decisions");

  const items: Record<Tab, MemoryEntry[]> = { decisions, errors, patterns };
  const current = items[activeTab];

  return (
    <div className="flex flex-col h-full">
      {/* tabs */}
      <div className="flex gap-1 mb-4">
        {(Object.keys(TAB_LABELS) as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-xs rounded font-medium transition-colors ${
              activeTab === tab
                ? "bg-[#0ea5e9]/20 text-[#0ea5e9] border border-[#0ea5e9]/40"
                : "text-[#8b949e] hover:text-[#e6edf3] border border-transparent"
            }`}
          >
            {TAB_LABELS[tab]}
            <span className="ml-1.5 text-[10px] opacity-60">{items[tab].length}</span>
          </button>
        ))}
      </div>

      {/* list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {current.length === 0 ? (
          <p className="text-xs text-[#8b949e] text-center py-8">
            No {TAB_LABELS[activeTab].toLowerCase()} recorded yet.
          </p>
        ) : (
          current.map((entry) => (
            <div
              key={entry.id}
              className="p-3 rounded-md bg-[#0f1117] border border-[#21262d] hover:border-[#30363d] transition-colors"
            >
              <div className="flex items-start gap-2">
                <Badge variant={activeTab === "errors" ? "error" : activeTab === "decisions" ? "ok" : "default"}>
                  #{entry.id}
                </Badge>
                <p className="text-xs text-[#e6edf3] leading-relaxed">{entry.content}</p>
              </div>
              {entry.score !== undefined && (
                <p className="mt-1 text-[10px] text-[#8b949e]">relevance: {entry.score.toFixed(3)}</p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
