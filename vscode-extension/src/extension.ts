/**
 * ProjectMind VS Code Extension v0.3.0 — entry point.
 *
 * Registers:
 *   - Activity Bar sidebar with 4 tree views: Brain, Git Intel, Cost, Plans
 *   - Status bar: PM: 6.1/10
 *   - Inline decorations: complexity warnings + security annotations
 *   - 11 commands covering review, prompt gen, risk scoring, plan approval, env discovery
 */

import * as vscode from "vscode";
import { ProjectMindClient } from "./projectmindClient";
import { StatusBarProvider } from "./providers/statusBar";
import { DecorationsProvider } from "./providers/decorations";
import { showImpactPanel } from "./providers/impactPanel";
import { BrainView } from "./views/brainView";
import { GitIntelView } from "./views/gitIntelView";
import { CostView } from "./views/costView";
import { PlansView } from "./views/plansView";

let statusBar: StatusBarProvider | null = null;
let decorations: DecorationsProvider | null = null;

export function activate(context: vscode.ExtensionContext): void {
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceRoot) return;

  const client = new ProjectMindClient(workspaceRoot);

  if (!client.isInitialized) {
    vscode.window
      .showInformationMessage(
        "ProjectMind: No .projectmind/ found. Run `projectmind init` to enable features.",
        "Learn More"
      )
      .then((choice) => {
        if (choice === "Learn More") {
          vscode.env.openExternal(
            vscode.Uri.parse("https://github.com/Aaravkhanal/llm-reviewer")
          );
        }
      });
  }

  // ── Status bar ──────────────────────────────────────────────────────────
  statusBar = new StatusBarProvider();
  statusBar.activate(client);
  context.subscriptions.push(statusBar);

  // ── Inline decorations ───────────────────────────────────────────────────
  decorations = new DecorationsProvider();
  decorations.activate(client, workspaceRoot);
  context.subscriptions.push(decorations);

  // ── Sidebar tree views ───────────────────────────────────────────────────
  const brainView    = new BrainView(client, workspaceRoot);
  const gitIntelView = new GitIntelView(client, workspaceRoot);
  const costView     = new CostView(client, workspaceRoot);
  const plansView    = new PlansView(client, workspaceRoot);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("projectmind.brainView",    brainView),
    vscode.window.registerTreeDataProvider("projectmind.gitIntelView", gitIntelView),
    vscode.window.registerTreeDataProvider("projectmind.costView",     costView),
    vscode.window.registerTreeDataProvider("projectmind.plansView",    plansView),
  );

  // Load sidebar data lazily (backend may not be running yet)
  void loadViews(brainView, gitIntelView, costView, plansView);

  // ── File watcher — refresh on .projectmind/ changes ─────────────────────
  const watcher = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(workspaceRoot, ".projectmind/*.json")
  );
  watcher.onDidChange(() => {
    statusBar?.refresh();
    if (vscode.window.activeTextEditor) {
      decorations?.decorate(vscode.window.activeTextEditor);
    }
  });
  context.subscriptions.push(watcher);

  // ── Commands — existing ──────────────────────────────────────────────────

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.refresh", async () => {
      statusBar?.refresh();
      if (vscode.window.activeTextEditor) {
        decorations?.decorate(vscode.window.activeTextEditor);
      }
      await loadViews(brainView, gitIntelView, costView, plansView);
      vscode.window.showInformationMessage("ProjectMind: All views refreshed.");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "projectmind.showImpact",
      async (fileUri?: vscode.Uri) => {
        const uri = fileUri ?? vscode.window.activeTextEditor?.document.uri;
        if (!uri) {
          vscode.window.showWarningMessage("ProjectMind: No file selected.");
          return;
        }
        await showImpactPanel(uri, client, workspaceRoot);
      }
    )
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.openDashboard", () => {
      const dashboardUrl = vscode.workspace
        .getConfiguration("projectmind")
        .get<string>("dashboardUrl", "http://localhost:3000");
      vscode.env.openExternal(vscode.Uri.parse(dashboardUrl));
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.trace", async () => {
      const errorText = await vscode.window.showInputBox({
        title: "ProjectMind: Root Cause Tracer",
        prompt: "Paste the error message or stack trace",
        placeHolder: "AttributeError: 'NoneType' object has no attribute 'user_id'…",
        ignoreFocusOut: true,
      });
      if (!errorText) return;

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "ProjectMind: Tracing root cause…" },
        async () => {
          const result = await client.fetchTrace(errorText, workspaceRoot);
          if (!result) {
            vscode.window.showErrorMessage(
              "ProjectMind: Could not trace — is the backend running? Run `projectmind serve`."
            );
            return;
          }
          showTracePanel(result as TraceResult, context);
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.onboard", async () => {
      const role = await vscode.window.showInputBox({
        title: "ProjectMind: Generate Onboarding Guide",
        prompt: "What role is the new developer?",
        value: "new backend engineer",
      });
      if (!role) return;
      const backendUrl = vscode.workspace
        .getConfiguration("projectmind")
        .get<string>("backendUrl", "http://localhost:8000");
      const url = `${backendUrl}/onboard/generate?project_path=${encodeURIComponent(workspaceRoot)}&role=${encodeURIComponent(role)}`;
      vscode.env.openExternal(vscode.Uri.parse(url));
    })
  );

  // ── Commands — new (Phase 7) ─────────────────────────────────────────────

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.reviewDiff", async () => {
      const diff = await vscode.window.showInputBox({
        title: "ProjectMind: Multi-Agent Review",
        prompt: "Paste a unified diff (or leave empty to review active file changes)",
        placeHolder: "--- a/auth.py\n+++ b/auth.py\n@@…",
        ignoreFocusOut: true,
      });

      const cfg = vscode.workspace.getConfiguration("projectmind");
      const provider = cfg.get<string>("llmProvider", "nvidia");
      const budget   = cfg.get<number>("reviewBudgetUsd", 1.0);

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "ProjectMind: Running multi-agent review…", cancellable: false },
        async () => {
          const result = await client.runAgentReview(diff ?? "", workspaceRoot, {
            llm_provider: provider,
            budget_per_task_usd: budget,
          });
          if (!result) {
            vscode.window.showErrorMessage("ProjectMind: Review failed — is the backend running?");
            return;
          }
          showReviewPanel(result, context);
          await loadViews(brainView, gitIntelView, costView, plansView);
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.generatePrompt", async () => {
      const task = await vscode.window.showInputBox({
        title: "ProjectMind: Generate Agent Prompt",
        prompt: "Describe what the AI agent should do",
        placeHolder: "Refactor the authentication module to use JWT…",
        ignoreFocusOut: true,
      });
      if (!task) return;

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "ProjectMind: Generating enriched prompt…" },
        async () => {
          const prompt = await client.generatePrompt(task, workspaceRoot);
          if (!prompt) {
            vscode.window.showErrorMessage("ProjectMind: Could not generate prompt — is the backend running?");
            return;
          }
          showPromptPanel(task, prompt, context);
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.scorePrRisk", async () => {
      const diff = await vscode.window.showInputBox({
        title: "ProjectMind: Score PR Risk",
        prompt: "Paste a unified diff to score",
        placeHolder: "--- a/payments.py\n+++ b/payments.py\n@@…",
        ignoreFocusOut: true,
      });
      if (!diff) return;

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "ProjectMind: Scoring PR risk…" },
        async () => {
          const result = await client.scoreRisk(diff, workspaceRoot);
          if (!result) {
            vscode.window.showErrorMessage("ProjectMind: Could not score risk — is the backend running?");
            return;
          }
          const lvl  = String(result.risk_level ?? "unknown").toUpperCase();
          const risk = Number(result.overall_risk ?? 0).toFixed(1);
          vscode.window
            .showInformationMessage(
              `ProjectMind: PR Risk = ${risk}/10 [${lvl}]`,
              "Show Details"
            )
            .then((choice) => {
              if (choice === "Show Details") showRiskPanel(result, context);
            });
          void gitIntelView.load();
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.approvePlan", async () => {
      const plans = await client.fetchPlans(workspaceRoot);
      const pending = (plans as Record<string, unknown>[]).filter(
        (p) => p.status === "pending_approval"
      );
      if (pending.length === 0) {
        vscode.window.showInformationMessage("ProjectMind: No plans pending approval.");
        return;
      }
      const pick = await vscode.window.showQuickPick(
        pending.map((p) => ({ label: String(p.title), description: `#${p.id}`, id: Number(p.id) })),
        { title: "Select a plan to approve" }
      );
      if (!pick) return;
      const result = await client.approvePlan(pick.id, "vscode");
      if (result) {
        vscode.window.showInformationMessage(`ProjectMind: Plan "${pick.label}" approved.`);
        void plansView.load();
      } else {
        vscode.window.showErrorMessage("ProjectMind: Approval failed — check backend logs.");
      }
    })
  );

  // ── Phase 20: Discover Environment ──────────────────────────────────────────

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.discoverEnvironment", async () => {
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "ProjectMind: Scanning your AI environment…",
          cancellable: false,
        },
        async (progress) => {
          progress.report({ message: "Detecting IDEs, providers, local models, MCP servers…" });
          const backendUrl = vscode.workspace
            .getConfiguration("projectmind")
            .get<string>("backendUrl", "http://localhost:8000");
          try {
            const resp = await fetch(
              `${backendUrl}/discover/scan?project_path=${encodeURIComponent(workspaceRoot)}&force=true`
            );
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json() as Record<string, unknown>;
            showDiscoveryPanel(data, context);
          } catch {
            vscode.window.showErrorMessage(
              "ProjectMind: Discovery failed — is the backend running? Run `projectmind serve`."
            );
          }
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.importProviders", async () => {
      const backendUrl = vscode.workspace
        .getConfiguration("projectmind")
        .get<string>("backendUrl", "http://localhost:8000");
      try {
        const resp = await fetch(
          `${backendUrl}/discover/import?project_path=${encodeURIComponent(workspaceRoot)}`,
          { method: "POST" }
        );
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json() as { imported: string[]; skipped: string[] };
        const msg = data.imported.length
          ? `Imported: ${data.imported.join(", ")}`
          : "No new providers to import.";
        vscode.window.showInformationMessage(`ProjectMind: ${msg}`);
      } catch {
        vscode.window.showErrorMessage("ProjectMind: Import failed — is the backend running?");
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("projectmind.setBudget", async () => {
      const input = await vscode.window.showInputBox({
        title: "ProjectMind: Set Monthly Budget",
        prompt: "Monthly limit in USD (e.g. 10)",
        value: "10",
      });
      if (!input || isNaN(Number(input))) return;
      const limit = Number(input);
      const backendUrl = vscode.workspace
        .getConfiguration("projectmind")
        .get<string>("backendUrl", "http://localhost:8000");
      try {
        await fetch(`${backendUrl}/cost/budget`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_path: workspaceRoot, monthly_limit_usd: limit }),
        });
        vscode.window.showInformationMessage(`ProjectMind: Budget set to $${limit}/month.`);
        void costView.load();
      } catch {
        vscode.window.showErrorMessage("ProjectMind: Could not set budget — is the backend running?");
      }
    })
  );
}

