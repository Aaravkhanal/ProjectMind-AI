"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Card, Badge } from "@/components/ui/Card";
import type { AgentReview } from "@/lib/types";

const DEFAULT_PROJECT = process.env.NEXT_PUBLIC_DEFAULT_PROJECT ?? "/app";

type Tab = "final" | "architect" | "security" | "quality";

const TAB_LABELS: Record<Tab, string> = {
  final:     "Unified Review",
  architect: "Architect",
  security:  "Security",
  quality:   "Quality",
};

function ReviewTab({ review }: { review: AgentReview }) {
  const [tab, setTab] = useState<Tab>("final");
  const content: Record<Tab, string> = {
    final:     review.final_review,
    architect: review.architect_review,
    security:  review.security_review,
    quality:   review.quality_review,
  };

  return (
    <div>
      <div className="flex gap-1 mb-4">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-xs rounded font-medium transition-colors ${
              tab === t
                ? "bg-[#0ea5e9]/20 text-[#0ea5e9] border border-[#0ea5e9]/40"
                : "text-[#8b949e] hover:text-[#e6edf3] border border-transparent"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>
      <div className="prose prose-invert prose-sm max-w-none">
        <pre className="whitespace-pre-wrap text-xs text-[#e6edf3] leading-relaxed font-sans bg-[#0f1117] p-4 rounded-lg border border-[#21262d] overflow-y-auto" style={{ maxHeight: "50vh" }}>
          {content[tab] || "No output from this agent."}
        </pre>
      </div>
      {review.errors.length > 0 && (
        <div className="mt-3 space-y-1">
          {review.errors.map((e, i) => (
            <p key={i} className="text-xs text-red-400">⚠ {e}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ReviewPage() {
  const [diff, setDiff] = useState("");
  const [projectPath, setProjectPath] = useState(DEFAULT_PROJECT);
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgentReview | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!diff.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.multiAgentReview({
        diff,
        project_path: projectPath || undefined,
        llm_provider: provider,
        api_key: apiKey || undefined,
        model: model || undefined,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Multi-Agent Review</h1>
        <p className="text-sm text-[#8b949e] mt-0.5">
          Three specialist agents review your diff in parallel, then synthesize a unified report.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* input */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Card title="Diff Input">
            <textarea
              value={diff}
              onChange={(e) => setDiff(e.target.value)}
              placeholder="Paste your git diff here…"
              rows={14}
              className="w-full bg-[#0f1117] text-xs font-mono text-[#e6edf3] border border-[#21262d] rounded p-3 resize-none focus:outline-none focus:border-[#0ea5e9] placeholder-[#8b949e]"
            />
          </Card>

          <Card title="Configuration">
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[#8b949e] block mb-1">Project Path (optional)</label>
                <input value={projectPath} onChange={(e) => setProjectPath(e.target.value)}
                  className="w-full bg-[#0f1117] text-xs text-[#e6edf3] border border-[#21262d] rounded px-3 py-1.5 focus:outline-none focus:border-[#0ea5e9]" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-[#8b949e] block mb-1">Provider</label>
                  <select value={provider} onChange={(e) => setProvider(e.target.value)}
                    className="w-full bg-[#0f1117] text-xs text-[#e6edf3] border border-[#21262d] rounded px-3 py-1.5 focus:outline-none focus:border-[#0ea5e9]">
                    {["openai", "nvidia", "anthropic", "ollama"].map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-[#8b949e] block mb-1">Model (optional)</label>
                  <input value={model} onChange={(e) => setModel(e.target.value)}
                    placeholder="gpt-4o-mini"
                    className="w-full bg-[#0f1117] text-xs text-[#e6edf3] border border-[#21262d] rounded px-3 py-1.5 focus:outline-none focus:border-[#0ea5e9] placeholder-[#8b949e]" />
                </div>
              </div>
              <div>
                <label className="text-xs text-[#8b949e] block mb-1">API Key (optional — uses server env if blank)</label>
                <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                  className="w-full bg-[#0f1117] text-xs text-[#e6edf3] border border-[#21262d] rounded px-3 py-1.5 focus:outline-none focus:border-[#0ea5e9]" />
              </div>
            </div>
          </Card>

          <button
            type="submit"
            disabled={loading || !diff.trim()}
            className="w-full py-2.5 rounded-lg bg-[#0ea5e9] hover:bg-[#0284c7] disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
          >
            {loading ? "Running 3 agents in parallel…" : "Run Multi-Agent Review"}
          </button>
        </form>

        {/* output */}
        <div className="space-y-4">
          {loading && (
            <Card>
              <div className="space-y-3 py-4">
                {["Architect Agent", "Security Agent", "Quality Agent"].map((a) => (
                  <div key={a} className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-[#0ea5e9] animate-pulse" />
                    <span className="text-sm text-[#8b949e]">{a} reviewing…</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {error && (
            <Card>
              <p className="text-sm text-red-400">{error}</p>
            </Card>
          )}

          {result && (
            <Card title="Review Results">
              <div className="flex gap-2 mb-4">
                <Badge variant="ok">3 agents ran</Badge>
                {result.errors.length > 0 && (
                  <Badge variant="error">{result.errors.length} error(s)</Badge>
                )}
                {result.posted_comment && <Badge variant="ok">Comment posted</Badge>}
              </div>
              <ReviewTab review={result} />
            </Card>
          )}

          {!loading && !result && !error && (
            <Card>
              <div className="py-8 text-center">
                <p className="text-[#8b949e] text-sm">Paste a diff and click Run to start.</p>
                <p className="text-[#8b949e] text-xs mt-2">
                  ArchitectAgent + SecurityAgent + QualityAgent will analyze in parallel (~10-30s).
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
