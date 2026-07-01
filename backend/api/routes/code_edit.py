"""
Autonomous Code Editing API.

POST /edit/plan      — generate an edit plan (no changes applied)
POST /edit/apply     — apply a previously returned plan
POST /edit/execute   — plan + apply in one call (autonomous mode)
POST /edit/rollback  — git stash pop (undo last autonomous edit)
POST /edit/pipeline  — sequential agent pipeline: plan → refactor → test → docs
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/edit", tags=["code-editing"])


class EditRequest(BaseModel):
    project_path: str = "."
    goal: str
    target_files: Optional[list[str]] = None
    extra_context: str = ""
    model: str = "claude-sonnet-4-6"
    mode: str = "safe"    # safe | approval | autonomous


class ApplyPlanRequest(BaseModel):
    project_path: str = "."
    goal: str
    changes: list[dict]   # list of {action, path, content, reason}
    risks: list[str] = []
    model: str = "claude-sonnet-4-6"


class PipelineRequest(BaseModel):
    project_path: str = "."
    code: str
    language: str = "python"
    description: str = ""
    stages: Optional[list[str]] = None   # ["plan", "refactor", "testing", "docs"]


@router.post("/plan", summary="Generate edit plan without applying changes")
def plan_edit(req: EditRequest):
    """
    Analyzes the goal and target files, returns a structured edit plan.
    No files are modified. Use /edit/apply or /edit/execute to apply.
    """
    from backend.agents.code_editor import CodeEditorAgent

    agent = CodeEditorAgent(
        project_root=req.project_path,
        mode="safe",
        model=req.model,
    )
    try:
        result = agent.execute(
            goal=req.goal,
            target_files=req.target_files,
            extra_context=req.extra_context,
        )
        return {
            "goal":          result.plan.goal,
            "changes":       [
                {
                    "action":  c.action,
                    "path":    c.path,
                    "content": c.content,
                    "reason":  c.reason,
                }
                for c in result.plan.changes
            ],
            "risks":         result.plan.risks,
            "diff_preview":  result.diff_preview,
            "estimated_files": result.plan.estimated_files,
        }
    except Exception as e:
        raise HTTPException(500, f"Plan generation failed: {e}")


@router.post("/apply", summary="Apply a pre-generated edit plan")
def apply_plan(req: ApplyPlanRequest):
    """
    Apply changes from a plan returned by /edit/plan.
    Requires human review of the plan first (approval workflow).
    """
    from backend.agents.code_editor import CodeEditorAgent, EditPlan, FileChange

    changes = [
        FileChange(
            action=c.get("action", "edit"),
            path=c["path"],
            content=c.get("content"),
            reason=c.get("reason", ""),
        )
        for c in req.changes
    ]

    plan = EditPlan(
        goal=req.goal,
        changes=changes,
        risks=req.risks,
        estimated_files=len(changes),
        mode="approval",
    )

    agent = CodeEditorAgent(
        project_root=req.project_path,
        mode="approval",
        model=req.model,
    )
    try:
        result = agent.apply_plan(plan)
        return {
            "applied":          result.applied,
            "applied_changes":  result.applied_changes,
            "errors":           result.errors,
            "rollback_available": result.rollback_available,
        }
    except Exception as e:
        raise HTTPException(500, f"Apply failed: {e}")


@router.post("/execute", summary="Generate plan AND apply immediately (autonomous mode)")
def execute_autonomous(req: EditRequest):
    """
    Plans and applies changes in a single call.
    Use mode='autonomous' for fully automatic execution.
    git stash is used as a safety net — call /edit/rollback to undo.
    """
    from backend.agents.code_editor import CodeEditorAgent

    agent = CodeEditorAgent(
        project_root=req.project_path,
        mode=req.mode,
        model=req.model,
    )
    try:
        result = agent.execute(
            goal=req.goal,
            target_files=req.target_files,
            extra_context=req.extra_context,
        )
        return {
            "mode":               result.mode,
            "applied":            result.applied,
            "goal":               result.plan.goal,
            "applied_changes":    result.applied_changes,
            "errors":             result.errors,
            "risks":              result.plan.risks,
            "rollback_available": result.rollback_available,
            "diff_preview":       result.diff_preview,
        }
    except Exception as e:
        raise HTTPException(500, f"Execute failed: {e}")


@router.post("/rollback", summary="Undo last autonomous edit via git stash pop")
def rollback(project_path: str = "."):
    """
    Pops the git stash created by the last autonomous edit.
    Only works if the edit set rollback_available=True.
    """
    import subprocess
    result = subprocess.run(
        ["git", "stash", "pop"],
        cwd=project_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"ok": False, "message": result.stderr or "Nothing to rollback"}
    return {"ok": True, "message": "Rolled back successfully", "details": result.stdout}


@router.post("/pipeline", summary="Sequential agent pipeline: plan → refactor → test → docs")
def run_pipeline(req: PipelineRequest):
    """
    Runs multiple specialized agents sequentially.
    Each agent's output feeds into the next as context.

    Default pipeline: plan → refactor → testing → docs
    Custom stages: ["refactor", "testing"] for a shorter run.
    """
    from backend.agents.orchestration import sequential_pipeline

    try:
        result = sequential_pipeline(
            code=req.code,
            project_path=req.project_path,
            stages=req.stages,
            language=req.language,
            description=req.description,
        )
        return {
            "mode":           "sequential",
            "final_answer":   result.final_answer,
            "stages":         result.participants,
            "total_cost_usd": result.total_cost_usd,
        }
    except Exception as e:
        raise HTTPException(500, f"Pipeline failed: {e}")