export function deactivate(): void {
  statusBar?.dispose();
  decorations?.dispose();
}

// ── Helpers ──────────────────────────────────────────────────────────────────

async function loadViews(...views: Array<{ load(): Promise<void> }>): Promise<void> {
  await Promise.allSettled(views.map((v) => v.load()));
}

// ── Webview panels ────────────────────────────────────────────────────────────

interface TraceResult {
  error_summary?: string;
  affected_files?: string[];
  causes?: Array<{ rank: number; kind: string; confidence: number; description: string; detail: string; file?: string }>;
}

function showTracePanel(result: TraceResult, _ctx: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "projectmindTrace", "PM: Root Cause Trace", vscode.ViewColumn.Beside,
    { enableScripts: false }
  );
  const causes = (result.causes ?? [])
    .map((c) => `
    <div style="margin-bottom:12px;padding:8px 12px;border-left:3px solid ${confColor(c.confidence)}">
      <strong>#${c.rank} ${c.description}</strong>
      <div style="font-size:.85em;color:var(--vscode-descriptionForeground);margin-top:4px">${c.detail}</div>
      <div style="font-size:.8em;margin-top:2px">
        Confidence: <strong>${(c.confidence * 100).toFixed(0)}%</strong> &nbsp;|&nbsp; ${c.kind}
        ${c.file ? `&nbsp;|&nbsp; <code>${c.file}</code>` : ""}
      </div>
    </div>`)
    .join("");

  panel.webview.html = pmHtml(
    "Root Cause Trace",
    `<p><strong>Error:</strong> ${result.error_summary ?? "(unknown)"}</p>
     ${result.affected_files?.length ? `<p><strong>Affected:</strong> ${result.affected_files.slice(0, 5).map((f) => `<code>${f}</code>`).join(", ")}</p>` : ""}
     <h2>Probable Causes</h2>
     ${causes || "<p><em>No causes identified.</em></p>"}`
  );
}

