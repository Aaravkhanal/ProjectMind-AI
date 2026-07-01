/**
 * ProjectMind client — reads .projectmind/ files directly (no backend needed)
 * and optionally calls the backend API for richer features.
 */

import * as fs from "fs";
import * as path from "path";
import * as https from "https";
import * as http from "http";
import * as vscode from "vscode";

export interface HealthScore {
  overall: number;
  architecture: number;
  security: number;
  maintainability: number;
  code_quality: number;
  breakdown: Record<string, number>;
  generated_at?: string;
}

export interface ComplexFunction {
  name: string;
  file: string;
  line: number;
  complexity: number;
}

export interface ImpactResult {
  file: string;
  impact_score: number;
  directly_affected: string[];
  transitively_affected: string[];
  centrality_score: number;
}

export class ProjectMindClient {
  private pmDir: string;
  private backendUrl: string;

  constructor(workspaceRoot: string) {
    this.pmDir = path.join(workspaceRoot, ".projectmind");
    this.backendUrl = vscode.workspace
      .getConfiguration("projectmind")
      .get("backendUrl", "http://localhost:8000");
  }

  get isInitialized(): boolean {
    return fs.existsSync(this.pmDir);
  }

  // ── Local file reads (no backend) ─────────────────────────────────────

  readHealthScore(): HealthScore | null {
    const p = path.join(this.pmDir, "health_score.json");
    if (!fs.existsSync(p)) return null;
    try {
      return JSON.parse(fs.readFileSync(p, "utf8")) as HealthScore;
    } catch {
      return null;
    }
  }

  readComplexFunctions(): ComplexFunction[] {
    const p = path.join(this.pmDir, "architecture_report.json");
    if (!fs.existsSync(p)) return [];
    try {
      const report = JSON.parse(fs.readFileSync(p, "utf8"));
      return (report.high_complexity_functions ?? []) as ComplexFunction[];
    } catch {
      return [];
    }
  }

  readSecurityIssues(): Array<{ file: string; line: number; severity: string; description: string }> {
    const p = path.join(this.pmDir, "architecture_report.json");
    if (!fs.existsSync(p)) return [];
    try {
      const report = JSON.parse(fs.readFileSync(p, "utf8"));
      return (report.security_issues ?? []) as Array<{ file: string; line: number; severity: string; description: string }>;
    } catch {
      return [];
    }
  }

  // ── Backend API calls (optional — needs `projectmind serve` running) ──

  async fetchImpact(filePath: string, workspaceRoot: string): Promise<ImpactResult | null> {
    const relPath = path.relative(workspaceRoot, filePath).replace(/\\/g, "/");
    try {
      const data = await this.get(
        `/graph/impact?project_path=${encodeURIComponent(workspaceRoot)}&file=${encodeURIComponent(relPath)}`
      );
      return data as ImpactResult;
    } catch {
      return null;
    }
  }

  async fetchTrace(errorText: string, workspaceRoot: string): Promise<unknown | null> {
    try {
      return await this.post("/tracer/trace", {
        project_path: workspaceRoot,
        error_text: errorText,
      });
    } catch {
      return null;
    }
  }

  async backendOnline(): Promise<boolean> {
    try {
      await this.get("/health");
      return true;
    } catch {
      return false;
    }
  }

  // ── Repository Brain (Phase 2) ────────────────────────────────────────

  async fetchBrainSummary(workspaceRoot: string): Promise<Record<string, unknown> | null> {
    try {
      return await this.get(`/brain/summary?project_path=${enc(workspaceRoot)}`) as Record<string, unknown>;
    } catch { return null; }
  }

  async fetchHotspots(workspaceRoot: string): Promise<Record<string, unknown>[]> {
    try {
      return await this.get(`/brain/hotspots?project_path=${enc(workspaceRoot)}&limit=10`) as Record<string, unknown>[];
    } catch { return []; }
  }

  async fetchDebt(workspaceRoot: string): Promise<Record<string, unknown>[]> {
    try {
      return await this.get(`/brain/debt?project_path=${enc(workspaceRoot)}&limit=30`) as Record<string, unknown>[];
    } catch { return []; }
  }

  // ── Git Intelligence (Phase 5) ────────────────────────────────────────

