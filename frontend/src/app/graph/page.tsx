"use client";

import { useState } from "react";
import useSWR from "swr";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { Card, Badge } from "@/components/ui/Card";
import type { GraphNode } from "@/lib/types";

// Force-graph uses canvas — must be client-only
const KnowledgeGraph = dynamic(
  () => import("@/components/KnowledgeGraph").then((m) => m.KnowledgeGraph),
  { ssr: false, loading: () => <div className="w-full h-full flex items-center justify-center text-[#8b949e] text-sm">Loading graph…</div> }
);

const DEFAULT_PROJECT = process.env.NEXT_PUBLIC_DEFAULT_PROJECT ?? "/app";

export default function GraphPage() {
  const [projectPath] = useState(DEFAULT_PROJECT);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [impactFile, setImpactFile] = useState<string | null>(null);

  const { data: graph, isLoading } = useSWR(
    `graph:${projectPath}`,
    () => api.graph(projectPath, true),
    { revalidateOnFocus: false }
  );

  const { data: central } = useSWR(
    `central:${projectPath}`,
    () => api.graphCentral(projectPath, 8),
    { revalidateOnFocus: false }
  );

  const { data: impact } = useSWR(
    impactFile ? `impact:${projectPath}:${impactFile}` : null,
    () => api.graphImpact(projectPath, impactFile!),
    { revalidateOnFocus: false }
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Knowledge Graph</h1>
          <p className="text-sm text-[#8b949e] mt-0.5">
            {graph ? `${graph.nodes.length} nodes · ${graph.edges.length} edges` : "File dependency graph"}
          </p>
        </div>
        <div className="flex gap-2 text-xs text-[#8b949e]">
          {[["#0ea5e9", "file"], ["#a78bfa", "function"], ["#34d399", "class"]].map(([c, l]) => (
            <span key={l} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full inline-block" style={{ background: c }} />
              {l}
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4" style={{ height: "calc(100vh - 220px)" }}>
        {/* graph canvas */}
        <div className="lg:col-span-3 rounded-lg border border-[#30363d] overflow-hidden bg-[#0f1117]" style={{ minHeight: 400 }}>
          {isLoading ? (
            <div className="w-full h-full flex items-center justify-center text-[#8b949e] text-sm">
              Building graph…
            </div>
          ) : graph ? (
            <KnowledgeGraph
              nodes={graph.nodes}
              edges={graph.edges}
              onNodeClick={(n) => {
                setSelected(n);
                if (n.kind === "file") setImpactFile(n.id);
              }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-[#8b949e] text-sm">
              Run <code className="mx-1 text-xs bg-[#21262d] px-1.5 py-0.5 rounded">projectmind graph build</code> first.
            </div>
          )}
        </div>

        {/* right panel */}
        <div className="space-y-4 overflow-y-auto">
          {/* selected node */}
          {selected && (
            <Card title="Selected Node">
              <div className="space-y-2">
                <p className="text-xs font-mono text-[#e6edf3] break-all">{selected.name}</p>
                <Badge variant={selected.kind === "file" ? "ok" : "default"}>{selected.kind}</Badge>
                {selected.loc && <p className="text-xs text-[#8b949e]">{selected.loc} lines</p>}
                {selected.centrality !== undefined && (
                  <p className="text-xs text-[#8b949e]">centrality: {selected.centrality.toFixed(4)}</p>
                )}
              </div>
            </Card>
          )}

          {/* impact */}
          {impact && (
            <Card title={`Impact (${impact.affected_files.length} files)`}>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {impact.affected_files.length === 0 ? (
                  <p className="text-xs text-green-400">No dependents — safe to change.</p>
                ) : (
                  impact.affected_files.slice(0, 20).map((f) => (
                    <p key={f} className="text-[10px] font-mono text-[#8b949e] hover:text-[#e6edf3] cursor-pointer truncate"
                      onClick={() => setImpactFile(f)}>
                      → {f}
                    </p>
                  ))
                )}
              </div>
            </Card>
          )}

          {/* most central */}
          <Card title="Most Critical Files">
            <div className="space-y-1">
              {central?.files.map((f, i) => (
                <div key={f.file}
                  className="flex items-center gap-2 cursor-pointer hover:bg-[#0f1117] px-1 py-1 rounded"
                  onClick={() => { setImpactFile(f.file); setSelected({ id: f.file, kind: "file", name: f.file, centrality: f.centrality_score }); }}
                >
                  <span className="text-[10px] text-[#8b949e] w-4">{i + 1}.</span>
                  <span className="text-[10px] font-mono text-[#e6edf3] truncate flex-1">{f.file.split("/").slice(-2).join("/")}</span>
                  <span className="text-[10px] text-[#0ea5e9] shrink-0">{f.centrality_score.toFixed(3)}</span>
                </div>
              )) ?? <p className="text-xs text-[#8b949e]">Run graph build first.</p>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