function showReviewPanel(result: Record<string, unknown>, _ctx: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "projectmindReview", "PM: Multi-Agent Review", vscode.ViewColumn.Beside,
    { enableScripts: false }
  );
  const md = (s: unknown) => String(s ?? "").replace(/\n/g, "<br>");
  panel.webview.html = pmHtml(
    "Multi-Agent Review",
    `<h2>Architect</h2><div class="box">${md(result.architect_review)}</div>
     <h2>Security</h2><div class="box">${md(result.security_review)}</div>
     <h2>Quality</h2><div class="box">${md(result.quality_review)}</div>
     <h2>Final Verdict</h2><div class="box verdict">${md(result.final_review)}</div>
     <p style="font-size:.8em;color:var(--vscode-descriptionForeground)">
       Complexity: ${result.task_complexity ?? "—"} | Errors: ${(result.errors as unknown[])?.length ?? 0}
     </p>`
  );
}

function showPromptPanel(task: string, prompt: string, _ctx: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "projectmindPrompt", "PM: Agent Prompt", vscode.ViewColumn.Beside,
    { enableScripts: true }
  );
  panel.webview.html = pmHtml(
    "Enriched Agent Prompt",
    `<p><strong>Task:</strong> ${task}</p>
     <button onclick="navigator.clipboard.writeText(document.getElementById('prompt').innerText)" style="margin-bottom:8px;padding:4px 10px;cursor:pointer">Copy to clipboard</button>
     <pre id="prompt" style="white-space:pre-wrap;word-break:break-word;background:var(--vscode-textCodeBlock-background);padding:12px;border-radius:4px">${prompt}</pre>`
  );
}

