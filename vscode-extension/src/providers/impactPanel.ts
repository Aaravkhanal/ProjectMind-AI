/**
 * Impact Panel — webview that shows the blast radius of a file.
 *
 * "Right-click a file → ProjectMind: Show Impact"
 *
 * If the backend is running, fetches live graph data.
 * If not, shows cached health + complexity data from .projectmind/.
 */

import * as vscode from "vscode";
import * as path from "path";
import { ProjectMindClient } from "../projectmindClient";

export async function showImpactPanel(
  fileUri: vscode.Uri,
  client: ProjectMindClient,
  workspaceRoot: string
): Promise<void> {
  const filePath = fileUri.fsPath;
  const relPath = path.relative(workspaceRoot, filePath).replace(/\\/g, "/");

  const panel = vscode.window.createWebviewPanel(
    "projectmindImpact",
    `PM Impact: ${path.basename(filePath)}`,
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  panel.webview.html = buildLoadingHtml(relPath);

  const online = await client.backendOnline();
  let impactData: unknown = null;

  if (online) {
    impactData = await client.fetchImpact(filePath, workspaceRoot);
  }

  const health = client.readHealthScore();
  const complexFns = client.readComplexFunctions().filter((fn) => {
    const f = fn.file.replace(/\\/g, "/");
    return f === relPath || f.endsWith("/" + relPath) || relPath.endsWith("/" + f);
  });
  const secIssues = client.readSecurityIssues().filter((i) => {
    const f = i.file.replace(/\\/g, "/");
    return f === relPath || f.endsWith("/" + relPath) || relPath.endsWith("/" + f);
  });

  panel.webview.html = buildImpactHtml(relPath, impactData, health, complexFns, secIssues, online);
}

function buildLoadingHtml(file: string): string {
  return `<!DOCTYPE html><html><body style="font-family:sans-serif;padding:20px">
    <h2>ProjectMind — Analyzing ${file}…</h2>
    <p>Fetching impact data…</p>
  </body></html>`;
}

function buildImpactHtml(
  file: string,
  impact: unknown,
  health: { overall?: number; security?: number } | null,
  complexFns: Array<{ name: string; line: number; complexity: number }>,
  secIssues: Array<{ line: number; severity: string; description: string }>,
  backendOnline: boolean
): string {
  const i = impact as {
    impact_score?: number;
    centrality_score?: number;
    directly_affected?: string[];
    transitively_affected?: string[];
  } | null;

  const impactScore = i?.impact_score ?? "?";
  const centrality  = i?.centrality_score ?? "?";
  const direct      = i?.directly_affected ?? [];
  const transitive  = i?.transitively_affected ?? [];

  const scoreColor = (s: number | string) =>
    typeof s === "number" ? (s >= 7.5 ? "#4caf50" : s >= 5 ? "#ff9800" : "#f44336") : "#888";

  const listItems = (arr: string[]) =>
    arr.length ? arr.map((f) => `<li><code>${f}</code></li>`).join("") : "<li><em>none</em></li>";

  const complexHtml = complexFns.length
    ? complexFns
        .map(
          (fn) =>
            `<tr><td><code>${fn.name}</code></td><td>line ${fn.line}</td>
             <td style="color:#ff9800;font-weight:bold">${fn.complexity}</td></tr>`
        )
        .join("")
    : `<tr><td colspan="3"><em>No high-complexity functions</em></td></tr>`;

  const secHtml = secIssues.length
    ? secIssues
        .map(
          (s) =>
            `<tr><td style="color:#f44336">${s.severity?.toUpperCase()}</td>
             <td>line ${s.line}</td><td>${s.description?.slice(0, 80)}</td></tr>`
        )
        .join("")
    : `<tr><td colspan="3"><em>No security issues found</em></td></tr>`;

  const backendNote = backendOnline
    ? `<span style="color:#4caf50">● backend online</span>`
    : `<span style="color:#888">● backend offline — showing cached data. Run <code>projectmind serve</code> for live graph data.</span>`;

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground);
           background: var(--vscode-editor-background); padding: 20px; margin: 0; }
    h1 { font-size: 1.1em; margin-bottom: 4px; }
    h2 { font-size: 0.95em; color: var(--vscode-descriptionForeground); margin-top: 1.5em; }
    .badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
             font-weight: bold; font-size: 1.2em; color: white; margin-right: 8px; }
    table { border-collapse: collapse; width: 100%; margin-top: 8px; }
    td, th { padding: 4px 8px; text-align: left; border-bottom: 1px solid var(--vscode-widget-border); }
    th { font-size: 0.85em; color: var(--vscode-descriptionForeground); }
    ul { margin: 4px 0; padding-left: 1.2em; }
    li { font-size: 0.9em; }
    code { font-family: var(--vscode-editor-font-family); font-size: 0.9em;
           background: var(--vscode-textCodeBlock-background); padding: 1px 4px; border-radius: 3px; }
    .status { font-size: 0.8em; margin-bottom: 16px; }
  </style>
</head>
<body>
  <h1>📍 ${file}</h1>
  <div class="status">${backendNote}</div>

  <h2>Impact</h2>
  <span class="badge" style="background:${scoreColor(typeof impactScore === 'number' ? impactScore : 5)}">
    ${typeof impactScore === 'number' ? impactScore.toFixed(1) : '?'}/10
  </span> blast radius &nbsp;|&nbsp;
  <strong>centrality: ${typeof centrality === 'number' ? centrality.toFixed(3) : '?'}</strong>

  <h2>Directly Affected Files (${direct.length})</h2>
  <ul>${listItems(direct.slice(0, 15))}</ul>

  <h2>Transitively Affected (${transitive.length})</h2>
  <ul>${listItems(transitive.slice(0, 10))}</ul>

  <h2>High-Complexity Functions</h2>
  <table>
    <tr><th>Function</th><th>Location</th><th>Complexity</th></tr>
    ${complexHtml}
  </table>

  <h2>Security Issues</h2>
  <table>
    <tr><th>Severity</th><th>Location</th><th>Description</th></tr>
    ${secHtml}
  </table>

  ${health ? `
  <h2>Project Health</h2>
  <p>
    Overall: <strong style="color:${scoreColor(health.overall ?? 0)}">${health.overall ?? '?'}/10</strong> &nbsp;|&nbsp;
    Security: <strong style="color:${scoreColor(health.security ?? 0)}">${health.security ?? '?'}/10</strong>
  </p>` : ''}
</body>
</html>`;
}
