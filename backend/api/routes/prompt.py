from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.prompt.generator import SmartPromptGenerator

router = APIRouter(prefix="/prompt", tags=["prompt"])


class GeneratePromptRequest(BaseModel):
    project_path: str
    task: str
    llm_enhance: bool = False
    llm_model: Optional[str] = None
    llm_provider: str = "openai"
    api_key: Optional[str] = None
    k_memories: int = 5


class GeneratePromptResponse(BaseModel):
    prompt: str
    context: dict
    relevant_memories: list
    budget: dict
    token_estimate: int


@router.post("/generate", response_model=GeneratePromptResponse)
def generate_prompt(req: GeneratePromptRequest):
    root = Path(req.project_path).resolve()
    if not (root / ".projectmind").exists():
        raise HTTPException(
            status_code=404,
            detail=f".projectmind/ not found. Run POST /analyze first.",
        )

    try:
        gen = SmartPromptGenerator(str(root))
        result = gen.generate(
            task=req.task,
            llm_enhance=req.llm_enhance,
            llm_model=req.llm_model,
            llm_provider=req.llm_provider,
            api_key=req.api_key,
            k_memories=req.k_memories,
        )
        return GeneratePromptResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