function showRiskPanel(result: Record<string, unknown>, _ctx: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "projectmindRisk", "PM: PR Risk Score", vscode.ViewColumn.Beside,
    { enableScripts: false }
  );
  const breakdown = Object.entries(result.breakdown as Record<string, number> ?? {})
    .map(([k, v]) => `<tr><td>${k}</td><td>${v.toFixed(2)}</td></tr>`)
    .join("");
  panel.webview.html = pmHtml(
    "PR Risk Assessment",
    `<h2 style="color:${riskColor(result.risk_level as string)}">${String(result.risk_level ?? "").toUpperCase()} — ${Number(result.overall_risk ?? 0).toFixed(1)}/10</h2>
     <table style="border-collapse:collapse;width:100%">
       <tr><th style="text-align:left;padding:4px 8px">Factor</th><th style="text-align:left">Score</th></tr>
       ${breakdown}
     </table>
     ${result.recommendation ? `<h2>Recommendation</h2><p>${result.recommendation}</p>` : ""}`
  );
}

// ── Shared HTML wrapper ───────────────────────────────────────────────────────

function pmHtml(title: string, body: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family:var(--vscode-font-family); color:var(--vscode-foreground);
           background:var(--vscode-editor-background); padding:20px; line-height:1.5; }
    h1 { font-size:1.1em; border-bottom:1px solid var(--vscode-panel-border); padding-bottom:6px; }
    h2 { font-size:.95em; color:var(--vscode-descriptionForeground); margin-top:1.5em; }
    code { font-family:var(--vscode-editor-font-family); font-size:.9em;
           background:var(--vscode-textCodeBlock-background); padding:1px 4px; border-radius:3px; }
    .box { background:var(--vscode-input-background); padding:12px; border-radius:4px; font-size:.9em; margin-bottom:8px; }
    .verdict { border-left:3px solid var(--vscode-testing-iconPassed); }
    table td, table th { padding:4px 12px 4px 0; vertical-align:top; }
  </style>
