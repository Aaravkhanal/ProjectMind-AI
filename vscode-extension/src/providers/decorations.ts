/**
 * Inline decorations — shows complexity warnings directly in the editor.
 *
 * Reads high_complexity_functions from architecture_report.json and
 * annotates the matching function definition lines with an inline gutter icon
 * and end-of-line message like:  ⚠ complexity: 14  (threshold: 10)
 */

import * as vscode from "vscode";
import * as path from "path";
import { ProjectMindClient } from "../projectmindClient";

const COMPLEXITY_DECORATION = vscode.window.createTextEditorDecorationType({
  after: {
    margin: "0 0 0 2em",
    color: new vscode.ThemeColor("editorWarning.foreground"),
    fontStyle: "italic",
  },
  gutterIconPath: undefined,
  overviewRulerColor: new vscode.ThemeColor("editorWarning.foreground"),
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

const SECURITY_DECORATION = vscode.window.createTextEditorDecorationType({
  after: {
    margin: "0 0 0 2em",
    color: new vscode.ThemeColor("editorError.foreground"),
    fontStyle: "italic",
  },
  overviewRulerColor: new vscode.ThemeColor("editorError.foreground"),
  overviewRulerLane: vscode.OverviewRulerLane.Right,
});

export class DecorationsProvider implements vscode.Disposable {
  private disposables: vscode.Disposable[] = [];
  private client: ProjectMindClient | null = null;
  private workspaceRoot: string = "";

  activate(client: ProjectMindClient, workspaceRoot: string): void {
    this.client = client;
    this.workspaceRoot = workspaceRoot;

    this.disposables.push(
      vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (editor) this.decorate(editor);
      }),
      vscode.workspace.onDidSaveTextDocument(() => {
        if (vscode.window.activeTextEditor) {
          this.decorate(vscode.window.activeTextEditor);
        }
      })
    );

    if (vscode.window.activeTextEditor) {
      this.decorate(vscode.window.activeTextEditor);
    }
  }

  decorate(editor: vscode.TextEditor): void {
    if (!this.client) return;
    const showDecorations = vscode.workspace
      .getConfiguration("projectmind")
      .get<boolean>("showComplexityDecorations", true);
    if (!showDecorations) {
      editor.setDecorations(COMPLEXITY_DECORATION, []);
      editor.setDecorations(SECURITY_DECORATION, []);
      return;
    }

    const threshold = vscode.workspace
      .getConfiguration("projectmind")
      .get<number>("complexityThreshold", 10);

    const docPath = editor.document.uri.fsPath;
    const relPath = path
      .relative(this.workspaceRoot, docPath)
      .replace(/\\/g, "/");

    // ── Complexity decorations ─────────────────────────────────────────
    const complexFns = this.client.readComplexFunctions().filter((fn) => {
      const fnFile = fn.file.replace(/\\/g, "/");
      return (
        fnFile === relPath ||
        fnFile.endsWith("/" + relPath) ||
        relPath.endsWith("/" + fnFile)
      );
    });

    const complexRanges: vscode.DecorationOptions[] = complexFns
      .filter((fn) => fn.complexity >= threshold)
      .map((fn) => {
        const lineIdx = Math.max(0, fn.line - 1);
        const line = editor.document.lineAt(Math.min(lineIdx, editor.document.lineCount - 1));
        return {
          range: line.range,
          renderOptions: {
            after: {
              contentText: `  ⚠ complexity: ${fn.complexity} (threshold: ${threshold})`,
            },
          },
        };
      });

    editor.setDecorations(COMPLEXITY_DECORATION, complexRanges);

    // ── Security decorations ───────────────────────────────────────────
    const secIssues = this.client.readSecurityIssues().filter((i) => {
      const iFile = i.file.replace(/\\/g, "/");
      return (
        iFile === relPath ||
        iFile.endsWith("/" + relPath) ||
        relPath.endsWith("/" + iFile)
      );
    });

    const secRanges: vscode.DecorationOptions[] = secIssues.map((i) => {
      const lineIdx = Math.max(0, (i.line ?? 1) - 1);
      const line = editor.document.lineAt(Math.min(lineIdx, editor.document.lineCount - 1));
      return {
        range: line.range,
        renderOptions: {
          after: {
            contentText: `  ✗ ${i.severity?.toUpperCase()}: ${i.description?.slice(0, 60)}`,
          },
        },
      };
    });

    editor.setDecorations(SECURITY_DECORATION, secRanges);
  }

  dispose(): void {
    this.disposables.forEach((d) => d.dispose());
    COMPLEXITY_DECORATION.dispose();
    SECURITY_DECORATION.dispose();
  }
}
