from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.compression.compressor import Compressor

router = APIRouter(prefix="/compress", tags=["compress"])


class CompressRequest(BaseModel):
    project_path: str
    with_budget: bool = True
    total_token_budget: int = 6_000


class CompressResponse(BaseModel):
    project_path: str
    context: dict
    token_estimate: int
    budget: Optional[dict] = None
    assembled_text: Optional[str] = None


@router.post("", response_model=CompressResponse)
def compress_context(req: CompressRequest):
    root = Path(req.project_path).resolve()
    pm_dir = root / ".projectmind"
    if not pm_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f".projectmind/ not found in {root}. Run POST /analyze first.",
        )

    try:
        compressor = Compressor(str(root))
        if req.with_budget:
            from backend.core.compression.budget import coding_agent_budget
            budget = coding_agent_budget(req.total_token_budget)
            result = compressor.compress_with_budget(budget)
            return CompressResponse(
                project_path=str(root),
                context=result["context_json"],
                token_estimate=result["budget"]["used"],
                budget=result["budget"],
                assembled_text=result["assembled_text"],
            )
        ctx = compressor.compress()
        return CompressResponse(
            project_path=str(root),
            context=ctx,
            token_estimate=compressor.estimate_tokens(),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
