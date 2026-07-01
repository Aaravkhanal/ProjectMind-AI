"""
Onboarding endpoint.

POST /onboard/generate  — generate a role-aware onboarding guide
GET  /onboard/generate  — same, with query params
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/onboard", tags=["onboarding"])


class OnboardRequest(BaseModel):
    project_path: str
    role: str = "new developer"


class OnboardResponse(BaseModel):
    project_name: str
    role: str
    markdown: str
    entry_points: list[str]
    reading_list_count: int
    key_decisions_count: int
    gotchas_count: int


@router.post("/generate", response_model=OnboardResponse)
def generate_onboarding(req: OnboardRequest):
    return _generate(req.project_path, req.role)


@router.get("/generate", response_model=OnboardResponse)
def generate_onboarding_get(
    project_path: str = Query(...),
    role: str = Query("new developer"),
):
    return _generate(project_path, role)


def _generate(project_path: str, role: str) -> OnboardResponse:
    root = Path(project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")
    if not (root / ".projectmind").exists():
        raise HTTPException(
            status_code=400,
            detail="No .projectmind/ found. Run `projectmind init` first.",
        )
    from backend.core.onboarding.generator import OnboardingGenerator

    try:
        gen = OnboardingGenerator(str(root))
        guide = gen.generate(role=role)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Onboarding generation failed: {e}")

    return OnboardResponse(
        project_name=guide.project_name,
        role=guide.role,
        markdown=guide.to_markdown(),
        entry_points=guide.entry_points,
        reading_list_count=len(guide.reading_list),
        key_decisions_count=len(guide.key_decisions),
        gotchas_count=len(guide.gotchas),
    )
