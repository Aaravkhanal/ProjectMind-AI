"""
Dependency risk endpoints.

GET  /deps/risk?project_path=...   — scan + score all dependencies
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/deps", tags=["deps"])


class CVEModel(BaseModel):
    id: str
    severity: str
    summary: str


class DepRiskModel(BaseModel):
    name: str
    ecosystem: str
    declared_version: str
    latest_version: str
    days_since_release: int
    is_stale: bool
    has_maintainer: bool
    import_count: int
    cves: list[CVEModel]
    risk_score: float
    risk_level: str
    source: str


class DepsRiskResponse(BaseModel):
    project_path: str
    total_deps: int
    critical: int
    high: int
    medium: int
    low: int
    results: list[DepRiskModel]


@router.get("/risk", response_model=DepsRiskResponse)
def get_dep_risk(
    project_path: str = Query(..., description="Absolute path to the project root"),
    limit: int = Query(50, ge=1, le=200),
):
    root = Path(project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")

    from backend.core.deps.risk import score_dependencies

    try:
        results = score_dependencies(root)[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dependency scan failed: {e}")

    def _to_model(r) -> DepRiskModel:
        return DepRiskModel(
            name=r.name,
            ecosystem=r.ecosystem,
            declared_version=r.declared_version,
            latest_version=r.latest_version,
            days_since_release=r.days_since_release,
            is_stale=r.is_stale,
            has_maintainer=r.has_maintainer,
            import_count=r.import_count,
            cves=[CVEModel(id=c.id, severity=c.severity, summary=c.summary) for c in r.cves],
            risk_score=r.risk_score,
            risk_level=r.risk_level,
            source=r.source,
        )

    models = [_to_model(r) for r in results]
    return DepsRiskResponse(
        project_path=str(root),
        total_deps=len(models),
        critical=sum(1 for r in models if r.risk_level == "CRITICAL"),
        high=sum(1 for r in models if r.risk_level == "HIGH"),
        medium=sum(1 for r in models if r.risk_level == "MEDIUM"),
        low=sum(1 for r in models if r.risk_level == "LOW"),
        results=models,
    )
