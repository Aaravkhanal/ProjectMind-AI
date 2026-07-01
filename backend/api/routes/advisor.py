"""
Architect Advisor endpoint.

POST /advisor/ask
  Answer an architectural question about a project using compressed context.
  The LLM never reads raw source code — only the ~600-token compressed summary.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/advisor", tags=["advisor"])


class AdvisorRequest(BaseModel):
    project_path: str
    question: str
    llm_provider: str = "openai"
    model: Optional[str] = None
    api_key: Optional[str] = None


class AdvisorResponse(BaseModel):
    answer: str
    question: str
    context_tokens: int


@router.post("/ask", response_model=AdvisorResponse)
def ask_architect(req: AdvisorRequest):
    from backend.core.advisor.advisor import ArchitectAdvisor
    from pathlib import Path

    root = Path(req.project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")
    if not (root / ".projectmind").exists():
        raise HTTPException(
            status_code=400,
            detail=f"No .projectmind/ at {root} — run `projectmind init` first.",
        )

    api_key = req.api_key or os.environ.get("API_KEY", "")

    try:
        advisor = ArchitectAdvisor(str(root))
        result = advisor.ask(
            question=req.question,
            llm_provider=req.llm_provider,
            model=req.model,
            api_key=api_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advisor failed: {e}")

    return AdvisorResponse(
        answer=result["answer"],
        question=result["question"],
        context_tokens=result["context_tokens"],
    )
