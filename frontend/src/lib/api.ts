import type { AgentReview, HealthScore, KnowledgeGraph, MemoryEntry, ProjectDNA } from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<{ status: string; version: string; uptime_seconds: number }>("/health"),

  analyze: (projectPath: string) =>
    get<ProjectDNA>(`/analyze?path=${encodeURIComponent(projectPath)}`),

  healthScore: (projectPath: string) =>
    get<HealthScore>(`/architecture/health?path=${encodeURIComponent(projectPath)}`),

  graph: (projectPath: string, filesOnly = true) =>
    get<KnowledgeGraph>(
      `/graph?path=${encodeURIComponent(projectPath)}&files_only=${filesOnly}`
    ),

  graphImpact: (projectPath: string, file: string) =>
    get<{ affected_files: string[]; depth: number }>(
      `/graph/impact?path=${encodeURIComponent(projectPath)}&file=${encodeURIComponent(file)}`
    ),

  graphCentral: (projectPath: string, topN = 10) =>
    get<{ files: Array<{ file: string; centrality_score: number }> }>(
      `/graph/central?path=${encodeURIComponent(projectPath)}&top_n=${topN}`
    ),

  memory: (projectPath: string) =>
    get<{ decisions: MemoryEntry[]; errors: MemoryEntry[]; patterns: MemoryEntry[] }>(
      `/memory?path=${encodeURIComponent(projectPath)}`
    ),

  compress: (projectPath: string) =>
    post<{ context_json: Record<string, unknown>; budget: { used: number; total_budget: number } }>(
      "/compress",
      { path: projectPath }
    ),

  multiAgentReview: (body: {
    diff: string;
    project_path?: string;
    llm_provider?: string;
    api_key?: string;
    model?: string;
  }) => post<AgentReview>("/review/multi-agent", body),
};
