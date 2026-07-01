"""
Execution Planning + Human Approval API.

Plan lifecycle:
  draft → pending_approval → approved → in_progress → completed | cancelled

Step lifecycle:
  pending → approved | rejected → in_progress → done | skipped

Endpoints:
  POST   /plans                              create plan (from planner output or manual)
  GET    /plans                              list plans for a project
  GET    /plans/{id}                         get plan + all steps
  POST   /plans/{id}/submit                  draft → pending_approval
  POST   /plans/{id}/approve                 approve whole plan (and non-flagged steps)
  POST   /plans/{id}/cancel                  cancel plan
  POST   /plans/{id}/steps/{sid}/approve     approve individual step
  POST   /plans/{id}/steps/{sid}/reject      reject step with reason
  POST   /plans/{id}/steps/{sid}/start       mark step in_progress
  POST   /plans/{id}/steps/{sid}/complete    mark step done + store output
  POST   /plans/{id}/steps/{sid}/skip        skip step
  POST   /plans/{id}/steps/{sid}/execute     run the assigned specialized agent
"""

from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/plans", tags=["execution"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _store():
    from backend.core.execution.store import ExecutionStore
    db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
    store = ExecutionStore(db_path=db_path)
    store.init_db()
    return store


def _plan_or_404(store, plan_id: int):
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return plan


def _step_or_404(store, plan_id: int, step_id: int):
    steps = store.get_steps(plan_id)
    for s in steps:
        if s.id == step_id:
            return s
    raise HTTPException(status_code=404, detail=f"Step {step_id} not found in plan {plan_id}")


def _plan_out(plan, steps=None) -> dict:
    d = {
        "id": plan.id,
        "project_path": plan.project_path,
        "title": plan.title,
        "goal": plan.goal,
        "status": plan.status,
        "source": plan.source,
        "total_steps": plan.total_steps,
        "approved_steps": plan.approved_steps,
        "completed_steps": plan.completed_steps,
        "estimated_effort": plan.estimated_effort,
        "estimated_cost_usd": plan.estimated_cost_usd,
        "created_by": plan.created_by,
        "approved_by": plan.approved_by,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }
    if steps is not None:
        d["steps"] = [_step_out(s) for s in steps]
    return d


def _step_out(step) -> dict:
    return {
        "id": step.id,
        "plan_id": step.plan_id,
        "step_number": step.step_number,
        "title": step.title,
        "description": step.description,
        "files": json.loads(step.files or "[]"),
        "effort": step.effort,
        "agent_type": step.agent_type,
        "requires_approval": step.requires_approval,
        "status": step.status,
        "approved_by": step.approved_by,
        "approved_at": step.approved_at.isoformat() if step.approved_at else None,
        "rejection_reason": step.rejection_reason,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        "output": step.output,
        "output_type": step.output_type,
        "created_at": step.created_at.isoformat(),
    }


# ── Request models ─────────────────────────────────────────────────────────────

class CreatePlanRequest(BaseModel):
    project_path: str = "."
    # Option A: from planner output
    planner_output: Optional[str] = None
    # Option B: manual steps
    title: Optional[str] = None
    goal: Optional[str] = None
    steps: Optional[list[dict]] = None
    # Meta
    created_by: Optional[str] = None
    source: str = "planner"
    source_ref: Optional[str] = None
    estimated_cost_usd: float = 0.0


class ApproveStepRequest(BaseModel):
    approved_by: str = "human"


class RejectStepRequest(BaseModel):
    reason: str = ""
    approved_by: str = "human"


class CompleteStepRequest(BaseModel):
    output: str = ""
    output_type: str = "notes"   # "code" | "markdown" | "notes"


class SkipStepRequest(BaseModel):
    reason: str = ""


class ExecuteStepRequest(BaseModel):
    """Run the step's assigned specialized agent."""
    code: str                           # code context for the agent
    description: str = ""
    file_path: Optional[str] = None
    language: str = "python"
    api_key: Optional[str] = None
    llm_provider: str = "nvidia"
    budget_per_task_usd: float = 1.0
    extra: dict = {}


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("", summary="Create an execution plan")
def create_plan(req: CreatePlanRequest):
    """
    Two creation modes:
    - Pass `planner_output` (markdown from POST /agents/plan) → auto-parsed into steps
    - Pass `title` + `goal` + `steps` array → manual plan
    """
    store = _store()

    if req.planner_output:
        from backend.core.execution.parser import parse
        parsed = parse(req.planner_output)
        plan = store.create_from_parsed(
            project_path=req.project_path,
            parsed=parsed,
            created_by=req.created_by,
            source=req.source,
            source_ref=req.source_ref,
            estimated_cost_usd=req.estimated_cost_usd,
        )
    elif req.title and req.goal and req.steps is not None:
        plan = store.create_manual(
            project_path=req.project_path,
            title=req.title,
            goal=req.goal,
            steps_data=req.steps,
            created_by=req.created_by,
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either `planner_output` or `title` + `goal` + `steps`.",
        )

    steps = store.get_steps(plan.id)
    return _plan_out(plan, steps)


@router.get("", summary="List execution plans for a project")
def list_plans(project_path: str = ".", status: Optional[str] = None, limit: int = 50):
    store = _store()
    plans = store.list_plans(project_path, status=status, limit=limit)
    return [_plan_out(p) for p in plans]


