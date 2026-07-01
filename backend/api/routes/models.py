"""
Multi-model orchestration API.

Endpoints:
  GET  /models/available          — list every model available given current env keys
  GET  /models/catalog            — full catalog (all models, including unavailable ones)
  POST /models/recommend          — classify a task and recommend the best model per agent
  GET  /models/routing-table      — show the complexity → tier → model mapping
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.llm.catalog import ALL_MODELS, ModelConfig, ModelTier, TaskComplexity
from backend.llm.router import (
    ModelRouter,
    _available_models,
    _available_providers,
    classify_task,
)

router = APIRouter(prefix="/models", tags=["models"])


# ── Response schemas ───────────────────────────────────────────────────────────

class ModelOut(BaseModel):
    provider: str
    model_id: str
    display_name: str
    tier: str
    context_window: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    strengths: list[str]
    available: bool
    requires_env: str


class RecommendRequest(BaseModel):
    description: str = ""
    diff: str = ""
    file_count: int = 0
    preferred_provider: Optional[str] = None
    budget_per_task_usd: float = 1.0
    force_complexity: Optional[str] = None   # "simple" | "medium" | "complex"


class AgentRecommendation(BaseModel):
    agent: str
    model_id: str
    provider: str
    display_name: str
    tier: str
    reason: str
    estimated_cost_usd: float


class RecommendResponse(BaseModel):
    complexity: str
    agents: list[AgentRecommendation]
    total_estimated_cost_usd: float
    available_providers: list[str]


class RoutingTableEntry(BaseModel):
    complexity: str
    preferred_tiers: list[str]
    example_models: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _model_to_out(m: ModelConfig, available_ids: set[str]) -> ModelOut:
    return ModelOut(
        provider=m.provider,
        model_id=m.model_id,
        display_name=m.display_name,
        tier=m.tier.value,
        context_window=m.context_window,
        cost_per_1k_input=m.cost_per_1k_input,
        cost_per_1k_output=m.cost_per_1k_output,
        strengths=m.strengths,
        available=m.model_id in available_ids,
        requires_env=m.requires_env,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/available", summary="List models available with current API keys")
def get_available_models() -> list[ModelOut]:
    available = _available_models()
    available_ids = {m.model_id for m in available}
    return [_model_to_out(m, available_ids) for m in available]


@router.get("/catalog", summary="Full model catalog across all providers")
def get_full_catalog() -> list[ModelOut]:
    available_ids = {m.model_id for m in _available_models()}
    return [_model_to_out(m, available_ids) for m in ALL_MODELS]


@router.post("/recommend", summary="Classify task complexity and recommend best model per agent")
def recommend_models(req: RecommendRequest) -> RecommendResponse:
    force = TaskComplexity(req.force_complexity) if req.force_complexity else None
    complexity = force or classify_task(req.description, req.diff, req.file_count)

    preferred = req.preferred_provider or os.environ.get("LLM_PROVIDER", "nvidia")
    mr = ModelRouter(
        preferred_provider=preferred,
        budget_per_task_usd=req.budget_per_task_usd,
    )

    all_decisions = mr.route_all_agents(complexity)
    agents_out: list[AgentRecommendation] = []
    total_cost = 0.0

    for role, decision in all_decisions.items():
        agents_out.append(AgentRecommendation(
            agent=role,
            model_id=decision.model.model_id,
            provider=decision.model.provider,
            display_name=decision.model.display_name,
            tier=decision.model.tier.value,
            reason=decision.reason,
            estimated_cost_usd=decision.estimated_cost_usd,
        ))
        total_cost += decision.estimated_cost_usd

    return RecommendResponse(
        complexity=complexity.value,
        agents=agents_out,
        total_estimated_cost_usd=round(total_cost, 6),
        available_providers=sorted(_available_providers()),
    )


@router.get("/routing-table", summary="Show complexity → tier → model routing rules")
def get_routing_table() -> list[RoutingTableEntry]:
    from backend.llm.router import _COMPLEXITY_TO_TIERS
    available = _available_models()

    rows = []
    for complexity, tiers in _COMPLEXITY_TO_TIERS.items():
        examples = []
        for tier in tiers:
            for m in available:
                if m.tier == tier:
                    examples.append(m.model_id)
                    break
        rows.append(RoutingTableEntry(
            complexity=complexity.value,
            preferred_tiers=[t.value for t in tiers],
            example_models=examples[:3],
        ))
    return rows


@router.get("/providers", summary="Show which providers are active given current env keys")
def get_active_providers() -> dict:
    providers = _available_providers()
    return {
        "active": sorted(providers),
        "inactive": sorted(
            p for p in ["nvidia", "openai", "anthropic", "gemini", "deepseek", "ollama"]
            if p not in providers
        ),
        "hint": "Add the missing env vars to unlock additional providers.",
    }
