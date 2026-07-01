"""
ADR (Architecture Decision Record) endpoints.

GET  /adr/list?project_path=...          — list existing ADRs
GET  /adr/detect?project_path=...        — detect ADR-worthy changes
POST /adr/create                          — create a new ADR
POST /adr/auto                           — auto-create from detected change
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/adr", tags=["adr"])


class ADRCreateRequest(BaseModel):
    project_path: str
    title: str
    context: str
    decision: str
    positive: list[str] = []
    negative: list[str] = []
    status: str = "accepted"
    deciders: Optional[str] = None


class ADRResponse(BaseModel):
    file: str
    path: str
    number: int


class DetectedChangeModel(BaseModel):
    kind: str
    title: str
    context: str
    suggested_decision: str
    positive: list[str]
    negative: list[str]
    auto_confidence: float


@router.get("/list")
def list_adrs(project_path: str = Query(...)):
    root = _require(project_path)
    from backend.core.adr.generator import ADRGenerator
    gen = ADRGenerator(str(root))
    return {"adrs": gen.list_adrs(), "adr_dir": str(root / "docs" / "adr")}


@router.get("/detect", response_model=list[DetectedChangeModel])
def detect_changes(project_path: str = Query(...)):
    root = _require(project_path)
    from backend.core.adr.generator import detect_adr_worthy_changes
    changes = detect_adr_worthy_changes(root / ".projectmind")
    return [
        DetectedChangeModel(
            kind=c.kind, title=c.title, context=c.context,
            suggested_decision=c.suggested_decision,
            positive=c.positive, negative=c.negative,
            auto_confidence=c.auto_confidence,
        )
        for c in changes
    ]


@router.post("/create", response_model=ADRResponse)
def create_adr(req: ADRCreateRequest):
    root = _require(req.project_path)
    from backend.core.adr.generator import ADRGenerator
    gen = ADRGenerator(str(root))
    path = gen.create(
        title=req.title, context=req.context, decision=req.decision,
        positive=req.positive or None, negative=req.negative or None,
        status=req.status, deciders=req.deciders,
    )
    return ADRResponse(file=path.name, path=str(path), number=int(path.name[:4]))


def _require(project_path: str) -> Path:
    root = Path(project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")
    return root
