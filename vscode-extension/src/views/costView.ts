import * as vscode from "vscode";
import { ProjectMindClient } from "../projectmindClient";

type CItem = vscode.TreeItem & { children?: CItem[] };

export class CostView implements vscode.TreeDataProvider<CItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<CItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private data: CItem[] = [];

  constructor(private client: ProjectMindClient, private workspaceRoot: string) {}

  refresh(): void { this._onDidChangeTreeData.fire(); }

  async load(): Promise<void> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const summary = await this.client.fetchCostSummary(this.workspaceRoot) as any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const alerts  = await this.client.fetchCostAlerts(this.workspaceRoot) as any[];
    this.data = [];

    if (alerts.length > 0) {
      this.data.push(
        makeSection(
          `Budget Alerts (${alerts.length})`,
          "$(bell-dot)",
          alerts.map((a) => makeLeaf(String(a.message), "$(warning)", `${Number(a.percent_used).toFixed(1)}% used`))
        )
      );
    }

    if (summary) {
      const budget = (summary.budget ?? {}) as Record<string, unknown>;
      const limit  = budget.limit != null ? `$${Number(budget.limit).toFixed(2)}` : "No limit";
      const pct    = budget.percent_used != null ? ` (${budget.percent_used}%)` : "";

      this.data.push(
        makeSection("This Month", "$(credit-card)", [
          makeLeaf(`Spend: $${Number(summary.spend_this_month).toFixed(4)}`, "$(credit-card)"),
          makeLeaf(`Budget: ${limit}${pct}`, budgetIcon(Number(budget.percent_used))),
          makeLeaf(`Remaining: $${budget.remaining != null ? Number(budget.remaining).toFixed(4) : "∞"}`, "$(pass)"),
          makeLeaf(`Forecast: $${Number(summary.monthly_forecast_usd).toFixed(3)}/mo`, "$(graph)"),
          makeLeaf(`Operations: ${summary.total_operations}`, "$(list-unordered)"),
          makeLeaf(`Downgraded: ${summary.downgraded_count}`, "$(arrow-down)"),
        ])
      );

      const byOp = (summary.breakdown_by_operation ?? {}) as Record<string, number>;
      if (Object.keys(byOp).length > 0) {
        this.data.push(
          makeSection(
            "By Operation",
            "$(pie-chart)",
            Object.entries(byOp).map(([op, cost]) =>
              makeLeaf(`${op}: $${cost.toFixed(6)}`, "$(dash)")
            )
          )
        );
      }

      const byTier = (summary.breakdown_by_tier ?? {}) as Record<string, number>;
      if (Object.keys(byTier).length > 0) {
        this.data.push(
          makeSection(
            "By Model Tier",
            "$(server)",
            Object.entries(byTier).map(([tier, cost]) =>
              makeLeaf(`${tier}: $${cost.toFixed(6)}`, tierIcon(tier))
            )
          )
        );
      }
    }

    if (this.data.length === 0) {
      this.data = [makeLeaf("No cost data yet — run a review to start tracking", "$(info)")];
    }

    this.refresh();
  }

  getTreeItem(el: CItem): vscode.TreeItem { return el; }
  getChildren(el?: CItem): CItem[] {
    if (!el) return this.data;
    return (el as any).children ?? [];
  }
}

function makeSection(label: string, icon: string, children: CItem[]): CItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.Expanded) as CItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  (item as any).children = children;
  return item;
}

function makeLeaf(label: string, icon: string, tooltip?: string): CItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None) as CItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  if (tooltip) item.tooltip = tooltip;
  return item;
}

function budgetIcon(pct: number): string {
  if (!pct) return "pass";
  if (pct >= 100) return "error";
  if (pct >= 80) return "warning";
  return "pass";
}

function tierIcon(tier: string): string {
  const m: Record<string, string> = {
    fast: "zap", balanced: "server", powerful: "rocket", reasoning: "lightbulb",
  };
  return m[tier] ?? "dash";
}
