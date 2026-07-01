/**
 * Status bar — shows PM: 6.1/10 with color coding.
 * Updates every N seconds by reading health_score.json directly.
 */

import * as vscode from "vscode";
import { ProjectMindClient, HealthScore } from "../projectmindClient";

export class StatusBarProvider implements vscode.Disposable {
  private item: vscode.StatusBarItem;
  private timer: NodeJS.Timer | undefined;
  private client: ProjectMindClient | null = null;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = "projectmind.openDashboard";
    this.item.tooltip = "ProjectMind Health Score — click to open dashboard";
  }

  activate(client: ProjectMindClient): void {
    this.client = client;
    this.refresh();
    const interval =
      vscode.workspace
        .getConfiguration("projectmind")
        .get<number>("refreshIntervalSeconds", 30) * 1000;
    this.timer = setInterval(() => this.refresh(), interval);
    this.item.show();
  }

  refresh(): void {
    if (!this.client) return;
    if (!this.client.isInitialized) {
      this.item.text = "$(circle-slash) PM: not initialized";
      this.item.color = new vscode.ThemeColor("editorWarning.foreground");
      return;
    }

    const health = this.client.readHealthScore();
    if (!health) {
      this.item.text = "$(warning) PM: no data";
      this.item.color = new vscode.ThemeColor("editorWarning.foreground");
      return;
    }

    const score = health.overall;
    const { text, color } = this.scoreDisplay(score, health);
    this.item.text = text;
    this.item.color = color;
    this.item.backgroundColor =
      score < 5 ? new vscode.ThemeColor("statusBarItem.errorBackground") : undefined;
  }

  private scoreDisplay(
    score: number,
    health: HealthScore
  ): { text: string; color: vscode.ThemeColor | undefined } {
    const b = health.breakdown ?? {};
    const hasSecErrors = (b.security_errors ?? 0) > 0;
    const icon = score >= 7.5 ? "$(shield)" : score >= 5 ? "$(warning)" : "$(error)";
    const secFlag = hasSecErrors ? " ⚠SEC" : "";
    const color =
      score >= 7.5
        ? new vscode.ThemeColor("terminal.ansiGreen")
        : score >= 5
        ? new vscode.ThemeColor("terminal.ansiYellow")
        : new vscode.ThemeColor("terminal.ansiRed");
    return {
      text: `${icon} PM: ${score.toFixed(1)}/10${secFlag}`,
      color,
    };
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer as NodeJS.Timeout);
    this.item.dispose();
  }
}