</head>
<body>
  <h1>🧠 ${title}</h1>
  ${body}
</body>
</html>`;
}

function confColor(conf: number): string {
  if (conf >= 0.8) return "#f44336";
  if (conf >= 0.6) return "#ff9800";
  return "#888";
}

function riskColor(level: string): string {
  if (level === "critical") return "#f44336";
  if (level === "high") return "#ff9800";
  if (level === "medium") return "#ffeb3b";
  return "#4caf50";
}

function showDiscoveryPanel(data: Record<string, unknown>, _ctx: vscode.ExtensionContext): void {
  const panel = vscode.window.createWebviewPanel(
    "projectmindDiscovery", "PM: Environment Discovery", vscode.ViewColumn.Beside,
    { enableScripts: false }
  );

  const summary = data.summary as Record<string, unknown> ?? {};
  const profile = data.profile as Record<string, unknown> ?? {};
  const caps    = (profile.capabilities as Record<string, unknown>) ?? {};

  const providerList = (summary.providers as string[] ?? [])
    .map((p) => `<li>✓ ${p}</li>`).join("") || "<li><em>None detected</em></li>";

  const agentList = (summary.installed_agents as string[] ?? [])
    .map((a) => `<li>✓ ${a}</li>`).join("") || "<li><em>None detected</em></li>";

  const localList = (summary.local_servers as string[] ?? [])
    .map((s) => `<li>✓ ${s} (local — free)</li>`).join("") || "<li><em>No local servers running</em></li>";

  const mcpCount   = Number(summary.mcp_count ?? 0);
  const modelCount = Number(summary.model_count ?? 0);
  const editor     = String(summary.editor ?? "unknown");
  const defModel   = String(summary.default_model ?? "none");
  const duration   = Number(data.scan_duration_ms ?? 0).toFixed(0);

  const routingRows = [
    ["Architecture", caps.best_architecture],
    ["Coding",       caps.best_coding],
    ["Security",     caps.best_security],
    ["Review",       caps.best_review],
    ["Testing",      caps.best_testing],
    ["Documentation",caps.best_documentation],
    ["Bug Fix",      caps.best_bug_fix],
    ["Reasoning",    caps.best_reasoning],
    ["Fastest",      caps.fastest],
    ["Cheapest",     caps.cheapest],
  ].map(([task, model]) =>
    `<tr><td>${task}</td><td><code>${model ?? "—"}</code></td></tr>`
  ).join("");

  const errors = (summary.errors as string[] ?? []);
  const errHtml = errors.length
    ? `<h2>Warnings</h2><ul>${errors.map((e) => `<li style="color:var(--vscode-inputValidation-warningBorder)">${e}</li>`).join("")}</ul>`
    : "";

  panel.webview.html = pmHtml(
    "Environment Discovery",
    `<p style="color:var(--vscode-descriptionForeground);font-size:.85em">
       Scanned in ${duration}ms · ${modelCount} models · ${mcpCount} MCP servers · Editor: <strong>${editor}</strong>
     </p>

     <h2>Detected Providers</h2>
     <ul>${providerList}</ul>

     <h2>Installed AI Agents</h2>
     <ul>${agentList}</ul>

     <h2>Local Model Servers</h2>
     <ul>${localList}</ul>

     <h2>Intelligent Routing Table</h2>
     <p style="font-size:.8em;color:var(--vscode-descriptionForeground)">
       Default model: <code>${defModel}</code>
     </p>
     <table style="border-collapse:collapse;width:100%">
       <tr><th style="text-align:left;padding:4px 8px 4px 0">Task</th><th style="text-align:left">Model</th></tr>
       ${routingRows}
     </table>
     ${errHtml}`
  );
}
