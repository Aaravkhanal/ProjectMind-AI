"""
BYOK Provider Management API.

GET  /providers/catalog         — all 15+ supported providers with metadata
GET  /providers                 — configured providers for a project
POST /providers/add             — add / update an API key
DELETE /providers/{provider}    — deactivate a provider
POST /providers/{provider}/test — validate API key with real call
POST /providers/{provider}/benchmark — run model profiling (async)
GET  /providers/recommendations — best/cheapest/fastest per task type
POST /providers/complete        — single LLM call via LiteLLM gateway
POST /providers/debate          — debate mode: N models, synthesize winner
POST /providers/vote            — voting mode: N models, majority answer
POST /providers/reflect         — reflection mode: self-critique
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.core.providers.schema import SUPPORTED_PROVIDERS, PROVIDER_METADATA

router = APIRouter(prefix="/providers", tags=["providers"])


def _store():
    from backend.core.providers.store import ProviderStore
    db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
    s = ProviderStore(db_path=db_path)
    s.init_db()
    return s


# ── Request models ────────────────────────────────────────────────────────────

class AddProviderRequest(BaseModel):
    project_path: str = "."
    provider: str                   # "openai" | "anthropic" | etc.
    api_key: Optional[str] = None   # None for local providers (Ollama)
    base_url_override: Optional[str] = None   # custom endpoint

class CompleteRequest(BaseModel):
    project_path: str = "."
    model: str                      # "claude-sonnet-4-6" | "gpt-4o" | etc.
    messages: list[dict]
    temperature: float = 0.3
    max_tokens: int = 2048

class DebateRequest(BaseModel):
    project_path: str = "."
    question: str
    models: list[str] = ["claude-sonnet-4-6", "gpt-4o", "deepseek-chat"]
    synthesizer_model: Optional[str] = None
    max_tokens: int = 1024

class VoteRequest(BaseModel):
    project_path: str = "."
    question: str
    models: list[str] = ["claude-sonnet-4-6", "gpt-4o", "deepseek-chat"]
    max_tokens: int = 512

class ReflectRequest(BaseModel):
    project_path: str = "."
    question: str
    model: str = "claude-sonnet-4-6"
    reflection_rounds: int = 1
    max_tokens: int = 1024

class BenchmarkRequest(BaseModel):
    project_path: str = "."
    provider: str
    model_ids: list[str]
    tasks: Optional[list[str]] = None   # None = all 8 task types


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/catalog", summary="All supported providers with metadata")
def get_catalog():
    """Returns full list of supported providers, their env key names, and default models."""
    return {
        "providers": [
            {
                "id":       p,
                "label":    PROVIDER_METADATA.get(p, {}).get("label", p),
                "base_url": PROVIDER_METADATA.get(p, {}).get("base_url"),
                "key_env":  PROVIDER_METADATA.get(p, {}).get("key_env"),
                "models":   PROVIDER_METADATA.get(p, {}).get("models", []),
                "is_local": p in ("ollama", "lmstudio", "vllm", "llamacpp"),
            }
            for p in SUPPORTED_PROVIDERS
        ],
        "total": len(SUPPORTED_PROVIDERS),
    }


@router.get("", summary="Configured providers for a project")
def list_providers(project_path: str = "."):
    store = _store()
    return {"providers": store.list_providers(project_path)}


@router.post("/add", summary="Add or update a provider API key")
def add_provider(req: AddProviderRequest):
    """
    Store an encrypted API key for a provider.
    For local providers (Ollama, LM Studio), api_key is optional.
    """
    store = _store()
    record = store.add_provider(
        project_path=req.project_path,
        provider=req.provider,
        api_key=req.api_key,
        base_url_override=req.base_url_override,
    )
    meta = PROVIDER_METADATA.get(req.provider, {})
    return {
        "provider":    record.provider,
        "label":       meta.get("label", req.provider),
        "has_key":     bool(record.encrypted_key),
        "is_active":   record.is_active,
        "health_status": record.health_status,
    }


@router.delete("/{provider}", summary="Deactivate a provider")
def remove_provider(provider: str, project_path: str = "."):
    store = _store()
    ok = store.remove_provider(project_path, provider)
    if not ok:
        raise HTTPException(404, f"Provider '{provider}' not found for this project")
    return {"removed": provider}


@router.post("/{provider}/test", summary="Test provider connectivity with a real API call")
def test_provider(provider: str, project_path: str = "."):
    """
    Validates the API key by sending a minimal completion request.
    Updates health status in DB.
    """
    from backend.llm.litellm_gateway import LiteLLMGateway

    gateway = LiteLLMGateway(project_path=project_path)
    result  = gateway.test_provider(provider)

    store = _store()
    store.update_health(
        project_path=project_path,
        provider=provider,
        status="ok" if result["ok"] else "error",
        message=result.get("error") or f"Latency: {result.get('latency_ms', 0):.0f}ms",
    )

    return {
        "provider":    provider,
        "ok":          result["ok"],
        "latency_ms":  result.get("latency_ms", 0),
        "error":       result.get("error"),
        "model_tested":result.get("model_tested"),
    }


@router.post("/{provider}/benchmark", summary="Profile all models for a provider")
def benchmark_provider(req: BenchmarkRequest, background_tasks: BackgroundTasks):
    """
    Runs model capability benchmarking in the background.
    Results are stored in ModelProfile table and retrievable via /providers/recommendations.
    """
    from backend.core.providers.profiler import ModelProfiler

    def _run():
        db_path = os.environ.get("DB_PATH", ".projectmind/memory.db")
        profiler = ModelProfiler(project_path=req.project_path, db_path=db_path)
        profiler.profile_all_models(
            provider=req.provider,
            model_ids=req.model_ids,
            tasks=req.tasks,
        )

    background_tasks.add_task(_run)
    return {
        "status":   "benchmarking_started",
        "provider": req.provider,
        "models":   req.model_ids,
        "tasks":    req.tasks or ["all"],
        "note":     "Results available at GET /providers/recommendations when complete",
    }


@router.get("/recommendations", summary="Best/cheapest/fastest model per task type")
def get_recommendations(project_path: str = "."):
    """
    Returns a matrix of best/cheapest/fastest model for each task type,
    based on profiling data. Empty if no benchmarks have been run.
    """
    store = _store()
    return {
        "project_path": project_path,
        "recommendations": store.get_recommendations(project_path),
        "note": "Run POST /providers/{provider}/benchmark to populate this data",
    }


# ── LiteLLM Gateway endpoints ─────────────────────────────────────────────────

@router.post("/complete", summary="Single LLM call through LiteLLM (any provider)")
def complete(req: CompleteRequest):
    """
    Direct LLM completion using any supported model.
    API keys resolved from BYOK store or environment.
    """
    from backend.llm.litellm_gateway import LiteLLMGateway

    gateway = LiteLLMGateway(project_path=req.project_path)
    try:
        resp = gateway.complete(
            model=req.model,
            messages=req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return {
            "text":          resp.text,
            "model":         resp.model,
            "provider":      resp.provider,
            "tokens_input":  resp.tokens_input,
            "tokens_output": resp.tokens_output,
            "cost_usd":      resp.cost_usd,
            "latency_ms":    resp.latency_ms,
        }
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")


@router.post("/debate", summary="Debate mode: same question → N models → synthesized winner")
def debate(req: DebateRequest):
    """
    Routes the same question to multiple models simultaneously.
    A synthesizer judges responses and produces a final combined answer.

    Use for: complex decisions, architectural trade-offs, code reviews where you
    want multiple AI perspectives.
    """
    from backend.agents.orchestration import debate as run_debate

    try:
        result = run_debate(
            question=req.question,
            models=req.models,
            project_path=req.project_path,
            synthesizer_model=req.synthesizer_model,
            max_tokens=req.max_tokens,
        )
        return {
            "mode":                "debate",
            "final_answer":        result.final_answer,
            "winner_model":        result.winner_model,
            "synthesis_reasoning": result.synthesis_reasoning,
            "participants":        result.participants,
            "total_cost_usd":      result.total_cost_usd,
            "total_latency_ms":    result.total_latency_ms,
        }
    except Exception as e:
        raise HTTPException(500, f"Debate failed: {e}")


@router.post("/vote", summary="Voting mode: N models vote, majority wins")
def vote(req: VoteRequest):
    """
    Multiple models answer the same question.
    Best for factual / classification tasks where consensus matters.
    """
    from backend.agents.orchestration import vote as run_vote

    try:
        result = run_vote(
            question=req.question,
            models=req.models,
            project_path=req.project_path,
            max_tokens=req.max_tokens,
        )
        return {
            "mode":             "voting",
            "final_answer":     result.final_answer,
            "winner":           result.winner,
            "participants":     result.participants,
            "total_cost_usd":   result.total_cost_usd,
        }
    except Exception as e:
        raise HTTPException(500, f"Vote failed: {e}")


@router.post("/reflect", summary="Reflection mode: model critiques and improves its own answer")
def reflect(req: ReflectRequest):
    """
    A model generates a response, then critiques itself and produces an improved version.
    Best for complex reasoning where initial responses can be shallow.
    """
    from backend.agents.orchestration import reflect as run_reflect

    try:
        result = run_reflect(
            question=req.question,
            model=req.model,
            project_path=req.project_path,
            reflection_rounds=req.reflection_rounds,
            max_tokens=req.max_tokens,
        )
        return {
            "mode":         "reflection",
            "final_answer": result.final_answer,
            "all_rounds":   result.synthesis_reasoning,
            "total_cost":   result.total_cost_usd,
        }
    except Exception as e:
        raise HTTPException(500, f"Reflection failed: {e}")
