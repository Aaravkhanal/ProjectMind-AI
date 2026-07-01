"""
Repository Brain API.

Exposes the accumulated learning from all past reviews:
  GET  /brain/summary              — dashboard numbers
  GET  /brain/hotspots             — files ranked by debt score
  GET  /brain/contributors         — per-author quality signals
  GET  /brain/debt                 — open tech debt items
  GET  /brain/insights             — aggregated text insights
  GET  /brain/reviews              — recent review history
  POST /brain/debt/{id}/resolve    — mark a debt item as resolved
  POST /brain/index                — manually index a review result
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/brain", tags=["brain"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_store(project_path: str):
    from backend.core.brain.store import BrainStore
    db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
    store = BrainStore(db_path=db_path)
    store.init_db()
    return store


def _get_indexer():
    from backend.core.brain.indexer import BrainIndexer
    db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
    return BrainIndexer(db_path=db_path)


# ── request / response models ──────────────────────────────────────────────────

class IndexRequest(BaseModel):
    project_path: str
    diff: str
    final_review: str
    architect_review: str = ""
    security_review: str = ""
    quality_review: str = ""
    pr_info: Optional[dict] = None
    task_complexity: str = "medium"
    models_used: Optional[list] = None
    estimated_cost_usd: float = 0.0
    duration_seconds: Optional[float] = None


class ResolveResponse(BaseModel):
    id: int
    resolved: bool
    resolved_at: Optional[str] = None


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/summary", summary="Repository brain dashboard")
def get_summary(project_path: str = "."):
    store = _get_store(project_path)
    return store.get_summary(project_path)


@router.get("/hotspots", summary="Files ranked by accumulated tech debt")
def get_hotspots(project_path: str = ".", limit: int = 20):
    store = _get_store(project_path)
    hotspots = store.get_hotspots(project_path, limit=limit)
    return [
        {
            "file_path": h.file_path,
            "change_count": h.change_count,
            "bug_count": h.bug_count,
            "review_flags": h.review_flags,
            "debt_score": h.debt_score,
            "last_changed": h.last_changed.isoformat(),
        }
        for h in hotspots
    ]


@router.get("/contributors", summary="Per-author quality and velocity signals")
def get_contributors(project_path: str = "."):
    store = _get_store(project_path)
    contributors = store.list_contributors(project_path)
    return [
        {
            "author": c.author,
            "pr_count": c.pr_count,
            "avg_diff_size": round(c.avg_diff_size, 1),
            "avg_quality_score": round(c.avg_quality_score, 2),
            "avg_security_score": round(c.avg_security_score, 2),
            "blocking_issues_total": c.blocking_issues_total,
            "first_pr": c.first_pr.isoformat() if c.first_pr else None,
            "last_pr": c.last_pr.isoformat() if c.last_pr else None,
        }
        for c in contributors
    ]


@router.get("/debt", summary="Open technical debt items")
def get_debt(
    project_path: str = ".",
    resolved: bool = False,
    severity: Optional[str] = None,
):
    store = _get_store(project_path)
    items = store.list_debt(project_path, resolved=resolved, severity=severity)
    return [
        {
            "id": d.id,
            "category": d.category,
            "severity": d.severity,
            "description": d.description,
            "file_path": d.file_path,
            "pr_review_id": d.pr_review_id,
            "created_at": d.created_at.isoformat(),
        }
        for d in items
    ]


@router.get("/insights", summary="Aggregated review insights")
def get_insights(project_path: str = "."):
    store = _get_store(project_path)
    insights = store.list_insights(project_path)
    return [
        {
            "type": i.insight_type,
            "title": i.title,
            "body": i.body,
            "confidence": i.confidence,
            "pr_count_basis": i.pr_count_basis,
            "updated_at": i.updated_at.isoformat(),
        }
        for i in insights
    ]


@router.get("/reviews", summary="Recent PR review history")
def get_reviews(project_path: str = ".", limit: int = 50):
    store = _get_store(project_path)
    reviews = store.list_reviews(project_path, limit=limit)
    return [
        {
            "id": r.id,
            "platform": r.platform,
            "pr_number": r.pr_number,
            "pr_title": r.pr_title,
            "author": r.author,
            "task_complexity": r.task_complexity,
            "files_changed": r.files_changed,
            "overall_score": r.overall_score,
            "blocking_issues": r.blocking_issues,
            "estimated_cost_usd": r.estimated_cost_usd,
            "created_at": r.created_at.isoformat(),
        }
        for r in reviews
    ]


@router.post("/debt/{debt_id}/resolve", summary="Mark a tech debt item as resolved")
def resolve_debt(debt_id: int, project_path: str = "."):
    store = _get_store(project_path)
    item = store.resolve_debt(debt_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Debt item {debt_id} not found")
    return ResolveResponse(
        id=item.id,
        resolved=item.resolved,
        resolved_at=item.resolved_at.isoformat() if item.resolved_at else None,
    )


@router.post("/index", summary="Manually index a review result into the brain")
def index_review(req: IndexRequest):
    indexer = _get_indexer()
    result = indexer.index(
        project_path=req.project_path,
        diff=req.diff,
        final_review=req.final_review,
        architect_review=req.architect_review,
        security_review=req.security_review,
        quality_review=req.quality_review,
        pr_info=req.pr_info,
        task_complexity=req.task_complexity,
        models_used=req.models_used,
        estimated_cost_usd=req.estimated_cost_usd,
        duration_seconds=req.duration_seconds,
    )
    return result
