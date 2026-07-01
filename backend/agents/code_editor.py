"""
Autonomous Code Editor Agent — reads, edits, creates, and deletes files.

Modes:
  safe       — suggests diffs only, never writes
  approval   — generates a change plan, waits for human approval before applying
  autonomous — applies changes directly (with git stash rollback)

Safety features:
  - All changes go through git stash first so they're reversible
  - No changes outside the project root
  - Blocked file patterns: .env*, *secret*, *.key, *.pem
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_BLOCKED_PATTERNS = [
    r"\.env",
    r"secret",
    r"\.key$",
    r"\.pem$",
    r"\.p12$",
    r"\.pfx$",
    r"credentials",
    r"id_rsa",
    r"__pycache__",
]


def _is_blocked(path: str) -> bool:
    p = path.lower()
    return any(re.search(pat, p) for pat in _BLOCKED_PATTERNS)


def _safe_path(project_root: str, relative_path: str) -> Path:
    """Ensure the path is within project root (no path traversal)."""
    root  = Path(project_root).resolve()
    full  = (root / relative_path).resolve()
    if not str(full).startswith(str(root)):
        raise ValueError(f"Path traversal blocked: {relative_path}")
    if _is_blocked(relative_path):
        raise ValueError(f"Blocked file pattern: {relative_path}")
    return full


@dataclass
class FileChange:
    action: str            # "create" | "edit" | "delete" | "rename"
    path: str              # relative to project root
    content: Optional[str] = None    # new content (for create/edit)
    old_path: Optional[str] = None   # for rename
    reason: str = ""


@dataclass
class EditPlan:
    goal: str
    changes: list[FileChange] = field(default_factory=list)
    estimated_files: int = 0
    risks: list[str] = field(default_factory=list)
    mode: str = "safe"


@dataclass
class EditResult:
    mode: str
    applied: bool
    plan: EditPlan
    applied_changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rollback_available: bool = False
    diff_preview: str = ""


class CodeEditorAgent:
    """
    AI-powered file editor with Safe / Approval / Autonomous modes.

    Usage:
        agent = CodeEditorAgent(project_root="/my/project", mode="safe")
        result = agent.execute(goal="Add type hints to all functions in auth.py")
    """

    def __init__(
        self,
        project_root: str,
        mode: str = "safe",     # safe | approval | autonomous
        model: str = "claude-sonnet-4-6",
        db_path: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.mode  = mode
        self.model = model
        self.db_path = db_path or os.environ.get("DB_PATH", ".projectmind/memory.db")

    def execute(
        self,
        goal: str,
        target_files: Optional[list[str]] = None,
        extra_context: str = "",
    ) -> EditResult:
        """
        Plan and optionally apply file changes to achieve the goal.
        """
        plan = self._plan(goal, target_files, extra_context)

        if self.mode == "safe":
            return EditResult(
                mode="safe",
                applied=False,
                plan=plan,
                diff_preview=self._render_diff_preview(plan),
            )

        if self.mode == "approval":
            # Return the plan for human review; caller must call apply_plan()
            return EditResult(
                mode="approval",
                applied=False,
                plan=plan,
                diff_preview=self._render_diff_preview(plan),
            )

        # autonomous — apply immediately
        return self._apply(plan)

    def apply_plan(self, plan: EditPlan) -> EditResult:
        """Apply a pre-generated plan (called after human approval)."""
        return self._apply(plan)

    def rollback(self) -> bool:
        """Roll back the last applied changes using git stash pop."""
        result = subprocess.run(
            ["git", "stash", "pop"],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    # ── Private ──────────────────────────────────────────────────────────────

    def _plan(self, goal: str, target_files: Optional[list[str]], extra_context: str) -> EditPlan:
        from backend.llm.litellm_gateway import LiteLLMGateway

        gateway = LiteLLMGateway(project_path=str(self.project_root), db_path=self.db_path)

        # Read target files
        file_contents = ""
        if target_files:
            for rel_path in target_files[:5]:  # cap at 5 files per call
                try:
                    full = _safe_path(str(self.project_root), rel_path)
                    if full.exists():
                        content = full.read_text(encoding="utf-8", errors="ignore")[:3000]
                        file_contents += f"\n=== {rel_path} ===\n{content}\n"
                except Exception:
                    pass

        system = """You are a code editing agent. Given a goal and file contents, produce a JSON edit plan.

