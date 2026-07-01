"""
Specialized AI agent endpoints.

POST /agents/plan      — Feature request → step-by-step implementation plan
POST /agents/refactor  — Code → concrete refactoring suggestions (before/after)
POST /agents/tests     — Code → runnable pytest test file
POST /agents/docs      — Code → docstrings / README section / API docs
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["specialized-agents"])


# ── Shared request / response models ──────────────────────────────────────────

class SpecializedRequest(BaseModel):
    # ── the code to work on ──────────────────────────────────────────────────
    code: str
    description: str = ""
    file_path: Optional[str] = None
    language: str = "python"
    project_context: str = ""         # pass in compressed .projectmind context

    # ── LLM routing ──────────────────────────────────────────────────────────
    api_key: Optional[str] = None
    llm_provider: str = "nvidia"
    budget_per_task_usd: float = 1.0

    # ── agent-specific knobs ─────────────────────────────────────────────────
    extra: dict = {}                  # e.g. {"doc_type": "readme"} or {"test_framework": "unittest"}


class SpecializedResponse(BaseModel):
    artifact: str
    agent: str
    model_used: str
    complexity: str
    estimated_cost_usd: float
    errors: list[str]


# ── Helper ─────────────────────────────────────────────────────────────────────

def _make_input(req: SpecializedRequest, llm_provider_override: str | None = None):
    from backend.agents.specialized.base import AgentInput
    return AgentInput(
        code=req.code,
        description=req.description,
        file_path=req.file_path,
        project_context=req.project_context,
        language=req.language,
        llm_provider=llm_provider_override or req.llm_provider or os.environ.get("LLM_PROVIDER", "nvidia"),
        api_key=req.api_key or os.environ.get("API_KEY", ""),
        budget_per_task_usd=req.budget_per_task_usd,
        extra=req.extra or {},
    )


def _to_response(out) -> SpecializedResponse:
    return SpecializedResponse(
        artifact=out.artifact,
        agent=out.agent,
        model_used=out.model_used,
        complexity=out.complexity,
        estimated_cost_usd=out.estimated_cost_usd,
        errors=out.errors,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post(
    "/plan",
    summary="Generate a step-by-step implementation plan for a feature or task",
    response_model=SpecializedResponse,
)
def plan(req: SpecializedRequest):
    """
    Takes a task description + existing code context.
    Returns a structured plan: Goal → Steps (with file paths + effort) → Risks → DoD.
    """
    from backend.agents.specialized import planner
    out = planner.run(_make_input(req))
    return _to_response(out)


@router.post(
    "/refactor",
    summary="Produce concrete before/after refactoring suggestions",
    response_model=SpecializedResponse,
)
def refactor(req: SpecializedRequest):
    """
    Analyzes the provided code and returns safe, actionable refactoring suggestions
    with BEFORE/AFTER code blocks. Each suggestion is marked [SAFE], [NEEDS_TESTS], or [RISKY].
    """
    from backend.agents.specialized import refactor as refactor_agent
    out = refactor_agent.run(_make_input(req))
    return _to_response(out)


@router.post(
    "/tests",
    summary="Generate a runnable pytest test file for the provided code",
    response_model=SpecializedResponse,
)
def generate_tests(req: SpecializedRequest):
    """
    Generates comprehensive test cases covering happy path, edge cases, and error paths.
    Output is a complete, importable test file. Pass `extra.test_framework` to use
    a different framework (e.g. `unittest`, `jest`).
    """
    from backend.agents.specialized import testing
    out = testing.run(_make_input(req))
    return _to_response(out)


@router.post(
    "/docs",
    summary="Generate documentation: docstrings, README section, or API reference",
    response_model=SpecializedResponse,
)
def generate_docs(req: SpecializedRequest):
    """
    Three doc types via `extra.doc_type`:
    - `"docstrings"` (default) — adds inline docstrings to every public function/class
    - `"readme"` — generates a README section describing the module
    - `"api"` — generates OpenAPI-style endpoint documentation for route files
    """
    from backend.agents.specialized import docs
    out = docs.run(_make_input(req))
    return _to_response(out)


@router.post(
    "/pipeline",
    summary="Run all four specialized agents on the same code in parallel",
    response_model=dict,
)
def full_pipeline(req: SpecializedRequest):
    """
    Convenience endpoint: runs plan + refactor + tests + docs on the same input
    concurrently. Returns all four artifacts in one response.
    Ideal for onboarding to a new file or doing a deep-dive on a module.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backend.agents.specialized import docs, planner, refactor as refactor_agent, testing

    inp = _make_input(req)
    tasks = {
        "plan":    lambda: planner.run(inp),
        "refactor": lambda: refactor_agent.run(inp),
        "tests":   lambda: testing.run(inp),
        "docs":    lambda: docs.run(inp),
    }

    results = {}
    errors = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                out = future.result()
                results[name] = {
                    "artifact": out.artifact,
                    "model_used": out.model_used,
                    "complexity": out.complexity,
                    "estimated_cost_usd": out.estimated_cost_usd,
                    "errors": out.errors,
                }
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                results[name] = {"artifact": "", "errors": [str(exc)]}

    total_cost = sum(
        r.get("estimated_cost_usd", 0) for r in results.values()
    )
    return {
        "results": results,
        "total_estimated_cost_usd": round(total_cost, 6),
        "pipeline_errors": errors,
    }
