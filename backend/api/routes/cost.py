"""
Cost Optimization Engine API.

GET  /cost/summary            — spend analytics, forecast, budget status
GET  /cost/budget             — current budget for a project
POST /cost/budget             — set / update project budget
GET  /cost/history            — per-operation cost records
GET  /cost/alerts             — unacknowledged budget alerts
POST /cost/alerts/acknowledge — clear alerts for a project
POST /cost/optimize           — estimate cost + show model downgrade plan
POST /cost/record             — manually record a cost (for external callers)
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/cost", tags=["cost"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _store():
    from backend.core.cost.store import CostStore
    db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
    s = CostStore(db_path=db_path)
    s.init_db()
    return s


# ── request / response models ──────────────────────────────────────────────────

class SetBudgetRequest(BaseModel):
    project_path: str = "."
    monthly_limit_usd: float = 10.0
    alert_at_percent: float = 80.0
    hard_limit: bool = False
    fallback_tier: str = "fast"    # fast|balanced|powerful|reasoning


class OptimizeRequest(BaseModel):
    project_path: str = "."
    complexity: str = "medium"         # simple|medium|complex
    preferred_provider: str = "nvidia"
    per_call_budget_usd: Optional[float] = None   # override monthly budget for this call


class RecordCostRequest(BaseModel):
    project_path: str = "."
    operation: str                     # review|plan|refactor|testing|docs|pipeline
    model_id: str
    provider: str
    model_tier: str = "balanced"
    agent_role: Optional[str] = None
    tokens_input: int = 0
    tokens_output: int = 0
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    was_downgraded: bool = False
    original_model_id: Optional[str] = None
    duration_seconds: Optional[float] = None


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/summary", summary="Spend analytics, forecast, and budget status")
def get_summary(project_path: str = "."):
    """
    Returns:
    - spend this month vs last month + MoM change
    - monthly forecast at current burn rate
    - breakdown by operation, model tier, and top models
    - budget utilization and remaining
    - unacknowledged alert count
    """
    store = _store()
    return store.get_summary(project_path)


@router.get("/budget", summary="Get current budget settings for a project")
def get_budget(project_path: str = "."):
    store = _store()
    budget = store.get_budget(project_path)
    if not budget:
        return {
            "project_path":       project_path,
            "monthly_limit_usd":  None,
            "alert_at_percent":   None,
            "hard_limit":         False,
            "fallback_tier":      "fast",
            "spend_this_month":   store.get_spend(project_path),
            "configured":         False,
        }
    spend = store.get_spend(project_path)
    return {
        "project_path":       budget.project_path,
        "monthly_limit_usd":  budget.monthly_limit_usd,
        "alert_at_percent":   budget.alert_at_percent,
        "hard_limit":         budget.hard_limit,
        "fallback_tier":      budget.fallback_tier,
        "spend_this_month":   round(spend, 6),
        "remaining":          round(budget.monthly_limit_usd - spend, 4),
        "percent_used":       round(spend / budget.monthly_limit_usd * 100, 1) if budget.monthly_limit_usd else 0,
        "configured":         True,
        "updated_at":         budget.updated_at.isoformat(),
    }


@router.post("/budget", summary="Set or update project budget")
def set_budget(req: SetBudgetRequest):
    """
    Configure a monthly budget for a project.

    When `hard_limit=True`, the system will raise an error if a review
    is requested after the budget is exhausted. Otherwise it just fires alerts.

    `fallback_tier` controls which model tier to fall back to when budget
    is tight (e.g. "fast" = 8B models, "balanced" = 70B models).
    """
    store = _store()
    budget = store.set_budget(
        project_path=req.project_path,
        monthly_limit_usd=req.monthly_limit_usd,
        alert_at_percent=req.alert_at_percent,
        hard_limit=req.hard_limit,
        fallback_tier=req.fallback_tier,
    )
    return {
        "project_path":      budget.project_path,
        "monthly_limit_usd": budget.monthly_limit_usd,
        "alert_at_percent":  budget.alert_at_percent,
        "hard_limit":        budget.hard_limit,
        "fallback_tier":     budget.fallback_tier,
        "updated_at":        budget.updated_at.isoformat(),
    }


@router.get("/history", summary="Per-operation cost records")
def get_history(
    project_path: str = ".",
    billing_month: Optional[str] = None,   # e.g. "2026-06"
    operation: Optional[str] = None,
    limit: int = 100,
):
    store = _store()
    records = store.list_records(
        project_path, billing_month=billing_month, operation=operation, limit=limit
    )
    return [
        {
            "id":                  r.id,
            "operation":           r.operation,
            "agent_role":          r.agent_role,
            "model_id":            r.model_id,
            "model_tier":          r.model_tier,
            "provider":            r.provider,
            "tokens_input":        r.tokens_input,
            "tokens_output":       r.tokens_output,
            "estimated_cost_usd":  r.estimated_cost_usd,
            "actual_cost_usd":     r.actual_cost_usd,
            "was_downgraded":      r.was_downgraded,
            "original_model_id":   r.original_model_id,
            "billing_month":       r.billing_month,
            "duration_seconds":    r.duration_seconds,
            "created_at":          r.created_at.isoformat(),
        }
        for r in records
    ]


@router.get("/alerts", summary="Unacknowledged budget alerts")
def get_alerts(project_path: str = "."):
    store = _store()
    alerts = store.list_alerts(project_path, unacknowledged_only=True)
    return [
        {
            "id":            a.id,
            "type":          a.alert_type,
            "message":       a.message,
            "spend":         a.spend_at_alert,
            "limit":         a.budget_limit,
            "percent_used":  a.percent_used,
            "created_at":    a.created_at.isoformat(),
        }
        for a in alerts
    ]


@router.post("/alerts/acknowledge", summary="Acknowledge all alerts for a project")
def acknowledge_alerts(project_path: str = "."):
    store = _store()
    count = store.acknowledge_alerts(project_path)
    return {"acknowledged": count}


@router.post("/optimize", summary="Estimate cost and model selection with budget constraints")
def optimize(req: OptimizeRequest):
    """
    Pre-flight cost estimate for a review at the given complexity level.
    Shows:
    - What models would be selected normally (full quality)
    - What models get selected with budget constraints applied
    - Potential savings
    - Which agents would be downgraded

    No DB writes — purely informational.
    """
    from backend.core.cost.optimizer import CostOptimizer
    from backend.llm.router import TaskComplexity

    try:
        complexity = TaskComplexity(req.complexity)
    except ValueError:
        raise HTTPException(400, f"Invalid complexity: {req.complexity}. Use simple|medium|complex")

    optimizer = CostOptimizer(
        project_path=req.project_path,
        preferred_provider=req.preferred_provider,
    )

    estimate = optimizer.estimate_review_cost(complexity)

    # Also show per-agent optimized decisions
    try:
        decisions = optimizer.optimize_all_agents(complexity)
        per_agent_detail = [
            {
                "agent":            role,
                "model":            d.model.model_id,
                "tier":             d.model.tier.value,
                "was_downgraded":   d.was_downgraded,
                "original_model":   d.original_model.model_id if d.original_model else None,
                "estimated_cost":   d.estimated_cost_usd,
                "reason":           d.reason[:120],
            }
            for role, d in decisions.items()
        ]
        estimate["per_agent_detail"] = per_agent_detail
    except Exception as e:
        estimate["optimization_error"] = str(e)

    return estimate


@router.post("/record", summary="Record a cost entry (for external callers or CI)")
def record_cost(req: RecordCostRequest):
    store = _store()
    record = store.record_cost(
        project_path=req.project_path,
        operation=req.operation,
        model_id=req.model_id,
        provider=req.provider,
        model_tier=req.model_tier,
        agent_role=req.agent_role,
        tokens_input=req.tokens_input,
        tokens_output=req.tokens_output,
        estimated_cost_usd=req.estimated_cost_usd,
        actual_cost_usd=req.actual_cost_usd,
        was_downgraded=req.was_downgraded,
        original_model_id=req.original_model_id,
        duration_seconds=req.duration_seconds,
    )
    return {
        "id":                 record.id,
        "billing_month":      record.billing_month,
        "actual_cost_usd":    record.actual_cost_usd,
        "was_downgraded":     record.was_downgraded,
        "created_at":         record.created_at.isoformat(),
    }
