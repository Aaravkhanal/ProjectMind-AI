import * as vscode from "vscode";
import { ProjectMindClient } from "../projectmindClient";

type BrainItem = vscode.TreeItem & { children?: BrainItem[] };

export class BrainView implements vscode.TreeDataProvider<BrainItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<BrainItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private data: BrainItem[] = [];

  constructor(private client: ProjectMindClient, private workspaceRoot: string) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  async load(): Promise<void> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const summary  = await this.client.fetchBrainSummary(this.workspaceRoot) as any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const hotspots = await this.client.fetchHotspots(this.workspaceRoot) as any[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const debt     = await this.client.fetchDebt(this.workspaceRoot) as any[];

    this.data = [];

    if (summary) {
      const statsSection = makeSection("Overview", "$(book)", [
        makeLeaf(`Total Reviews: ${summary.total_reviews}`, "$(history)"),
        makeLeaf(`Tech Debt Items: ${summary.total_debt_items}`, "$(warning)"),
        makeLeaf(`Contributors: ${summary.total_contributors}`, "$(person)"),
        makeLeaf(`Avg Quality: ${(summary.avg_quality_score as number)?.toFixed(1) ?? "—"}/10`, "$(star)"),
      ]);
      this.data.push(statsSection);
    }

    if (hotspots.length > 0) {
      const hotSection = makeSection(
        `Hot Files (${hotspots.length})`,
        "$(flame)",
        hotspots.slice(0, 8).map((h) => {
          const item = makeLeaf(
            path_tail(String(h.file_path)),
            debtIcon(Number(h.debt_score)),
            `Changes: ${h.change_count} | Debt: ${Number(h.debt_score).toFixed(1)}/10 | Bugs: ${h.bug_count}`
          );
          return item;
        })
      );
      this.data.push(hotSection);
    }

    if (debt.length > 0) {
      const byCat = groupBy(debt, (d) => String(d.category));
      const debtSection = makeSection(
        `Tech Debt (${debt.length})`,
        "$(tools)",
        Object.entries(byCat).map(([cat, items]) =>
          makeSection(
            `${cat} (${items.length})`,
            severityIcon(String(items[0]?.severity)),
            items.slice(0, 5).map((d) =>
              makeLeaf(truncate(String(d.description), 55), "$(circle-small)", String(d.file_path ?? ""))
            )
          )
        )
      );
      this.data.push(debtSection);
    }

    if (this.data.length === 0) {
      this.data = [makeLeaf("No brain data yet — run a review first", "$(info)")];
    }

    this.refresh();
  }

  getTreeItem(element: BrainItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: BrainItem): BrainItem[] {
    if (!element) return this.data;
    return (element as any).children ?? [];
  }
}

function makeSection(label: string, icon: string, children: BrainItem[]): BrainItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.Expanded) as BrainItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  (item as any).children = children;
  return item;
}

function makeLeaf(label: string, icon: string, tooltip?: string): BrainItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None) as BrainItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  if (tooltip) item.tooltip = tooltip;
  return item;
}

function debtIcon(score: number): string {
  if (score >= 7) return "$(error)";
  if (score >= 4) return "$(warning)";
  return "$(pass)";
}

function severityIcon(sev?: string): string {
  if (sev === "critical") return "$(error)";
  if (sev === "high") return "$(warning)";
  return "$(info)";
}

function groupBy<T>(arr: T[], key: (t: T) => string): Record<string, T[]> {
  return arr.reduce<Record<string, T[]>>((acc, t) => {
    (acc[key(t)] = acc[key(t)] ?? []).push(t);
    return acc;
  }, {});
}

function path_tail(p: string): string {
  return p.split(/[/\\]/).pop() ?? p;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