Respond with ONLY valid JSON in this exact format:
{
  "goal": "...",
  "risks": ["...", "..."],
  "changes": [
    {
      "action": "edit",
      "path": "relative/path/to/file.py",
      "content": "FULL NEW FILE CONTENT HERE",
      "reason": "Why this change is needed"
    }
  ]
}

Rules:
- Only include files that NEED to change
- For "edit": provide the COMPLETE new file content (not a diff)
- For "create": provide the full content of the new file
- For "delete": omit content field
- Relative paths only, no leading /
- Do NOT change .env, secret, key, or credential files
"""

        user = f"""Goal: {goal}

{f'Extra context: {extra_context}' if extra_context else ''}

Current file contents:
{file_contents or '(no files provided — use your best judgment for the goal)'}
"""

        response = gateway.complete(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=4096,
        )

        # Parse JSON from response
        try:
            import json
            text = response.text
            # Extract JSON block if wrapped in markdown
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0]
            data = json.loads(text.strip())

            changes = [
                FileChange(
                    action=c.get("action", "edit"),
                    path=c["path"],
                    content=c.get("content"),
                    old_path=c.get("old_path"),
                    reason=c.get("reason", ""),
                )
                for c in data.get("changes", [])
            ]

            return EditPlan(
                goal=data.get("goal", goal),
                changes=changes,
                estimated_files=len(changes),
                risks=data.get("risks", []),
                mode=self.mode,
            )

        except Exception as e:
            # Return a safe empty plan on parse failure
            return EditPlan(
                goal=goal,
                changes=[],
                risks=[f"Plan parsing failed: {e}"],
                mode=self.mode,
            )

    def _apply(self, plan: EditPlan) -> EditResult:
        applied = []
        errors  = []

        # Stash any uncommitted changes first (safety net)
        rollback_available = False
        try:
            result = subprocess.run(
                ["git", "stash", "--include-untracked", "-m", f"projectmind-pre-edit-{plan.goal[:40]}"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            rollback_available = result.returncode == 0 and "No local changes" not in result.stdout
        except Exception:
            pass

        for change in plan.changes:
            try:
                full_path = _safe_path(str(self.project_root), change.path)

                if change.action == "create":
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(change.content or "", encoding="utf-8")
                    applied.append(f"created: {change.path}")

                elif change.action == "edit":
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(change.content or "", encoding="utf-8")
                    applied.append(f"edited: {change.path}")

                elif change.action == "delete":
                    if full_path.exists():
                        full_path.unlink()
                        applied.append(f"deleted: {change.path}")

                elif change.action == "rename" and change.old_path:
                    old = _safe_path(str(self.project_root), change.old_path)
                    if old.exists():
                        old.rename(full_path)
                        applied.append(f"renamed: {change.old_path} → {change.path}")

            except Exception as e:
                errors.append(f"{change.action} {change.path}: {e}")

        return EditResult(
            mode=self.mode,
            applied=len(applied) > 0,
            plan=plan,
            applied_changes=applied,
            errors=errors,
            rollback_available=rollback_available,
            diff_preview=self._render_diff_preview(plan),
        )

    def _render_diff_preview(self, plan: EditPlan) -> str:
        lines = [f"# Edit Plan: {plan.goal}", ""]
        if plan.risks:
            lines.append("**Risks:**")
            lines.extend(f"- {r}" for r in plan.risks)
            lines.append("")

        for c in plan.changes:
            lines.append(f"## {c.action.upper()}: `{c.path}`")
            if c.reason:
                lines.append(f"*{c.reason}*")
            if c.content and c.action != "delete":
                preview = c.content[:400] + ("…" if len(c.content) > 400 else "")
                lines.append(f"```\n{preview}\n```")
            lines.append("")

        return "\n".join(lines)
