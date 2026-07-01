"""
Root cause tracer endpoint.

POST /tracer/trace
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/tracer", tags=["tracer"])


class TraceRequest(BaseModel):
    project_path: str
    error_text: str


class CauseModel(BaseModel):
    rank: int
    kind: str
    confidence: float
    description: str
    detail: str
    file: Optional[str] = None
    commit: Optional[str] = None


class TraceResponse(BaseModel):
    error_summary: str
    affected_files: list[str]
    affected_modules: list[str]
    causes: list[CauseModel]
    similar_past_errors: list[dict]


@router.post("/trace", response_model=TraceResponse)
def trace(req: TraceRequest):
    root = Path(req.project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")
    if not (root / ".projectmind").exists():
        raise HTTPException(status_code=400, detail="Run `projectmind init` first.")

    from backend.core.tracer.tracer import RootCauseTracer
    try:
        result = RootCauseTracer(str(root)).trace(req.error_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tracer failed: {e}")

    return TraceResponse(
        error_summary=result.error_summary,
        affected_files=result.affected_files,
        affected_modules=result.affected_modules,
        causes=[CauseModel(**{k: v for k, v in c.__dict__.items()}) for c in result.causes],
        similar_past_errors=result.similar_past_errors,
    )
