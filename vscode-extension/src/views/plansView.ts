import * as vscode from "vscode";
import { ProjectMindClient } from "../projectmindClient";

interface PlanStep {
  id: number;
  step_number: number;
  title: string;
  status: string;
  agent_type?: string;
  effort?: string;
  requires_approval: boolean;
}

interface Plan {
  id: number;
  title: string;
  status: string;
  goal?: string;
  total_steps: number;
  approved_steps: number;
  completed_steps: number;
  steps?: PlanStep[];
}

type PItem = vscode.TreeItem & { _plan?: Plan; _step?: PlanStep; children?: PItem[] };

export class PlansView implements vscode.TreeDataProvider<PItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<PItem | undefined | null | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private data: PItem[] = [];

  constructor(private client: ProjectMindClient, private workspaceRoot: string) {}

  refresh(): void { this._onDidChangeTreeData.fire(); }

  async load(): Promise<void> {
    const plans = await this.client.fetchPlans(this.workspaceRoot);
    this.data = [];

    if (plans.length === 0) {
      this.data = [makeLeaf("No execution plans — use /agents/plan to create one", "$(info)")];
      this.refresh();
      return;
    }

    for (const plan of (plans as unknown as Plan[]).slice(0, 15)) {
      const stepCount = `${plan.completed_steps}/${plan.total_steps}`;
      const label     = `${plan.title} [${plan.status}]`;
      const steps     = (plan.steps ?? []).map((s) => {
        const sl = makeLeaf(
          `${s.step_number}. ${s.title} [${s.status}]`,
          stepIcon(s.status),
          `Agent: ${s.agent_type ?? "—"} | Effort: ${s.effort ?? "—"} | Approval: ${s.requires_approval}`
        );
        (sl as any)._step = s;
        if (s.status === "pending" && s.requires_approval) {
          sl.contextValue = "pendingStep";
        }
        return sl;
      });

      const planItem = makeSection(label, planIcon(plan.status), steps);
      planItem.description = `${String(stepCount)} steps done`;
      (planItem as any)._plan = plan;
      if (plan.status === "pending_approval") {
        planItem.contextValue = "pendingPlan";
      }
      this.data.push(planItem);
    }

    this.refresh();
  }

  getTreeItem(el: PItem): vscode.TreeItem { return el; }
  getChildren(el?: PItem): PItem[] {
    if (!el) return this.data;
    return (el as any).children ?? [];
  }
}

function makeSection(label: string, icon: string, children: PItem[]): PItem {
  const item = new vscode.TreeItem(
    label,
    children.length > 0 ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None
  ) as PItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  (item as any).children = children;
  return item;
}

function makeLeaf(label: string, icon: string, tooltip?: string): PItem {
  const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None) as PItem;
  item.iconPath = new vscode.ThemeIcon(icon.replace(/\$\(|\)/g, ""));
  if (tooltip) item.tooltip = tooltip;
  return item;
}

function planIcon(status: string): string {
  const m: Record<string, string> = {
    draft: "circle-outline", pending_approval: "bell", approved: "check",
    in_progress: "sync~spin", completed: "pass-filled", cancelled: "circle-slash",
  };
  return m[status] ?? "circle-outline";
}

function stepIcon(status: string): string {
  const m: Record<string, string> = {
    pending: "circle-outline", approved: "check", in_progress: "sync~spin",
    done: "pass", skipped: "dash", rejected: "x",
  };
  return m[status] ?? "dash";
}
