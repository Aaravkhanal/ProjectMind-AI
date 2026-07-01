import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

from backend.core.dna.extractor import DNAExtractor
from backend.core.dna.generator import DNAGenerator
from backend.llm.providers import LLM, LLMProvider, PromptTemplate

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    project_path: str
    enhance_with_llm: bool = False
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_provider: str = "openai"


class AnalyzeResponse(BaseModel):
    project_path: str
    language: str
    frameworks: list[str]
    architecture_pattern: str
    database: Optional[str]
    auth_strategy: Optional[str]
    deployment: list[str]
    has_tests: bool
    test_framework: Optional[str]
    source_files: int
    total_files: int
    projectmind_dir: str
    message: str


@router.post("", response_model=AnalyzeResponse)
def analyze_project(req: AnalyzeRequest):
    root = Path(req.project_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {root}")
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {root}")

    extractor = DNAExtractor(str(root))
    dna = extractor.extract()

    llm_summary: Optional[str] = None
    if req.enhance_with_llm:
        try:
            api_key = req.llm_api_key or os.environ.get("API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            model_name = req.llm_model or os.environ.get("CODE_MODEL", "gpt-4o-mini")
            provider = LLMProvider(req.llm_provider.lower())
            llm = LLM(model_name=model_name, provider=provider, api_key=api_key)
            prompt = LLM.load_prompt(PromptTemplate.DNA_EXTRACT)
            chain = prompt | llm.model | StrOutputParser()
            llm_summary = chain.invoke({
                "dna_data": str(dna.to_dict()),
                "folder_structure": "\n".join(dna.folder_structure),
            })
        except Exception as e:
            llm_summary = None

    generator = DNAGenerator(dna, llm_summary=llm_summary)
    pm_dir = generator.generate()

    return AnalyzeResponse(
        project_path=str(root),
        language=dna.language,
        frameworks=dna.frameworks,
        architecture_pattern=dna.architecture_pattern,
        database=dna.database,
        auth_strategy=dna.auth_strategy,
        deployment=dna.deployment,
        has_tests=dna.has_tests,
        test_framework=dna.test_framework,
        source_files=dna.source_files,
        total_files=dna.total_files,
        projectmind_dir=str(pm_dir),
        message=f"ProjectMind initialized at {pm_dir}",
    )