  async fetchGitIntelSummary(workspaceRoot: string): Promise<Record<string, unknown> | null> {
    try {
      return await this.get(`/git-intel/summary?project_path=${enc(workspaceRoot)}`) as Record<string, unknown>;
    } catch { return null; }
  }

  async fetchChurn(workspaceRoot: string): Promise<Record<string, unknown>[]> {
    try {
      return await this.get(`/git-intel/churn?project_path=${enc(workspaceRoot)}&limit=10`) as Record<string, unknown>[];
    } catch { return []; }
  }

  async scoreRisk(diff: string, workspaceRoot: string): Promise<Record<string, unknown> | null> {
    try {
      return await this.post("/git-intel/score-risk", { diff, project_path: workspaceRoot }) as Record<string, unknown>;
    } catch { return null; }
  }

  // ── Cost Engine (Phase 6) ─────────────────────────────────────────────

  async fetchCostSummary(workspaceRoot: string): Promise<Record<string, unknown> | null> {
    try {
      return await this.get(`/cost/summary?project_path=${enc(workspaceRoot)}`) as Record<string, unknown>;
    } catch { return null; }
  }

  async fetchCostAlerts(workspaceRoot: string): Promise<Record<string, unknown>[]> {
    try {
      return await this.get(`/cost/alerts?project_path=${enc(workspaceRoot)}`) as Record<string, unknown>[];
    } catch { return []; }
  }

  // ── Execution Plans (Phase 4) ─────────────────────────────────────────

  async fetchPlans(workspaceRoot: string): Promise<Record<string, unknown>[]> {
    try {
      return await this.get(`/plans?project_path=${enc(workspaceRoot)}&limit=15`) as Record<string, unknown>[];
    } catch { return []; }
  }

  async approvePlan(planId: number, approvedBy: string): Promise<Record<string, unknown> | null> {
    try {
      return await this.post(`/plans/${planId}/approve`, { approved_by: approvedBy }) as Record<string, unknown>;
    } catch { return null; }
  }

  // ── Multi-agent review (Phase 1+3) ────────────────────────────────────

  async runAgentReview(
    diff: string,
    workspaceRoot: string,
    opts: { llm_provider?: string; budget_per_task_usd?: number } = {}
  ): Promise<Record<string, unknown> | null> {
    try {
      return await this.post("/agents/review", {
        diff,
        project_path: workspaceRoot,
        llm_provider: opts.llm_provider ?? "nvidia",
        budget_per_task_usd: opts.budget_per_task_usd ?? 1.0,
      }) as Record<string, unknown>;
    } catch { return null; }
  }

  // ── Enriched prompt (Phase 1) ─────────────────────────────────────────

  async generatePrompt(task: string, workspaceRoot: string): Promise<string | null> {
    try {
      const res = await this.post("/prompt/generate", {
        task,
        project_path: workspaceRoot,
      }) as Record<string, unknown>;
      return (res.prompt ?? res.enriched_prompt ?? JSON.stringify(res)) as string;
    } catch { return null; }
  }

  // ── HTTP helpers & utilities ───────────────────────────────────────────

  private get(endpoint: string): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint, this.backendUrl);
      const mod = url.protocol === "https:" ? https : http;
      mod.get(url.toString(), { timeout: 5000 }, (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            resolve(JSON.parse(body));
          } else {
            reject(new Error(`HTTP ${res.statusCode}`));
          }
        });
      }).on("error", reject).on("timeout", () => reject(new Error("timeout")));
    });
  }

  private post(endpoint: string, body: unknown): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint, this.backendUrl);
      const payload = JSON.stringify(body);
      const mod = url.protocol === "https:" ? https : http;
      const req = mod.request(
        { ...url, method: "POST", headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) }, timeout: 10000 },
        (res) => {
          let data = "";
          res.on("data", (c) => (data += c));
          res.on("end", () => {
            if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
              resolve(JSON.parse(data));
            } else {
              reject(new Error(`HTTP ${res.statusCode}: ${data}`));
            }
          });
        }
      );
      req.on("error", reject);
      req.write(payload);
      req.end();
    });
  }
}

const enc = encodeURIComponent;
