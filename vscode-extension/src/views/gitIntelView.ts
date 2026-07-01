import * as vscode from "vscode";
import { ProjectMindClient } from "../projectmindClient";

type GIItem = vscode.TreeItem & { children?: GIItem[] };

export class GitIntelView implements vscode.TreeDataProvider<GIItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<GIItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private data: GIItem[] = [];

  constructor(private client: ProjectMindClient, private workspaceRoot: string) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  async load(): Promise<void> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const summary = await this.client.fetchGitIntelSummary(this.workspaceRoot) as any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const churn   = await this.client.fetchChurn(this.workspaceRoot) as any[];

    this.data = [];

    if (summary) {
      const byType = (summary.commits_by_type ?? {}) as Record<string, number>;
      const typeRows = Object.entries(byType)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([t, n]) => makeLeaf(`${t}: ${n}`, commitIcon(t)));

      this.data.push(
        makeSection("Commit Stats", "$(git-commit)", [
          makeLeaf(`Total: ${summary.total_commits ?? 0}`, "$(git-commit)"),
          makeLeaf(`Analyzed: ${summary.enriched_commits ?? 0}`, "$(telescope)"),
          ...typeRows,
        ])
      );

      if (summary.latest_risk) {
        const r = summary.latest_risk as Record<string, unknown>;
        const lvl = String(r.risk_level ?? "unknown");
        this.data.push(
          makeSection("Latest PR Risk", riskIcon(lvl), [
            makeLeaf(`Overall: ${Number(r.overall_risk ?? 0).toFixed(1)}/10 [${lvl.toUpperCase()}]`, riskIcon(lvl)),
            ...Object.entries((r.breakdown ?? {}) as Record<string, number>).map(([k, v]) =>
              makeLeaf(`${k}: ${v.toFixed(1)}`, "$(dash)")
            ),
          ])
        );
      }
    }

    if (churn.length > 0) {
      this.data.push(
        makeSection(
          `Churn Hot Spots (${churn.length})`,
          "$(flame)",
          churn.slice(0, 8).map((c) =>
            makeLeaf(
              path_tail(String(c.file_path)),
              churnIcon(Number(c.churn_score)),
              `Churn: ${Number(c.churn_score).toFixed(1)} | 30d commits: ${c.commits_30d} | Authors: ${c.unique_authors}`
            )
          )
        )
      );
    }

    if (this.data.length === 0) {
      this.data = [makeLeaf("No git intel yet — run /git-intel/analyze first", "$(info)")];
    }

    this.refresh();
  }

  getTreeItem(el: GIItem): vscode.TreeItem { return el; }
  getChildren(el?: GIItem): GIItem[] {
    if (!el) return this.data;
    return (el as any).children ?? [];
  }
}

function makeSection(label: string, icon: string, children: GIItem[]): GIItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.Expanded) as GIItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  (item as any).children = children;
  return item;
}

function makeLeaf(label: string, icon: string, tooltip?: string): GIItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None) as GIItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  if (tooltip) item.tooltip = tooltip;
  return item;
}

function commitIcon(type: string): string {
  const m: Record<string, string> = {
    feature: "$(add)", bug_fix: "$(bug)", refactor: "$(edit)",
    docs: "$(book)", test: "$(beaker)", chore: "$(settings-gear)",
    revert: "$(discard)", other: "$(circle-small)",
  };
  return m[type] ?? "$(circle-small)";
}

function riskIcon(level: string): string {
  if (level === "critical") return "$(error)";
  if (level === "high") return "$(warning)";
  if (level === "medium") return "$(info)";
  return "$(pass)";
}

function churnIcon(score: number): string {
  if (score >= 7) return "$(error)";
  if (score >= 4) return "$(warning)";
  return "$(pass)";
}

function path_tail(p: string): string {
  return p.split(/[/\\]/).pop() ?? p;
}
