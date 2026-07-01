"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { MemoryBrowser } from "@/components/MemoryBrowser";

const DEFAULT_PROJECT = process.env.NEXT_PUBLIC_DEFAULT_PROJECT ?? "/app";

export default function MemoryPage() {
  const [projectPath] = useState(DEFAULT_PROJECT);

  const { data, isLoading, error } = useSWR(
    `memory:${projectPath}`,
    () => api.memory(projectPath),
    { revalidateOnFocus: false }
  );

  const total = data
    ? data.decisions.length + data.errors.length + data.patterns.length
    : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Memory Browser</h1>
        <p className="text-sm text-[#8b949e] mt-0.5">
          {isLoading ? "Loading…" : `${total} memories stored for this project`}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Decisions", count: data?.decisions.length ?? 0, color: "#22c55e" },
          { label: "Known Errors", count: data?.errors.length ?? 0, color: "#ef4444" },
          { label: "Patterns", count: data?.patterns.length ?? 0, color: "#0ea5e9" },
        ].map((s) => (
          <Card key={s.label}>
            <p className="text-3xl font-bold" style={{ color: s.color }}>{s.count}</p>
            <p className="text-xs text-[#8b949e] mt-1">{s.label}</p>
          </Card>
        ))}
      </div>

      <Card className="h-[calc(100vh-320px)]">
        {isLoading ? (
          <div className="text-xs text-[#8b949e]">Loading memories…</div>
        ) : error ? (
          <div className="text-xs text-red-400">
            Could not load memory. Make sure the backend is running and
            <code className="ml-1 text-xs bg-[#21262d] px-1 py-0.5 rounded">projectmind init</code> has run.
          </div>
        ) : data ? (
          <MemoryBrowser
            decisions={data.decisions}
            errors={data.errors}
            patterns={data.patterns}
          />
        ) : null}
      </Card>
    </div>
  );
}
