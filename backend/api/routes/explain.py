"""
Grounded README/explain endpoint.

POST /explain/generate
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/explain", tags=["explain"])


class ExplainRequest(BaseModel):
    project_path: str
    audience: str = "developer"
    include_issues: bool = False
    llm_enhance: bool = False
    api_key: Optional[str] = None
    llm_provider: str = "openai"
    model: Optional[str] = None
    write_to_file: bool = False   # if True, write README.md to project root


class ExplainResponse(BaseModel):
    markdown: str
    written_to: Optional[str] = None


@router.post("/generate", response_model=ExplainResponse)
def generate_explanation(req: ExplainRequest):
    root = Path(req.project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")
    if not (root / ".projectmind").exists():
        raise HTTPException(status_code=400, detail="Run `projectmind init` first.")

    from backend.core.explain.generator import ExplainGenerator
    try:
        gen = ExplainGenerator(str(root))
        md = gen.generate(
            audience=req.audience,
            include_issues=req.include_issues,
            llm_enhance=req.llm_enhance,
            api_key=req.api_key,
            llm_provider=req.llm_provider,
            model=req.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    written_to: Optional[str] = None
    if req.write_to_file:
        out = root / "README.md"
        out.write_text(md, encoding="utf-8")
        written_to = str(out)

    return ExplainResponse(markdown=md, written_to=written_to)
