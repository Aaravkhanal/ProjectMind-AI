"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { HealthGauge } from "@/components/HealthGauge";
import { Card, StatRow, Badge } from "@/components/ui/Card";
import type { HealthScore } from "@/lib/types";

const DEFAULT_PROJECT = process.env.NEXT_PUBLIC_DEFAULT_PROJECT ?? "/app";

function useHealth(projectPath: string) {
  return useSWR(`health:${projectPath}`, () => api.healthScore(projectPath), {
    refreshInterval: 30_000,
  });
}

function useDNA(projectPath: string) {
  return useSWR(`dna:${projectPath}`, () => api.analyze(projectPath), {
    refreshInterval: 60_000,
  });
}

function IssueBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-[#8b949e]">{label}</span>
        <span className="font-mono text-[#e6edf3]">{value}</span>
      </div>
      <div className="h-1.5 rounded-full bg-[#21262d]">
        <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [projectPath, setProjectPath] = useState(DEFAULT_PROJECT);
  const [inputPath, setInputPath] = useState(DEFAULT_PROJECT);

  const { data: health, isLoading: healthLoading, error: healthErr } = useHealth(projectPath);
  const { data: dna, isLoading: dnaLoading } = useDNA(projectPath);

  const b = health?.breakdown;
  const maxIssue = b
    ? Math.max(
        b.security_errors + b.security_warnings,
        b.duplicate_functions,
        b.dead_functions + b.dead_classes,
        b.high_complexity_functions,
        1
      )
    : 1;

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-[#8b949e] mt-0.5">Project health, code intelligence, and memory at a glance.</p>
        </div>
        <form
          onSubmit={(e) => { e.preventDefault(); setProjectPath(inputPath); }}
          className="flex gap-2"
        >
          <input
            value={inputPath}
            onChange={(e) => setInputPath(e.target.value)}
            placeholder="Project path…"
            className="text-sm bg-[#161b22] border border-[#30363d] rounded px-3 py-1.5 text-[#e6edf3] placeholder-[#8b949e] focus:outline-none focus:border-[#0ea5e9] w-64"
          />
          <button
            type="submit"
            className="text-sm bg-[#0ea5e9] hover:bg-[#0284c7] text-white px-4 py-1.5 rounded font-medium transition-colors"
          >
            Load
          </button>
        </form>
      </div>

      {/* top row: gauges */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {healthLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="animate-pulse h-48">{null}</Card>
          ))
        ) : healthErr ? (
          <Card className="col-span-4">
            <p className="text-sm text-red-400">
              Could not load health score. Make sure the backend is running and
              <code className="ml-1 text-xs bg-[#21262d] px-1 py-0.5 rounded">
                projectmind analyze
              </code> has been run.
            </p>
          </Card>
        ) : health ? (
          <>
            <Card className="flex justify-center items-center py-4">
              <HealthGauge score={health.overall} label="Overall" />
            </Card>
            <Card className="flex justify-center items-center py-4">
              <HealthGauge score={health.architecture} label="Architecture" />
            </Card>
            <Card className="flex justify-center items-center py-4">
              <HealthGauge score={health.security} label="Security" />
            </Card>
            <Card className="flex justify-center items-center py-4">
              <HealthGauge score={health.maintainability} label="Maintainability" />
            </Card>
          </>
        ) : null}
      </div>

      {/* middle row: issues breakdown + DNA */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* issues */}
        <Card title="Issue Breakdown" className="lg:col-span-2">
          {b ? (
            <div className="space-y-3">
              <IssueBar label="Security issues" value={b.security_errors + b.security_warnings} max={maxIssue} color="#ef4444" />
              <IssueBar label="Dead code" value={b.dead_functions + b.dead_classes} max={maxIssue} color="#f59e0b" />
              <IssueBar label="Duplicate functions" value={b.duplicate_functions} max={maxIssue} color="#a78bfa" />
              <IssueBar label="High complexity" value={b.high_complexity_functions} max={maxIssue} color="#0ea5e9" />
              <IssueBar label="Circular deps" value={b.circular_dependencies} max={maxIssue} color="#34d399" />
              <div className="pt-2 grid grid-cols-3 gap-3 text-center">
                <div className="bg-[#0f1117] rounded p-2">
                  <p className="text-lg font-bold text-red-400">{b.security_errors}</p>
                  <p className="text-[10px] text-[#8b949e]">SEC ERRORS</p>
                </div>
                <div className="bg-[#0f1117] rounded p-2">
                  <p className="text-lg font-bold text-amber-400">{b.security_warnings}</p>
                  <p className="text-[10px] text-[#8b949e]">SEC WARNINGS</p>
                </div>
                <div className="bg-[#0f1117] rounded p-2">
                  <p className="text-lg font-bold text-[#0ea5e9]">{b.parse_errors}</p>
                  <p className="text-[10px] text-[#8b949e]">PARSE ERRORS</p>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-xs text-[#8b949e]">Run analysis to see breakdown.</p>
          )}
        </Card>

        {/* project DNA */}
        <Card title="Project DNA">
          {dnaLoading ? (
            <div className="space-y-2 animate-pulse">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-4 bg-[#21262d] rounded" />
              ))}
            </div>
          ) : dna ? (
            <div>
              <StatRow label="Language" value={dna.language} />
              <StatRow label="Architecture" value={dna.architecture_pattern} color="#0ea5e9" />
              <StatRow label="Database" value={dna.database ?? "none"} />
              <StatRow label="Auth" value={dna.auth_strategy ?? "none"} />
              <StatRow label="Tests" value={dna.has_tests ? `yes (${dna.test_framework})` : "none"} />
              <StatRow label="Source files" value={`${dna.source_files} / ${dna.total_files}`} />
              <div className="flex flex-wrap gap-1 mt-3">
                {dna.frameworks.map((f) => (
                  <Badge key={f}>{f}</Badge>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-[#8b949e]">Backend not reachable.</p>
          )}
        </Card>
      </div>

      {/* quick actions */}
      <Card title="Quick Actions">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "View Graph", href: "/graph", desc: "Explore dependencies" },
            { label: "Browse Memory", href: "/memory", desc: "Decisions & errors" },
            { label: "Run Review", href: "/review", desc: "Multi-agent PR review" },
            { label: "API Docs", href: "/api/docs", desc: "OpenAPI explorer" },
          ].map((a) => (
            <a
              key={a.href}
              href={a.href}
              className="flex flex-col gap-1 p-3 rounded-lg border border-[#30363d] bg-[#0f1117] hover:border-[#0ea5e9]/50 hover:bg-[#0ea5e9]/5 transition-all group"
            >
              <span className="text-sm font-medium text-[#e6edf3] group-hover:text-[#0ea5e9] transition-colors">
                {a.label}
              </span>
              <span className="text-xs text-[#8b949e]">{a.desc}</span>
            </a>
          ))}
        </div>
      </Card>
    </div>
  );
}