@router.get("/{plan_id}", summary="Get plan with all steps")
def get_plan(plan_id: int):
    store = _store()
    plan = _plan_or_404(store, plan_id)
    steps = store.get_steps(plan_id)
    return _plan_out(plan, steps)


@router.post("/{plan_id}/submit", summary="Submit plan for approval")
def submit_plan(plan_id: int):
    store = _store()
    _plan_or_404(store, plan_id)
    plan = store.submit_for_approval(plan_id)
    return _plan_out(plan, store.get_steps(plan_id))


@router.post("/{plan_id}/approve", summary="Approve the entire plan")
def approve_plan(plan_id: int, req: ApproveStepRequest = ApproveStepRequest()):
    store = _store()
    _plan_or_404(store, plan_id)
    plan = store.approve_plan(plan_id, approved_by=req.approved_by)
    return _plan_out(plan, store.get_steps(plan_id))


@router.post("/{plan_id}/cancel", summary="Cancel a plan")
def cancel_plan(plan_id: int):
    store = _store()
    _plan_or_404(store, plan_id)
    plan = store.cancel_plan(plan_id)
    return _plan_out(plan)


# ── Step routes ───────────────────────────────────────────────────────────────

@router.post("/{plan_id}/steps/{step_id}/approve", summary="Approve a single step")
def approve_step(plan_id: int, step_id: int, req: ApproveStepRequest = ApproveStepRequest()):
    store = _store()
    _plan_or_404(store, plan_id)
    step = store.approve_step(plan_id, step_id, approved_by=req.approved_by)
    if not step:
        raise HTTPException(404, f"Step {step_id} not found")
    return _step_out(step)


@router.post("/{plan_id}/steps/{step_id}/reject", summary="Reject a step with a reason")
def reject_step(plan_id: int, step_id: int, req: RejectStepRequest):
    store = _store()
    _plan_or_404(store, plan_id)
    step = store.reject_step(plan_id, step_id, reason=req.reason, approved_by=req.approved_by)
    if not step:
        raise HTTPException(404, f"Step {step_id} not found")
    return _step_out(step)


@router.post("/{plan_id}/steps/{step_id}/start", summary="Mark a step as in-progress")
def start_step(plan_id: int, step_id: int):
    store = _store()
    _plan_or_404(store, plan_id)
    step = store.start_step(plan_id, step_id)
    if not step:
        raise HTTPException(404, f"Step {step_id} not found")
    return _step_out(step)


@router.post("/{plan_id}/steps/{step_id}/complete", summary="Mark a step as done")
def complete_step(plan_id: int, step_id: int, req: CompleteStepRequest):
    store = _store()
    _plan_or_404(store, plan_id)
    step = store.complete_step(plan_id, step_id, output=req.output, output_type=req.output_type)
    if not step:
        raise HTTPException(404, f"Step {step_id} not found")
    return _step_out(step)


@router.post("/{plan_id}/steps/{step_id}/skip", summary="Skip a step")
def skip_step(plan_id: int, step_id: int, req: SkipStepRequest = SkipStepRequest()):
    store = _store()
    _plan_or_404(store, plan_id)
    step = store.skip_step(plan_id, step_id, reason=req.reason)
    if not step:
        raise HTTPException(404, f"Step {step_id} not found")
    return _step_out(step)


@router.post("/{plan_id}/steps/{step_id}/execute", summary="Run the step's assigned specialized agent")
def execute_step(plan_id: int, step_id: int, req: ExecuteStepRequest):
    """
    If the step has an `agent_type` assigned (refactor / testing / docs),
    runs that specialized agent and stores the output on the step automatically.
    Moves the step to in_progress → done.
    """
    store = _store()
    _plan_or_404(store, plan_id)
    step = _step_or_404(store, plan_id, step_id)

    if step.status not in ("approved", "pending", "in_progress"):
        raise HTTPException(
            400,
            f"Step is {step.status} — can only execute approved/pending/in_progress steps.",
        )

    agent_type = step.agent_type
    if not agent_type:
        raise HTTPException(
            400,
            "This step has no agent_type assigned. Use /complete to mark it done manually.",
        )

    # Mark in_progress
    store.start_step(plan_id, step_id)

    # Build agent input
    from backend.agents.specialized.base import AgentInput
    inp = AgentInput(
        code=req.code,
        description=req.description or step.description or step.title,
        file_path=req.file_path or (json.loads(step.files or "[]") or [None])[0],
        language=req.language,
        project_context="",
        llm_provider=req.llm_provider or os.environ.get("LLM_PROVIDER", "nvidia"),
        api_key=req.api_key or os.environ.get("API_KEY", ""),
        budget_per_task_usd=req.budget_per_task_usd,
        extra=req.extra,
    )

    # Dispatch to the right agent
    from backend.agents.specialized import docs, refactor, testing
    agent_map = {
        "refactor": refactor.run,
        "testing":  testing.run,
        "docs":     docs.run,
    }
    runner = agent_map.get(agent_type)
    if not runner:
        raise HTTPException(400, f"No runner for agent_type '{agent_type}'")

    out = runner(inp)

    # Store output and mark done
    step = store.complete_step(
        plan_id, step_id,
        output=out.artifact,
        output_type="code" if agent_type in ("refactor", "testing") else "markdown",
    )

    return {
        "step": _step_out(step),
        "agent": agent_type,
        "model_used": out.model_used,
        "complexity": out.complexity,
        "estimated_cost_usd": out.estimated_cost_usd,
        "errors": out.errors,
    }
